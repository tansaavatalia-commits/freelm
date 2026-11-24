from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from genesis.cli import main

from .conftest import write_config

GENESIS_ROOT = Path(__file__).resolve().parents[1]


def run(home, *args):
    return main(["--home", str(home), *args])


def test_status_and_doctor(home, capsys):
    assert run(home, "status", "--json") == 0
    status = json.loads(capsys.readouterr().out)
    assert status["schema_version"] == 1 and status["audit_chain_ok"] and [e["id"] for e in status["engines"]] == ["local", "freelm"]
    assert run(home, "doctor") == 0
    out = capsys.readouterr().out
    assert "Profilo:" in out and "[OK] Integrità del database" in out
    assert run(home, "doctor", "--json") == 0
    assert "ram_total_mb" in json.loads(capsys.readouterr().out)["hardware"]


def test_project_task_flow(home, capsys):
    assert run(home, "project", "add", "Demo", "-d", "prova") == 0
    assert run(home, "task", "submit", "system.echo", "--payload", '{"a": 1}', "--project", "demo") == 0
    task_id = capsys.readouterr().out.split("Compito in coda: ")[1].split()[0]
    assert run(home, "task", "run") == 0
    assert "succeeded" in capsys.readouterr().out
    assert run(home, "task", "show", task_id) == 0
    assert json.loads(capsys.readouterr().out)["result"] == {"a": 1}
    assert run(home, "task", "submit", "system.echo", "--payload", "{not json") == 2
    assert run(home, "task", "submit", "nope") == 1


def test_backup_restore_requires_confirm(home, capsys):
    assert run(home, "project", "add", "Prima") == 0
    assert run(home, "backup", "create") == 0
    backup = capsys.readouterr().out.strip().splitlines()[-1].split(": ", 1)[1]
    assert run(home, "project", "add", "Seconda") == 0
    assert run(home, "backup", "restore", backup) == 2  # no --confirm: nothing happens
    assert run(home, "project", "list") == 0
    assert "Seconda" in capsys.readouterr().out
    assert run(home, "backup", "restore", backup, "--confirm") == 0
    capsys.readouterr()
    assert run(home, "project", "list") == 0
    out = capsys.readouterr().out
    assert "Prima" in out and "Seconda" not in out
    assert run(home, "audit", "verify") == 0


def test_export_then_import_on_a_new_machine(home, tmp_path, capsys):
    assert run(home, "project", "add", "Portabile") == 0
    export = tmp_path / "export.json"
    assert run(home, "export", str(export)) == 0
    new_home = tmp_path / "other-pc"
    assert run(new_home, "doctor") == 0  # first run on the new PC (creates an empty database)
    assert run(new_home, "import", str(export)) == 0
    assert run(new_home, "import", str(export)) == 1  # never into a non-empty database
    capsys.readouterr()
    assert run(new_home, "project", "list") == 0
    assert "Portabile" in capsys.readouterr().out
    assert run(new_home, "audit", "verify") == 0


def test_approvals_commands(home, capsys):
    assert run(home, "approvals", "list") == 0
    assert "Nessuna approvazione" in capsys.readouterr().out
    assert run(home, "approvals", "approve", "missing") == 1


def test_bad_config_exits_2(home):
    write_config(home, "[general]\nprofile = 'turbo'\n")
    assert run(home, "status") == 2


def test_module_entry_point(tmp_path):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run([sys.executable, "-m", "genesis", "--home", str(tmp_path / "h"), "status"],
                          cwd=GENESIS_ROOT, capture_output=True, text=True, encoding="utf-8", env=env)
    assert proc.returncode == 0, proc.stderr
    assert "GÉNESIS" in proc.stdout


def test_no_private_data_inside_the_package():
    # Databases, data folders and real config files must never live in the repository.
    forbidden = {".db", ".sqlite", ".sqlite3", ".env", ".db-wal", ".db-shm"}
    leaks = [p for p in GENESIS_ROOT.rglob("*")
             if p.is_file() and (p.suffix in forbidden or p.name == "genesis.toml")]
    assert leaks == []
