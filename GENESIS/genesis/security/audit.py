"""Append-only, hash-chained audit log.

Every row stores the SHA-256 of its content plus the previous row's hash, so
editing or deleting a row in the middle breaks the chain and ``verify()``
reports where. SQL triggers also refuse UPDATE/DELETE. Limitation: removing the
newest rows (truncation) is not detectable without an external anchor
(documented in documentation/SECURITY.md).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from ..core.clock import Now, utcnow
from ..memory.db import Database
from .redact import redact

ZERO_HASH = "0" * 64


def _digest(prev: str, ts: str, principal: str, action: str, level: int | None, outcome: str, details: str) -> str:
    payload = json.dumps([prev, ts, principal, action, level, outcome, details], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AuditLog:
    def __init__(self, db: Database, now: Now = utcnow) -> None:
        self.db = db
        self._now = now

    def record(
        self,
        principal: str,
        action: str,
        outcome: str,
        level: int | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> int:
        details_json = redact(json.dumps(dict(details or {}), ensure_ascii=False, sort_keys=True, default=str))
        level = None if level is None else int(level)
        with self.db.transaction() as c:
            row = c.execute("SELECT hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
            prev = row[0] if row else ZERO_HASH
            ts = self._now()
            digest = _digest(prev, ts, principal, action, level, outcome, details_json)
            cur = c.execute(
                "INSERT INTO audit_log (ts, principal, action, level, outcome, details, prev_hash, hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (ts, principal, action, level, outcome, details_json, prev, digest),
            )
            return int(cur.lastrowid)

    def verify(self) -> tuple[bool, int | None]:
        """(True, None) if the chain is intact, else (False, seq of the first broken row)."""
        prev = ZERO_HASH
        for r in self.db.conn.execute("SELECT * FROM audit_log ORDER BY seq"):
            expected = _digest(prev, r["ts"], r["principal"], r["action"], r["level"], r["outcome"], r["details"])
            if r["prev_hash"] != prev or r["hash"] != expected:
                return False, int(r["seq"])
            prev = r["hash"]
        return True, None

    def tail(self, n: int = 20) -> list[dict[str, Any]]:
        rows = self.db.conn.execute("SELECT * FROM audit_log ORDER BY seq DESC LIMIT ?", (int(n),)).fetchall()
        return [dict(r) for r in reversed(rows)]

    def count(self) -> int:
        return int(self.db.conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0])
