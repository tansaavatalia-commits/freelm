from __future__ import annotations

import sqlite3

import pytest

from genesis.errors import ApprovalRequired, PermissionDenied
from genesis.memory.db import Database
from genesis.security.audit import AuditLog
from genesis.security.permissions import OWNER, Level, PermissionManager


@pytest.fixture
def pm(tmp_path):
    db = Database(tmp_path / "g.db")
    db.migrate()
    audit = AuditLog(db)
    yield PermissionManager(db, audit, {"owner": 5, "system": 3, "researcher": 1})
    db.close()


def test_audit_chain_detects_tampering(tmp_path):
    db = Database(tmp_path / "g.db")
    db.migrate()
    audit = AuditLog(db)
    for i in range(3):
        audit.record("owner", f"action.{i}", "ok", 1, {"i": i})
    assert audit.verify() == (True, None)
    with pytest.raises(sqlite3.DatabaseError):  # triggers make the log append-only
        db.conn.execute("UPDATE audit_log SET outcome = 'x' WHERE seq = 2")
    with pytest.raises(sqlite3.DatabaseError):
        db.conn.execute("DELETE FROM audit_log WHERE seq = 2")
    # An attacker with direct file access drops the trigger and edits a row:
    db.conn.execute("DROP TRIGGER audit_log_no_update")
    db.conn.execute("UPDATE audit_log SET outcome = 'forged' WHERE seq = 2")
    assert audit.verify() == (False, 2)
    db.close()


def test_audit_details_are_redacted(tmp_path):
    db = Database(tmp_path / "g.db")
    db.migrate()
    audit = AuditLog(db)
    audit.record("owner", "x", "ok", details={"api_key": "sk-or-v1-" + "q" * 40})
    assert "q" * 40 not in audit.tail(1)[0]["details"]
    db.close()


def test_levels_within_and_above_grant(pm):
    assert pm.authorize("researcher", "read", Level.READ).allowed
    assert not pm.authorize("researcher", "write", Level.WORKSPACE_WRITE).allowed
    assert not pm.authorize("unknown-agent", "read", Level.READ).allowed  # no grant = nothing
    with pytest.raises(PermissionDenied):
        pm.require("researcher", "run", Level.EXECUTE)
    with pytest.raises(ValueError):
        pm.authorize("owner", "x", 6)


def test_grants_cannot_be_raised_at_runtime(pm):
    with pytest.raises(TypeError):
        pm.grants["researcher"] = 5  # type: ignore[index]
    assert pm.grant_of("researcher") == 1


def test_level_4_needs_single_use_owner_approval(pm):
    with pytest.raises(ApprovalRequired) as info:
        pm.require(OWNER, "system.install", Level.SYSTEM_CHANGE)
    approval = info.value.approval_id
    with pytest.raises(ApprovalRequired):  # still pending
        pm.require(OWNER, "system.install", Level.SYSTEM_CHANGE, approval_id=approval)
    with pytest.raises(PermissionDenied):  # only the owner decides
        pm.decide(approval, True, decided_by="system")
    pm.decide(approval, True, decided_by=OWNER)
    assert pm.require(OWNER, "system.install", Level.SYSTEM_CHANGE, approval_id=approval).allowed
    with pytest.raises(PermissionDenied):  # consumed
        pm.require(OWNER, "system.install", Level.SYSTEM_CHANGE, approval_id=approval)


def test_approval_is_bound_to_action_principal_and_level(pm):
    approval = pm.request_approval(OWNER, "publish.release", Level.IRREVERSIBLE)
    pm.decide(approval, True, decided_by=OWNER)
    assert not pm.authorize(OWNER, "delete.everything", Level.IRREVERSIBLE, approval).allowed
    assert not pm.authorize(OWNER, "publish.release", Level.SYSTEM_CHANGE, approval).allowed
    assert not pm.authorize("system", "publish.release", Level.IRREVERSIBLE, approval).allowed  # grant 3 anyway
    assert pm.authorize(OWNER, "publish.release", Level.IRREVERSIBLE, approval).allowed


def test_denied_approval_cannot_be_used(pm):
    approval = pm.request_approval(OWNER, "spend.money", Level.IRREVERSIBLE)
    pm.decide(approval, False, decided_by=OWNER)
    assert not pm.authorize(OWNER, "spend.money", Level.IRREVERSIBLE, approval).allowed
    assert pm.list_approvals("denied")[0]["id"] == approval


def test_every_decision_is_audited(pm):
    before = pm.audit.count()
    pm.authorize("researcher", "read", Level.READ)
    pm.authorize("researcher", "write", Level.WORKSPACE_WRITE)
    rows = pm.audit.tail(2)
    assert pm.audit.count() == before + 2 and [r["outcome"] for r in rows] == ["allowed", "denied"]
