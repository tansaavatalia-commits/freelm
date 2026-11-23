from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from genesis.errors import GenesisError, MigrationError
from genesis.memory import migrations
from genesis.memory.db import Database, list_backups

GENESIS_ROOT = Path(__file__).resolve().parents[1]


def _add_project(db: Database, name: str) -> None:
    with db.transaction() as c:
        c.execute("INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, 't', 't')", (name, name))


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "g.db")
    d.migrate()
    yield d
    d.close()


def test_migrate_is_idempotent_and_uses_wal(tmp_path):
    d = Database(tmp_path / "g.db")
    assert d.migrate() == [1] and d.migrate() == [] and d.schema_version == migrations.latest()
    assert d.conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert d.integrity_ok()
    d.close()


def test_newer_schema_is_refused(tmp_path):
    raw = sqlite3.connect(tmp_path / "g.db")
    raw.execute("PRAGMA user_version = 99")
    raw.close()
    with pytest.raises(MigrationError):
        Database(tmp_path / "g.db").migrate()


def test_failed_migration_rolls_back(tmp_path, monkeypatch):
    bad = migrations.MIGRATIONS + ((2, "broken", "CREATE TABLE extra (x INTEGER); SELECT * FROM missing_table;"),)
    monkeypatch.setattr(migrations, "MIGRATIONS", bad)
    d = Database(tmp_path / "g.db")
    with pytest.raises(MigrationError):
        d.migrate()
    assert d.schema_version == 1  # v1 applied, v2 rolled back entirely
    assert d.conn.execute("SELECT name FROM sqlite_master WHERE name = 'extra'").fetchone() is None
    d.close()


def test_transaction_rolls_back_on_error(db):
    with pytest.raises(RuntimeError):
        with db.transaction():
            _add_project(db, "a")
            raise RuntimeError
    assert db.counts()["projects"] == 0


def test_committed_data_survives_a_killed_process(tmp_path):
    path = tmp_path / "g.db"
    script = (
        "import os, sys\n"
        "from genesis.memory.db import Database\n"
        "d = Database(sys.argv[1]); d.migrate()\n"
        "with d.transaction() as c:\n"
        "    c.execute(\"INSERT INTO projects (id, name, created_at, updated_at) VALUES ('k', 'k', 't', 't')\")\n"
        "os._exit(9)  # no close, no cleanup: like a crash\n"
    )
    proc = subprocess.run([sys.executable, "-c", script, str(path)], cwd=GENESIS_ROOT)
    assert proc.returncode == 9
    d = Database(path)
    assert d.integrity_ok() and d.counts()["projects"] == 1
    d.close()


def test_backup_is_verified_and_pruned(db, tmp_path):
    _add_project(db, "a")
    for _ in range(4):
        db.backup(tmp_path / "bk", keep=2)
    kept = list_backups(tmp_path / "bk")
    assert len(kept) == 2
    copy = sqlite3.connect(kept[-1])
    assert copy.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 1
    copy.close()


def test_restore_brings_data_back_and_keeps_a_safety_copy(db, tmp_path):
    _add_project(db, "before")
    snapshot = db.backup(tmp_path / "bk", keep=5)
    _add_project(db, "after")
    safety = db.restore(snapshot, tmp_path / "bk", keep=5)
    assert [r[0] for r in db.conn.execute("SELECT name FROM projects")] == ["before"]
    restored_from_safety = sqlite3.connect(safety)
    assert restored_from_safety.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 2
    restored_from_safety.close()


def test_restore_rejects_non_genesis_files(db, tmp_path):
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"not a database at all" * 100)
    with pytest.raises(GenesisError):
        db.restore(junk, tmp_path / "bk", keep=5)
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    with pytest.raises(GenesisError):
        db.restore(empty, tmp_path / "bk", keep=5)


def test_export_import_round_trip(db, tmp_path):
    _add_project(db, "p")
    with db.transaction() as c:
        c.execute("INSERT INTO tasks (id, project_id, kind, principal, level, status, created_at, updated_at) "
                  "VALUES ('t1', 'p', 'system.echo', 'owner', 1, 'succeeded', 't', 't')")
    counts = db.export_json(tmp_path / "out.json")
    assert counts["projects"] == 1 and counts["tasks"] == 1
    target = Database(tmp_path / "new.db")
    target.migrate()
    assert target.import_json(tmp_path / "out.json") == counts
    assert target.conn.execute("SELECT project_id FROM tasks").fetchone()[0] == "p"
    with pytest.raises(GenesisError):  # never into a non-empty database
        target.import_json(tmp_path / "out.json")
    target.close()


def test_import_rejects_foreign_or_malicious_files(db, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"format": "other"}), encoding="utf-8")
    with pytest.raises(GenesisError):
        db.import_json(bad)
    evil = {"format": "genesis-export", "schema_version": 1,
            "tables": {"projects": [{"id": "x", "name); DROP TABLE tasks; --": "y"}]}}
    bad.write_text(json.dumps(evil), encoding="utf-8")
    with pytest.raises(GenesisError):
        db.import_json(bad)
    assert db.conn.execute("SELECT name FROM sqlite_master WHERE name = 'tasks'").fetchone() is not None
