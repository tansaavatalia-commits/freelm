"""The GÉNESIS core assembled: one object that owns every service.

Runs with no graphical interface and with zero external providers.
"""

from __future__ import annotations

import platform
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any

from . import __version__
from .agents.catalog import load_agents
from .agents.runtime import AgentRunner
from .core.clock import Now, file_stamp, utcnow
from .core.config import Config, load_config
from .core.events import EventBus
from .core.logs import close_handler, setup_logging
from .core.projects import ProjectStore
from .core.tasks import TaskManager
from .core.worker import LOCK_FILENAME, WorkerLock
from .engines.registry import EngineRegistry
from .hardware.detect import HardwareInfo, detect
from .hardware.profiles import select_profile
from .intelligence.base import Request
from .intelligence.local import LocalEngine
from .intelligence.local_model import LocalModelProvider
from .intelligence.online import FreelmProvider
from .intelligence.router import Router
from .memory.db import Database, list_backups
from .models.catalog import load_catalog
from .research.lab import ResearchLab
from .security.audit import AuditLog
from .security.permissions import OWNER, Level, PermissionManager
from .tools.registry import ToolRegistry

MIN_FREE_DISK_GB = 2.0


class Genesis:
    def __init__(
        self,
        home: Path | str | None = None,
        *,
        config: Config | None = None,
        hardware: HardwareInfo | None = None,
        now: Now = utcnow,
    ) -> None:
        self.config = config or load_config(home)
        for folder in (self.config.data_dir, self.config.logs_dir, self.config.backups_dir, self.config.exports_dir):
            folder.mkdir(parents=True, exist_ok=True)
        self.hardware = hardware or detect(self.config.home)
        self.profile, self.profile_reason = select_profile(self.hardware, self.config.profile)
        self.log, self._log_handler = setup_logging(
            self.config.logs_dir, self.config.log_level, self.profile.log_max_bytes, self.profile.log_backups
        )
        self.db = Database(self.config.db_path)
        try:
            self.migrations_applied = self.db.migrate()
            self.bus = EventBus(self.log.getChild("events"), now=now)
            self.audit = AuditLog(self.db, now=now)
            self.permissions = PermissionManager(self.db, self.audit, self.config.grants, now=now)
            self.projects = ProjectStore(self.db, self.permissions, self.bus, now=now)
            self.tasks = TaskManager(self.db, self.bus, self.permissions, self.log.getChild("tasks"), now=now)
            self.router = Router([LocalEngine(), LocalModelProvider(self.config.local_model, self.profile.local_models),
                                  FreelmProvider()], remote_enabled=self.config.remote_enabled,
                                 remote_free_verified=self.config.remote_free_verified, audit=self.audit)
            self.tools = ToolRegistry(self.permissions, self.audit, self.config.workspace_dir,
                                      internet_enabled=self.config.internet_enabled, mcp_servers=self.config.mcp_servers)
            self.agents = AgentRunner(self.db, self.permissions, self.router, load_agents(self.config.home), now=now,
                                      tools=self.tools)
            self.engines = EngineRegistry(self)
            self.models = load_catalog(self.config.home)
            self.lab = ResearchLab(self, now=now)
            self._register_builtin_tasks()
        except BaseException:
            self.close()
            raise
        # Interrupted tasks are recovered by whoever takes the worker lock (see core/worker.py),
        # never here: a read-only command must not touch tasks a live worker is running.
        self.log.info(
            "core started",
            extra={"fields": {"version": __version__, "profile": self.profile.name,
                              "migrations": self.migrations_applied}},
        )

    def __enter__(self) -> Genesis:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self.db.close()
        close_handler(self._log_handler)

    @property
    def backup_keep(self) -> int:
        return self.config.backup_keep or self.profile.backup_keep

    def worker_lock(self) -> WorkerLock:
        return WorkerLock(self.config.data_dir / LOCK_FILENAME)

    def _register_builtin_tasks(self) -> None:
        register = self.tasks.register
        register("system.echo", lambda ctx: ctx.payload, Level.READ, "Restituisce il payload: verifica la coda.")
        register("system.hardware_snapshot", lambda ctx: detect(self.config.home).to_dict(), Level.READ,
                 "Rileva l'hardware in questo momento.")
        register("memory.integrity_check", lambda ctx: {"ok": self.db.integrity_ok()}, Level.READ,
                 "Controlla l'integrità del database.")
        register("intelligence.ask", self._ask_task, Level.READ,
                 "Chiede al router dei motori: payload {\"prompt\": \"...\", \"private\": false}.")
        register("agents.run", lambda ctx: self.agents.run(_s(ctx, "agent"), _s(ctx, "goal"), _b(ctx)), Level.READ,
                 'Esegue un agente: {"agent": "analyst", "goal": "..."}.')
        register("agents.direct", lambda ctx: self.agents.direct(_s(ctx, "goal"), _b(ctx)), Level.READ,
                 'Il Director scompone e delega: {"goal": "1. ... 2. ..."}.')
        register("agents.council", lambda ctx: self.agents.council(_s(ctx, "question"), ctx.payload.get("members"), _b(ctx)),
                 Level.READ, 'Consiglio di specialisti: {"question": "..."}.')
        register("tools.call", lambda ctx: self.tools.call(
            ctx.task["principal"], _s(ctx, "tool"), ctx.payload.get("params") or {}, approval_id=ctx.payload.get("approval_id"),
            cancelled=ctx.cancelled), Level.READ, 'Usa uno strumento: {"tool": "files.list", "params": {}} (livello dello strumento).')
        register("agents.research", lambda ctx: self.agents.research(_s(ctx, "url"), _s(ctx, "question"), _b(ctx)),
                 Level.READ, 'Il Researcher legge una pagina web: {"url": "https://...", "question": "..."}.')
        register("lab.run", self._lab_task, Level.READ,
                 'Esperimento: {"dataset": "classify-it", "subject": "classifier", "seed": 0}.')
        register("lab.reproduce", lambda ctx: self.lab.reproduce(_s(ctx, "experiment_id")), Level.READ,
                 'Riproduce un esperimento: {"experiment_id": "..."}.')
        register("engines.run", lambda ctx: self.engines.run(ctx.task["principal"], _s(ctx, "engine"), _s(ctx, "op"),
                                                             ctx.payload.get("payload") or {}), Level.READ,
                 'Operazione di un motore: {"engine": "reasoning", "op": "solve", "payload": {"text": "..."}}.')
        register("memory.backup", lambda ctx: {"path": str(self._backup())}, Level.WORKSPACE_WRITE,
                 "Crea un backup verificato del database.")

    def _ask_task(self, ctx: Any) -> dict[str, Any]:
        payload = ctx.payload
        prompt, task_type, private = payload.get("prompt"), payload.get("task_type"), payload.get("private", False)
        if not isinstance(prompt, str) or not isinstance(private, bool) or not isinstance(task_type, (str, type(None))):
            raise ValueError('payload atteso: {"prompt": "testo", "task_type": null, "private": false}')
        return self.router.route(Request(prompt, task_type, private))

    def _lab_task(self, ctx: Any) -> dict[str, Any]:
        p = ctx.payload
        allowed = {"dataset", "subject", "seed", "sample", "allow_remote", "name", "objective", "hypothesis",
                   "baseline_id"}
        if set(p) - allowed:
            raise ValueError(f"chiavi non ammesse: {', '.join(sorted(set(p) - allowed))}")
        types = {"seed": int, "sample": (int, type(None)), "allow_remote": bool, "name": (str, type(None)),
                 "objective": str, "hypothesis": str, "baseline_id": (str, type(None))}
        for key, kind in types.items():
            if key in p and (not isinstance(p[key], kind) or (kind is int and isinstance(p[key], bool))):
                raise ValueError(f"tipo non valido per {key}")
        exp = self.lab.run(dataset=_s(ctx, "dataset"), subject=_s(ctx, "subject"), seed=p.get("seed", 0),
                           sample=p.get("sample"), allow_remote=p.get("allow_remote", False), name=p.get("name"),
                           objective=p.get("objective", ""), hypothesis=p.get("hypothesis", ""),
                           baseline_id=p.get("baseline_id"))
        return {"experiment_id": exp["id"], "metrics": exp["metrics"], "evaluation": exp["evaluation"]}

    # -- memory operations ------------------------------------------------------

    def create_backup(self, principal: str = OWNER) -> Path:
        self.permissions.require(principal, "memory.backup", Level.WORKSPACE_WRITE)
        return self._backup()

    def _backup(self) -> Path:
        path = self.db.backup(self.config.backups_dir, self.backup_keep)
        self.bus.publish("memory.backup", {"path": str(path)})
        return path

    def backups(self) -> list[Path]:
        return list_backups(self.config.backups_dir)

    def restore_backup(self, source: Path | str, approval_id: str | None, principal: str = OWNER) -> Path:
        """Level 4 (needs an owner approval). Returns the safety backup of the replaced state."""
        self.permissions.require(
            principal, "memory.restore", Level.SYSTEM_CHANGE, approval_id=approval_id, details={"source": str(source)}
        )
        with self.worker_lock():  # never swap the data under a running worker ('genesis serve')
            safety = self.db.restore(Path(source), self.config.backups_dir, self.backup_keep)
            recovered = self.tasks.recover()
        # Written into the restored database, whose chain continues from the backup.
        self.audit.record(
            principal, "memory.restore", "ok", Level.SYSTEM_CHANGE,
            {"source": str(source), "safety_backup": str(safety), "approval_id": approval_id,
             "recovered_tasks": recovered},
        )
        self.bus.publish("memory.restored", {"source": str(source), "safety_backup": str(safety)})
        return safety

    def export_data(self, path: Path | str | None = None, principal: str = OWNER) -> tuple[Path, dict[str, int]]:
        self.permissions.require(principal, "memory.export", Level.WORKSPACE_WRITE)
        target = Path(path) if path else self.config.exports_dir / f"genesis-export-{file_stamp()}.json"
        return target, self.db.export_json(target)

    # -- introspection ------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        chain_ok, first_bad = self.audit.verify()
        return {
            "version": __version__,
            "home": str(self.config.home),
            "database": str(self.config.db_path),
            "schema_version": self.db.schema_version,
            "profile": self.profile.name,
            "profile_reason": self.profile_reason,
            "projects": len(self.projects.list()),
            "tasks": self.tasks.counts(),
            "pending_approvals": len(self.permissions.list_approvals("pending")),
            "audit_entries": self.audit.count(),
            "audit_chain_ok": chain_ok,
            "audit_first_bad_seq": first_bad,
            "backups": len(self.backups()),
            "engines": self.router.describe(),
        }

    def doctor(self) -> list[dict[str, str]]:
        checks: list[dict[str, str]] = []

        def add(name: str, ok: bool, detail: str, *, warn_only: bool = False) -> None:
            checks.append({"check": name, "status": "ok" if ok else ("warn" if warn_only else "fail"), "detail": detail})

        add("Python >= 3.11", sys.version_info >= (3, 11), platform.python_version())
        add("SQLite con ricerca full-text FTS5", _fts5_available(), f"SQLite {sqlite3.sqlite_version}", warn_only=True)
        add("Integrità del database", self.db.integrity_ok(), str(self.config.db_path))
        chain_ok, first_bad = self.audit.verify()
        add("Catena di audit", chain_ok, "intatta" if chain_ok else f"interrotta alla voce {first_bad}")
        add("Cartella dati scrivibile", _writable(self.config.data_dir), str(self.config.data_dir))
        free = self.hardware.disk_free_gb
        add("Spazio libero su disco", free is None or free >= MIN_FREE_DISK_GB,
            "non rilevato" if free is None else f"{free} GB liberi (minimo consigliato {MIN_FREE_DISK_GB} GB)",
            warn_only=True)
        add("RAM rilevata", self.hardware.ram_total_mb is not None,
            "non rilevata: uso il profilo prudente" if self.hardware.ram_total_mb is None
            else f"{self.hardware.ram_total_mb} MB", warn_only=True)
        return checks


def _s(ctx: Any, key: str) -> str:
    value = ctx.payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"payload: '{key}' deve essere un testo non vuoto")
    return value


def _b(ctx: Any) -> bool:
    value = ctx.payload.get("private", False)
    if not isinstance(value, bool):
        raise ValueError("payload: 'private' deve essere true o false")
    return value


def import_data(home: Path | str | None, source: Path | str) -> dict[str, int]:
    """Load an export into a fresh data folder. Runs before the core starts, so nothing
    (not even an audit row) can make the target database non-empty first."""
    config = load_config(home)
    db = Database(config.db_path)
    try:
        db.migrate()
        return db.import_json(Path(source))
    finally:
        db.close()


def _fts5_available() -> bool:
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE VIRTUAL TABLE probe USING fts5(text)")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()


def _writable(folder: Path) -> bool:
    probe = folder / f".write-test-{uuid.uuid4().hex}"
    try:
        probe.write_bytes(b"ok")
        probe.unlink()
        return True
    except OSError:
        return False
