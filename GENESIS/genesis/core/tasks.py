"""Persistent task queue with a sequential worker.

A task is one unit of work run by a registered handler. Its permission level
comes from the handler (a caller cannot lower it): it is checked when the task
is submitted (an approval for levels 4–5 is consumed there) and the grant is
re-checked when it runs. Tasks left ``running`` by a crash or power cut are put
back in the queue (or failed, if out of attempts) by :meth:`TaskManager.recover`.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from ..errors import TaskCancelled, TaskError
from ..memory.db import Database
from ..security.permissions import OWNER, Level, PermissionManager
from ..security.redact import redact
from .clock import Now, utcnow
from .events import EventBus

STATUSES = ("pending", "running", "succeeded", "failed", "cancelled")
KIND_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")
MAX_ATTEMPTS = 10
MAX_ERROR_CHARS = 2000


class TaskContext:
    """What a handler receives: the task, its payload and a cancellation probe."""

    def __init__(self, task: dict[str, Any], probe: Callable[[], bool]) -> None:
        self.task = task
        self.payload: dict[str, Any] = task["payload"]
        self._probe = probe

    def cancelled(self) -> bool:
        return self._probe()

    def check_cancelled(self) -> None:
        """Call at safe points in long handlers: raises if the owner asked to cancel."""
        if self._probe():
            raise TaskCancelled(self.task["id"])


@dataclass(frozen=True)
class HandlerSpec:
    kind: str
    fn: Callable[[TaskContext], Any]
    level: Level
    description: str


def _row(row: sqlite3.Row) -> dict[str, Any]:
    task = dict(row)
    task["payload"] = json.loads(task["payload"])
    task["result"] = None if task["result"] is None else json.loads(task["result"])
    task["cancel_requested"] = bool(task["cancel_requested"])
    return task


class TaskManager:
    def __init__(
        self,
        db: Database,
        bus: EventBus,
        permissions: PermissionManager,
        logger: logging.Logger | None = None,
        now: Now = utcnow,
    ) -> None:
        self.db = db
        self.bus = bus
        self.permissions = permissions
        self.log = logger or logging.getLogger("genesis.tasks")
        self._now = now
        self._handlers: dict[str, HandlerSpec] = {}

    # -- registry ---------------------------------------------------------------

    def register(self, kind: str, fn: Callable[[TaskContext], Any], level: int, description: str = "") -> None:
        if not KIND_RE.match(kind):
            raise TaskError(f"nome di tipo non valido: {kind!r}")
        if kind in self._handlers:
            raise TaskError(f"tipo già registrato: {kind}")
        self._handlers[kind] = HandlerSpec(kind, fn, Level(level), description)

    def kinds(self) -> list[HandlerSpec]:
        return sorted(self._handlers.values(), key=lambda s: s.kind)

    # -- queue operations -------------------------------------------------------

    def submit(
        self,
        kind: str,
        payload: dict[str, Any] | None = None,
        *,
        principal: str = OWNER,
        project_id: str | None = None,
        priority: int = 0,
        max_attempts: int = 1,
        approval_id: str | None = None,
    ) -> dict[str, Any]:
        spec = self._handlers.get(kind)
        if spec is None:
            raise TaskError(f"tipo di compito sconosciuto: {kind}")
        payload = {} if payload is None else payload
        if not isinstance(payload, dict):
            raise TaskError("il payload deve essere un oggetto JSON")
        try:
            payload_json = json.dumps(payload, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise TaskError(f"payload non serializzabile in JSON: {exc}") from exc
        if not 1 <= max_attempts <= MAX_ATTEMPTS:
            raise TaskError(f"max_attempts deve essere tra 1 e {MAX_ATTEMPTS}")
        self.permissions.require(
            principal, f"task.submit:{kind}", spec.level, approval_id=approval_id, details={"project_id": project_id}
        )
        task_id, ts = uuid.uuid4().hex, self._now()
        try:
            with self.db.transaction() as c:
                c.execute(
                    "INSERT INTO tasks (id, project_id, kind, payload, principal, level, status, priority, "
                    "max_attempts, approval_id, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)",
                    (task_id, project_id, kind, payload_json, principal, int(spec.level), int(priority),
                     max_attempts, approval_id, ts, ts),
                )
        except sqlite3.IntegrityError as exc:
            raise TaskError(f"progetto inesistente: {project_id}") from exc
        self.bus.publish("task.submitted", {"id": task_id, "kind": kind, "principal": principal})
        self.log.info("task submitted", extra={"fields": {"id": task_id, "kind": kind}})
        return self.get(task_id)  # type: ignore[return-value]

    def get(self, task_id: str) -> dict[str, Any] | None:
        row = self.db.conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return _row(row) if row else None

    def list(self, status: str | None = None, project_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if status is not None and status not in STATUSES:
            raise TaskError(f"stato sconosciuto: {status} (ammessi: {', '.join(STATUSES)})")
        where, args = [], []
        if status:
            where.append("status = ?")
            args.append(status)
        if project_id:
            where.append("project_id = ?")
            args.append(project_id)
        sql = "SELECT * FROM tasks" + (" WHERE " + " AND ".join(where) if where else "")
        rows = self.db.conn.execute(sql + " ORDER BY created_at DESC, rowid DESC LIMIT ?", (*args, int(limit)))
        return [_row(r) for r in rows]

    def counts(self) -> dict[str, int]:
        counts = dict.fromkeys(STATUSES, 0)
        for r in self.db.conn.execute("SELECT status, COUNT(*) AS n FROM tasks GROUP BY status"):
            counts[r["status"]] = int(r["n"])
        return counts

    def cancel(self, task_id: str, principal: str = OWNER) -> str:
        """Cancel a pending task, or ask a running one to stop. Returns the outcome."""
        self.permissions.require(principal, "task.cancel", Level.WORKSPACE_WRITE, details={"task_id": task_id})
        ts = self._now()
        with self.db.transaction() as c:
            row = c.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                raise TaskError(f"compito inesistente: {task_id}")
            if row["status"] == "pending":
                c.execute(
                    "UPDATE tasks SET status = 'cancelled', finished_at = ?, updated_at = ? WHERE id = ?",
                    (ts, ts, task_id),
                )
                outcome = "cancelled"
            elif row["status"] == "running":
                c.execute("UPDATE tasks SET cancel_requested = 1, updated_at = ? WHERE id = ?", (ts, task_id))
                outcome = "cancel_requested"
            else:
                outcome = row["status"]
        if outcome in ("cancelled", "cancel_requested"):
            self.bus.publish(f"task.{outcome}", {"id": task_id})
        return outcome

    def recover(self) -> int:
        """Re-queue tasks interrupted mid-run (call once at start-up). Returns how many."""
        ts, recovered = self._now(), []
        with self.db.transaction() as c:
            rows = c.execute(
                "SELECT id, attempts, max_attempts, cancel_requested FROM tasks WHERE status = 'running'"
            ).fetchall()
            for r in rows:
                if r["cancel_requested"]:
                    c.execute(
                        "UPDATE tasks SET status = 'cancelled', finished_at = ?, updated_at = ? WHERE id = ?",
                        (ts, ts, r["id"]),
                    )
                elif r["attempts"] < r["max_attempts"]:
                    c.execute(
                        "UPDATE tasks SET status = 'pending', error = ?, updated_at = ? WHERE id = ?",
                        ("interrotto da un riavvio: rimesso in coda", ts, r["id"]),
                    )
                else:
                    c.execute(
                        "UPDATE tasks SET status = 'failed', error = ?, finished_at = ?, updated_at = ? WHERE id = ?",
                        (f"interrotto da un riavvio dopo {r['attempts']} tentativi", ts, ts, r["id"]),
                    )
                recovered.append(r["id"])
        for task_id in recovered:
            self.bus.publish("task.recovered", {"id": task_id})
        return len(recovered)

    # -- worker -----------------------------------------------------------------

    def run_next(self) -> dict[str, Any] | None:
        """Claim and run the highest-priority pending task. Returns it, or None if the queue is empty."""
        ts = self._now()
        with self.db.transaction() as c:
            row = c.execute(
                "SELECT id FROM tasks WHERE status = 'pending' ORDER BY priority DESC, created_at, rowid LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            task_id = row["id"]
            c.execute(
                "UPDATE tasks SET status = 'running', attempts = attempts + 1, started_at = ?, updated_at = ? "
                "WHERE id = ?",
                (ts, ts, task_id),
            )
        task = self.get(task_id)
        assert task is not None
        spec = self._handlers.get(task["kind"])
        if spec is None:
            return self._finish(task_id, "failed", error=f"nessun gestore registrato per '{task['kind']}'")
        if not self.permissions.has_grant(task["principal"], spec.level):
            return self._finish(
                task_id, "failed", error=f"permesso revocato: '{task['principal']}' non ha più il livello {int(spec.level)}"
            )
        self.bus.publish("task.started", {"id": task_id, "kind": task["kind"], "attempt": task["attempts"]})
        try:
            result = spec.fn(TaskContext(task, lambda: self._cancel_requested(task_id)))
            result_json = json.dumps(result, ensure_ascii=False, default=str)
        except TaskCancelled:
            return self._finish(task_id, "cancelled")
        except Exception as exc:
            error = redact(f"{type(exc).__name__}: {exc}")[:MAX_ERROR_CHARS]
            self.log.warning("task failed", exc_info=True, extra={"fields": {"id": task_id, "attempt": task["attempts"]}})
            if task["attempts"] < task["max_attempts"]:
                return self._requeue(task_id, error)
            return self._finish(task_id, "failed", error=error)
        return self._finish(task_id, "succeeded", result=result_json)

    def run_pending(self, max_tasks: int | None = None) -> list[dict[str, Any]]:
        """Run queued tasks one after another (the lite profile never runs two at once)."""
        done: list[dict[str, Any]] = []
        while max_tasks is None or len(done) < max_tasks:
            task = self.run_next()
            if task is None:
                break
            done.append(task)
        return done

    def _cancel_requested(self, task_id: str) -> bool:
        row = self.db.conn.execute("SELECT cancel_requested FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return bool(row and row[0])

    def _requeue(self, task_id: str, error: str) -> dict[str, Any]:
        with self.db.transaction() as c:
            c.execute(
                "UPDATE tasks SET status = 'pending', error = ?, updated_at = ? WHERE id = ?",
                (error, self._now(), task_id),
            )
        self.bus.publish("task.retry", {"id": task_id})
        return self.get(task_id)  # type: ignore[return-value]

    def _finish(self, task_id: str, status: str, *, error: str | None = None, result: str | None = None) -> dict[str, Any]:
        ts = self._now()
        with self.db.transaction() as c:
            c.execute(
                "UPDATE tasks SET status = ?, error = ?, result = ?, finished_at = ?, updated_at = ? WHERE id = ?",
                (status, error, result, ts, ts, task_id),
            )
        self.bus.publish(f"task.{status}", {"id": task_id})
        self.log.info("task finished", extra={"fields": {"id": task_id, "status": status}})
        return self.get(task_id)  # type: ignore[return-value]
