"""SQLite storage: connection settings, versioned migrations, verified backups,
restore, and JSON export/import for moving GÉNESIS to another machine.

WAL journal + ``synchronous=NORMAL``: committed data survives a crash of the
process; a power cut can lose the last commits but cannot corrupt the file.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .. import __version__
from ..core.clock import file_stamp, utcnow
from ..errors import GenesisError, MigrationError
from . import migrations

EXPORT_FORMAT = "genesis-export"
EXPORT_TABLES = ("projects", "tasks", "approvals", "audit_log", "agent_runs")  # FK-safe insertion order
BACKUP_GLOB = "genesis-*.db"


def list_backups(directory: Path) -> list[Path]:
    """Backups in ``directory``, oldest first (names embed a sortable timestamp)."""
    return sorted(directory.glob(BACKUP_GLOB)) if directory.is_dir() else []


class Database:
    def __init__(self, path: Path | str) -> None:
        self.path = str(path)
        in_memory = self.path == ":memory:"
        if not in_memory:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA busy_timeout = 5000")
        if not in_memory:
            self.conn.execute("PRAGMA journal_mode = WAL")
            self.conn.execute("PRAGMA synchronous = NORMAL")

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """``BEGIN IMMEDIATE`` … ``COMMIT``; rolls back on any exception. Nested use joins the outer one."""
        if self.conn.in_transaction:
            yield self.conn
            return
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield self.conn
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        self.conn.execute("COMMIT")

    # -- schema ---------------------------------------------------------------

    @property
    def schema_version(self) -> int:
        return int(self.conn.execute("PRAGMA user_version").fetchone()[0])

    def migrate(self) -> list[int]:
        """Apply pending migrations, each atomically. Returns the versions applied."""
        current = self.schema_version
        latest = migrations.latest()
        if current > latest:
            raise MigrationError(
                f"il database ha lo schema v{current}, più recente di questa versione di GÉNESIS (v{latest})"
            )
        applied: list[int] = []
        for version, _description, sql in migrations.MIGRATIONS:
            if version <= current:
                continue
            try:
                self.conn.executescript(f"BEGIN IMMEDIATE;\n{sql}\nPRAGMA user_version = {int(version)};\nCOMMIT;")
            except sqlite3.Error as exc:
                if self.conn.in_transaction:
                    self.conn.execute("ROLLBACK")
                raise MigrationError(f"migrazione v{version} fallita: {exc}") from exc
            applied.append(version)
        return applied

    def integrity_ok(self) -> bool:
        return self.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

    def counts(self) -> dict[str, int]:
        return {t: int(self.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]) for t in EXPORT_TABLES}

    # -- backup / restore -----------------------------------------------------

    def backup(self, dest_dir: Path, keep: int, *, prune: bool = True) -> Path:
        """Online backup to ``dest_dir``, verified with ``integrity_check``; keeps the newest ``keep``."""
        if keep < 1:
            raise ValueError("keep must be >= 1")
        dest_dir.mkdir(parents=True, exist_ok=True)
        stamp = file_stamp()
        seq = 0
        while (target := dest_dir / f"genesis-{stamp}-{seq:03d}.db").exists():
            seq += 1  # Windows clocks can be coarse: never overwrite a backup
        dst = sqlite3.connect(target)
        try:
            self.conn.backup(dst)
            ok = dst.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            dst.close()
        if not ok:
            target.unlink(missing_ok=True)
            raise GenesisError("il backup non ha superato il controllo di integrità")
        if prune:
            for old in list_backups(dest_dir)[:-keep]:
                old.unlink(missing_ok=True)
        return target

    def restore(self, source: Path, safety_dir: Path, keep: int) -> Path:
        """Replace the live data with ``source``. A safety backup of the current state is taken
        first and its path returned, so a restore can always be undone."""
        source = Path(source).resolve()
        if not source.is_file():
            raise GenesisError(f"file di backup non trovato: {source}")
        src = sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)
        try:
            try:
                ok = src.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                version = int(src.execute("PRAGMA user_version").fetchone()[0])
            except sqlite3.DatabaseError as exc:
                raise GenesisError(f"{source} non è un database SQLite valido ({exc})") from exc
            if not ok:
                raise GenesisError(f"{source} non supera il controllo di integrità")
            if version < 1:
                raise GenesisError(f"{source} non è un database di GÉNESIS")
            if version > migrations.latest():
                raise MigrationError(f"{source} ha lo schema v{version}, più recente di questa versione di GÉNESIS")
            safety = self.backup(safety_dir, keep, prune=False)
            src.backup(self.conn)
        finally:
            src.close()
        self.migrate()  # an older backup is brought up to the current schema
        return safety

    # -- export / import (portability) ----------------------------------------

    def export_json(self, path: Path) -> dict[str, int]:
        tables = {t: [dict(r) for r in self.conn.execute(f"SELECT * FROM {t} ORDER BY rowid")] for t in EXPORT_TABLES}
        doc = {
            "format": EXPORT_FORMAT,
            "schema_version": self.schema_version,
            "genesis_version": __version__,
            "exported_at": utcnow(),
            "tables": tables,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path)  # atomic: never a half-written export
        return {t: len(rows) for t, rows in tables.items()}

    def import_json(self, path: Path) -> dict[str, int]:
        """Load an export into an **empty** database (no data can be overwritten)."""
        try:
            doc = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise GenesisError(f"esportazione illeggibile: {exc}") from exc
        if not isinstance(doc, dict) or doc.get("format") != EXPORT_FORMAT or not isinstance(doc.get("tables"), dict):
            raise GenesisError("il file non è un'esportazione di GÉNESIS")
        if doc.get("schema_version") != self.schema_version:
            raise MigrationError(
                f"esportazione con schema v{doc.get('schema_version')}, database v{self.schema_version}: "
                "usa la stessa versione di GÉNESIS su entrambe le macchine"
            )
        if any(self.counts().values()):
            raise GenesisError("l'importazione richiede un database vuoto: usa una cartella dati nuova (--home)")
        counts: dict[str, int] = {}
        with self.transaction() as c:
            for table in EXPORT_TABLES:
                rows = doc["tables"].get(table, [])
                columns = {r[1] for r in c.execute(f"PRAGMA table_info({table})")}
                for row in rows:
                    if not isinstance(row, dict) or not row or set(row) - columns:
                        raise GenesisError(f"riga non valida nella tabella {table}")
                    keys = list(row)  # validated against the real columns above
                    c.execute(
                        f"INSERT INTO {table} ({', '.join(keys)}) VALUES ({', '.join('?' * len(keys))})",
                        [row[k] for k in keys],
                    )
                counts[table] = len(rows)
        return counts
