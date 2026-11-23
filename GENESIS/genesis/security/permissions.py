"""Central permission layer: five autonomy levels, owner approvals, full audit.

* Every principal (the owner, the system, later each agent) has a maximum level
  read from the configuration at start-up. The mapping is read-only at runtime:
  there is no API to raise a grant, so nobody can widen their own permissions.
* Levels 4 (system changes) and 5 (irreversible/economic actions) additionally
  need an owner approval that matches principal, action and level, and is
  consumed on use (single use).
* Only the owner can decide approvals. Every decision is written to the audit log.

In-process Python code is trusted by design; agents (Phase 4) will act only
through this layer and never get a reference to :meth:`PermissionManager.decide`.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from enum import IntEnum
from types import MappingProxyType
from typing import Any, Mapping

from ..core.clock import Now, utcnow
from ..errors import ApprovalRequired, GenesisError, PermissionDenied
from ..memory.db import Database
from .audit import AuditLog

OWNER = "owner"


class Level(IntEnum):
    READ = 1  # reading, research, analysis
    WORKSPACE_WRITE = 2  # creating working files and records
    EXECUTE = 3  # running tests and controlled processes
    SYSTEM_CHANGE = 4  # installs and system changes: owner approval
    IRREVERSIBLE = 5  # spending, publishing, permanent deletion: explicit owner approval


APPROVAL_LEVEL = Level.SYSTEM_CHANGE


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    approval_id: str | None = None
    needs_approval: bool = False


class PermissionManager:
    def __init__(self, db: Database, audit: AuditLog, grants: Mapping[str, int], now: Now = utcnow) -> None:
        self.db = db
        self.audit = audit
        self._grants: Mapping[str, int] = MappingProxyType(dict(grants))
        self._now = now

    @property
    def grants(self) -> Mapping[str, int]:
        return self._grants

    def grant_of(self, principal: str) -> int:
        return int(self._grants.get(principal, 0))

    def has_grant(self, principal: str, level: int) -> bool:
        return self.grant_of(principal) >= int(level)

    def authorize(
        self,
        principal: str,
        action: str,
        level: int,
        approval_id: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> Decision:
        """Decide (and audit) whether ``principal`` may perform ``action`` at ``level``."""
        level = Level(level)
        if not self.has_grant(principal, level):
            decision = Decision(
                False, f"'{principal}' ha permesso massimo {self.grant_of(principal)}, richiesto {int(level)}"
            )
        elif level >= APPROVAL_LEVEL:
            decision = self._consume(principal, action, level, approval_id)
        else:
            decision = Decision(True, "entro il permesso concesso")
        self.audit.record(
            principal,
            action,
            "allowed" if decision.allowed else "denied",
            int(level),
            {"reason": decision.reason, "approval_id": decision.approval_id, "details": dict(details or {})},
        )
        return decision

    def require(
        self,
        principal: str,
        action: str,
        level: int,
        approval_id: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> Decision:
        """Like :meth:`authorize` but raises. A missing approval creates a pending request."""
        decision = self.authorize(principal, action, level, approval_id, details)
        if decision.allowed:
            return decision
        if decision.needs_approval:
            pending = decision.approval_id or self.request_approval(principal, action, level, details)
            raise ApprovalRequired(pending, action, int(level))
        raise PermissionDenied(f"azione '{action}' negata: {decision.reason}")

    def _consume(self, principal: str, action: str, level: Level, approval_id: str | None) -> Decision:
        if not approval_id:
            return Decision(False, "serve l'approvazione del proprietario", needs_approval=True)
        with self.db.transaction() as c:
            row = c.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
            if row is None:
                return Decision(False, "approvazione inesistente", approval_id)
            if (row["principal"], row["action"], row["level"]) != (principal, action, int(level)):
                return Decision(False, "l'approvazione riguarda un'altra azione", approval_id)
            if row["status"] == "pending":
                return Decision(False, "approvazione in attesa del proprietario", approval_id, needs_approval=True)
            if row["status"] != "approved":
                return Decision(False, f"approvazione in stato '{row['status']}'", approval_id)
            c.execute("UPDATE approvals SET status = 'used' WHERE id = ?", (approval_id,))
        return Decision(True, "approvata dal proprietario (uso singolo)", approval_id)

    # -- approvals --------------------------------------------------------------

    def request_approval(
        self, principal: str, action: str, level: int, details: Mapping[str, Any] | None = None
    ) -> str:
        level = Level(level)
        approval_id = uuid.uuid4().hex
        with self.db.transaction() as c:
            c.execute(
                "INSERT INTO approvals (id, principal, action, level, details, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, 'pending', ?)",
                (approval_id, principal, action, int(level), json.dumps(dict(details or {}), default=str), self._now()),
            )
        self.audit.record(principal, "approval.request", "pending", int(level), {"approval_id": approval_id, "action": action})
        return approval_id

    def decide(self, approval_id: str, approve: bool, decided_by: str) -> None:
        if decided_by != OWNER:
            self.audit.record(decided_by, "approval.decide", "denied", None, {"approval_id": approval_id})
            raise PermissionDenied("solo il proprietario può decidere le approvazioni")
        status = "approved" if approve else "denied"
        with self.db.transaction() as c:
            row = c.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
            if row is None:
                raise GenesisError(f"approvazione inesistente: {approval_id}")
            if row["status"] != "pending":
                raise GenesisError(f"approvazione già decisa (stato '{row['status']}')")
            c.execute(
                "UPDATE approvals SET status = ?, decided_at = ?, decided_by = ? WHERE id = ?",
                (status, self._now(), decided_by, approval_id),
            )
        self.audit.record(
            OWNER, "approval.decide", status, int(row["level"]), {"approval_id": approval_id, "action": row["action"]}
        )

    def list_approvals(self, status: str | None = None) -> list[dict[str, Any]]:
        sql, args = "SELECT * FROM approvals", ()
        if status:
            sql, args = sql + " WHERE status = ?", (status,)
        rows = self.db.conn.execute(sql + " ORDER BY created_at, rowid", args).fetchall()
        return [{**dict(r), "details": json.loads(r["details"])} for r in rows]
