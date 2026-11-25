"""Genesis Memory Engine: the four memory levels of the master prompt on SQLite.

* immediate  — in this process only, never written to disk (max 50 notes);
* project    — tied to a project, level 2;
* permanent  — authorized memory: the owner writes it; an agent needs grant 4 *and* an owner approval;
* operational — written only by the system.

Search uses SQLite FTS5 with BM25 ranking (accents ignored); without FTS5 it falls back to LIKE.
Secrets are redacted before anything is stored. Forgetting is a soft delete (reversible).
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
import uuid
from typing import Any

from .. import __version__
from ..core.clock import Now, utcnow
from ..core.projects import ProjectStore
from ..memory.db import Database
from ..security.permissions import OWNER, Level, PermissionManager
from ..security.redact import redact
from .base import Component, EngineOpError, GenesisEngine, Operation, text_arg

LEVELS = ("immediate", "project", "permanent", "operational")
MAX_CONTENT = 10_000
MAX_IMMEDIATE = 50


def _fold(text: str) -> str:
    """Lowercase without accents, like the FTS5 tokenizer (remove_diacritics)."""
    return unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()


class MemoryEngine(GenesisEngine):
    id, name, version = "memory", "Genesis Memory Engine", f"1.0@{__version__}"
    description = "Memoria immediata, di progetto, permanente autorizzata e operativa, con ricerca."
    components = (
        Component("archivio SQLite", "algoritmo", "tabella memories con livelli, progetti, etichette e fonte"),
        Component("ricerca full-text FTS5", "algoritmo", "classifica BM25, accenti ignorati; ripiego LIKE"),
        Component("assemblaggio del contesto", "algoritmo", "le memorie più pertinenti entro un limite di caratteri"),
    )
    operations = (
        Operation("remember", 2, "salva una memoria",
                  '{"content": "...", "level": "project|permanent|operational|immediate", "project": "...", "tags": ["..."]}'),
        Operation("recall", 1, "cerca nelle memorie", '{"query": "...", "level": "...", "project": "...", "limit": 10}'),
        Operation("forget", 2, "dimentica una memoria (reversibile)", '{"id": "..."}'),
        Operation("context", 1, "contesto pertinente per una richiesta", '{"query": "...", "budget": 1500}'),
    )

    def __init__(self, db: Database, permissions: PermissionManager, projects: ProjectStore, now: Now = utcnow) -> None:
        self.db, self.permissions, self.projects, self._now = db, permissions, projects, now
        self.immediate: list[dict[str, Any]] = []
        self.fts = self._ensure_fts()

    def _ensure_fts(self) -> bool:
        try:
            with self.db.transaction() as c:
                exists = c.execute("SELECT 1 FROM sqlite_master WHERE name = 'memories_fts'").fetchone()
                c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(content, tags, "
                          "content='memories', content_rowid='rowid', tokenize='unicode61 remove_diacritics 2')")
                c.execute("CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN "
                          "INSERT INTO memories_fts(rowid, content, tags) VALUES (new.rowid, new.content, new.tags); END")
                c.execute("CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN "
                          "INSERT INTO memories_fts(memories_fts, rowid, content, tags) "
                          "VALUES ('delete', old.rowid, old.content, old.tags); END")
                if not exists:  # e.g. data imported from another PC: index what is already there
                    c.execute("INSERT INTO memories_fts(memories_fts) VALUES ('rebuild')")
            return True
        except sqlite3.OperationalError:
            return False

    # -- operations ---------------------------------------------------------------

    def run(self, op: str, payload: dict[str, Any], principal: str = OWNER) -> Any:
        if op == "remember":
            return self.remember(principal, text_arg(payload, "content", MAX_CONTENT), str(payload.get("level", "project")),
                                 payload.get("project"), payload.get("tags") or [], str(payload.get("source", "")),
                                 payload.get("approval_id"))
        if op == "recall":
            return self.recall(text_arg(payload, "query", 500), payload.get("level"), payload.get("project"),
                               payload.get("limit", 10))
        if op == "forget":
            return self.forget(principal, str(payload.get("id", "")))
        if op == "context":
            budget = payload.get("budget", 1500)
            if not isinstance(budget, int) or isinstance(budget, bool) or not 100 <= budget <= 20_000:
                raise EngineOpError("budget tra 100 e 20000 caratteri")
            return self.context(text_arg(payload, "query", 500), budget, payload.get("project"))
        raise EngineOpError(f"operazione sconosciuta: {op}")

    def remember(self, principal: str, content: str, level: str, project: Any = None, tags: Any = None,
                 source: str = "", approval_id: Any = None) -> dict[str, Any]:
        if level not in LEVELS:
            raise EngineOpError(f"livello non valido (ammessi: {', '.join(LEVELS)})")
        tags = [] if tags is None else tags
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            raise EngineOpError("tags deve essere un elenco di testi")
        content = redact(content.strip())
        if level == "immediate":
            note = {"id": uuid.uuid4().hex, "level": level, "content": content, "tags": " ".join(tags), "created_at": self._now()}
            self.immediate = (self.immediate + [note])[-MAX_IMMEDIATE:]
            return note
        project_id = None
        if level == "project":
            found = self.projects.get(str(project)) if project else None
            if found is None:
                raise EngineOpError("la memoria di progetto richiede un progetto esistente ('project')")
            project_id = found["id"]
        elif level == "permanent" and principal != OWNER:
            # authorized memory: an agent needs an explicit owner approval
            self.permissions.require(principal, "memory.remember.permanent", Level.SYSTEM_CHANGE,
                                     approval_id=approval_id if isinstance(approval_id, str) else None)
        elif level == "operational" and principal != "system":
            raise EngineOpError("la memoria operativa è scritta solo dal sistema")
        memory_id = uuid.uuid4().hex
        with self.db.transaction() as c:
            c.execute("INSERT INTO memories (id, level, project_id, content, tags, source, principal, created_at) "
                      "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                      (memory_id, level, project_id, content, " ".join(tags), redact(source)[:500], principal, self._now()))
        return self.get(memory_id)

    def get(self, memory_id: str) -> dict[str, Any]:
        row = self.db.conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        if row is None:
            raise EngineOpError(f"memoria inesistente: {memory_id}")
        return dict(row)

    def recall(self, query: str, level: Any = None, project: Any = None, limit: Any = 10) -> list[dict[str, Any]]:
        if level is not None and level not in LEVELS:
            raise EngineOpError("livello non valido")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise EngineOpError("limit tra 1 e 100")
        words = re.findall(r"\w+", _fold(query))[:12]
        if not words:
            raise EngineOpError("la ricerca non contiene parole")
        hits: list[dict[str, Any]] = []
        if level in (None, "immediate"):
            hits += [{**n, "score": None} for n in reversed(self.immediate)
                     if any(w in _fold(n["content"]) for w in words)]
        if level == "immediate":
            return hits[:limit]
        where, args = ["m.deleted = 0"], []
        if level:
            where.append("m.level = ?")
            args.append(level)
        if project:
            found = self.projects.get(str(project))
            where.append("m.project_id = ?")
            args.append(found["id"] if found else "-")
        try:
            if not self.fts:
                raise sqlite3.OperationalError("fts non disponibile")
            match = " OR ".join(f'"{w}"' for w in words)  # quoted tokens: no FTS syntax injection
            rows = self.db.conn.execute(
                "SELECT m.*, bm25(memories_fts) AS score FROM memories_fts JOIN memories m ON m.rowid = memories_fts.rowid "
                f"WHERE memories_fts MATCH ? AND {' AND '.join(where)} ORDER BY score LIMIT ?",
                (match, *args, limit)).fetchall()
        except sqlite3.OperationalError:
            like = " OR ".join("lower(m.content) LIKE ?" for _ in words)
            rows = self.db.conn.execute(
                f"SELECT m.*, NULL AS score FROM memories m WHERE ({like}) AND {' AND '.join(where)} "
                "ORDER BY m.created_at DESC LIMIT ?", (*[f"%{w}%" for w in words], *args, limit)).fetchall()
        hits += [{**dict(r), "score": None if r["score"] is None else round(-r["score"], 4)} for r in rows]
        return hits[:limit]

    def forget(self, principal: str, memory_id: str) -> dict[str, Any]:
        memory = self.get(memory_id)
        if memory["level"] == "permanent" and principal != OWNER:
            raise EngineOpError("solo il proprietario può dimenticare una memoria permanente")
        if memory["level"] == "operational" and principal != "system":
            raise EngineOpError("la memoria operativa è gestita solo dal sistema")
        with self.db.transaction() as c:
            c.execute("UPDATE memories SET deleted = 1 WHERE id = ?", (memory_id,))
        return {"id": memory_id, "forgotten": True}

    def context(self, query: str, budget: int = 1500, project: Any = None) -> dict[str, Any]:
        lines, used, ids = [], 0, []
        for m in self.recall(query, None, project, 20):
            line = f"- [{m['level']}] {m['content']}"
            if used + len(line) > budget:
                break
            lines.append(line)
            ids.append(m["id"])
            used += len(line) + 1
        return {"context": "\n".join(lines), "memories": ids, "characters": used}
