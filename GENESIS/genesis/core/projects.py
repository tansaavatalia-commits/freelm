"""Projects: named containers for tasks (and, later, memory and agents)."""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from ..errors import GenesisError
from ..memory.db import Database
from ..security.permissions import OWNER, Level, PermissionManager
from .clock import Now, utcnow
from .events import EventBus

NAME_MAX = 80


class ProjectStore:
    def __init__(self, db: Database, permissions: PermissionManager, bus: EventBus, now: Now = utcnow) -> None:
        self.db = db
        self.permissions = permissions
        self.bus = bus
        self._now = now

    def create(self, name: str, description: str = "", principal: str = OWNER) -> dict[str, Any]:
        name = (name or "").strip()
        if not name or len(name) > NAME_MAX or any(ch in name for ch in "\r\n\t"):
            raise GenesisError(f"nome di progetto non valido (1–{NAME_MAX} caratteri, una sola riga)")
        self.permissions.require(principal, "project.create", Level.WORKSPACE_WRITE, details={"name": name})
        project_id, ts = uuid.uuid4().hex, self._now()
        try:
            with self.db.transaction() as c:
                c.execute(
                    "INSERT INTO projects (id, name, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (project_id, name, description.strip(), ts, ts),
                )
        except sqlite3.IntegrityError as exc:
            raise GenesisError(f"esiste già un progetto chiamato '{name}'") from exc
        self.bus.publish("project.created", {"id": project_id, "name": name})
        return self.get(project_id)  # type: ignore[return-value]

    def get(self, ref: str) -> dict[str, Any] | None:
        """Look a project up by id or by name (case-insensitive)."""
        row = self.db.conn.execute(
            "SELECT * FROM projects WHERE id = ? OR name = ? COLLATE NOCASE", (ref, ref)
        ).fetchone()
        return dict(row) if row else None

    def list(self, include_archived: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT * FROM projects" + ("" if include_archived else " WHERE status = 'active'")
        return [dict(r) for r in self.db.conn.execute(sql + " ORDER BY name COLLATE NOCASE")]

    def archive(self, ref: str, principal: str = OWNER) -> dict[str, Any]:
        project = self.get(ref)
        if project is None:
            raise GenesisError(f"progetto inesistente: {ref}")
        self.permissions.require(principal, "project.archive", Level.WORKSPACE_WRITE, details={"id": project["id"]})
        with self.db.transaction() as c:
            c.execute(
                "UPDATE projects SET status = 'archived', updated_at = ? WHERE id = ?", (self._now(), project["id"])
            )
        self.bus.publish("project.archived", {"id": project["id"], "name": project["name"]})
        return self.get(project["id"])  # type: ignore[return-value]
