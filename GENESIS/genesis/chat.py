"""Núcleo chat: conversations with history, memory and free engines.

A turn is prepared on the core thread (store the user message, local commands, deterministic engines,
choose the streaming engine), the model streams *outside* the core thread (so the interface stays
responsive), and the answer is stored back on the core thread. Rules inherited from the router:
paid engines never, remote engines only if the owner enabled them and confirmed they are free,
a private conversation never leaves this computer.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from .core.clock import Now, utcnow
from .errors import GenesisError
from .intelligence.base import Provider, Request
from .intelligence.router import Router, RouterError
from .memory.db import Database
from .security.permissions import OWNER
from .security.redact import redact

MAX_MESSAGE = 8_000
HISTORY_BUDGET = 12_000  # characters of past turns sent to the model (free models have small contexts)
MEMORY_BUDGET = 1_500
TITLE_LEN = 60
DETERMINISTIC = ("math", "text.stats")
REMEMBER = re.compile(r"^\s*(?:ricorda(?:ti)?|memorizza)\s+(?:che\s+)?(?P<fact>.{3,})$", re.IGNORECASE | re.DOTALL)
SYSTEM_PROMPT = (
    "Sei GÉNESIS, l'assistente personale del proprietario, eseguito sul suo PC. Rispondi in italiano, in modo "
    "chiaro e diretto, con frasi semplici: il proprietario non è uno sviluppatore. Se non sei sicuro, dillo. "
    "Non inventare fatti, link o numeri. Usa elenchi e titoli in Markdown solo quando aiutano. Oggi è {today}."
)
NO_ENGINE = (
    "Per rispondere a domande libere come questa serve il **motore online gratuito**, che ora è spento.\n\n"
    "Intanto posso fare **calcoli** (per esempio `quanto fa 12*(3+4)?`), **analisi di testo** e ricordare "
    "cose che mi dici (`ricorda che …`). Come accendere il motore online: pagina Motori."
)


class ChatError(GenesisError):
    pass


class ChatStore:
    def __init__(self, db: Database, router: Router, memory: Any, now: Now = utcnow) -> None:
        self.db, self.router, self.memory, self._now = db, router, memory, now

    # -- conversations ------------------------------------------------------------

    def create(self, title: str = "", private: bool = False) -> dict[str, Any]:
        cid, now = uuid.uuid4().hex, self._now()
        with self.db.transaction() as c:
            c.execute("INSERT INTO conversations (id, title, private, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                      (cid, _title(title) or "Nuova conversazione", int(bool(private)), now, now))
        return self._conversation(cid)

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.db.conn.execute(
            "SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS messages "
            "FROM conversations c WHERE c.deleted = 0 ORDER BY c.updated_at DESC LIMIT ?", (limit,)).fetchall()
        return [_conv(r) for r in rows]

    def get(self, cid: str) -> dict[str, Any]:
        conv = self._conversation(cid)
        rows = self.db.conn.execute("SELECT * FROM messages WHERE conversation_id = ? ORDER BY seq", (cid,)).fetchall()
        return {**conv, "messages": [dict(r) for r in rows]}

    def rename(self, cid: str, title: str) -> dict[str, Any]:
        self._conversation(cid)
        if not _title(title):
            raise ChatError("titolo vuoto")
        with self.db.transaction() as c:
            c.execute("UPDATE conversations SET title = ? WHERE id = ?", (_title(title), cid))
        return self._conversation(cid)

    def delete(self, cid: str) -> dict[str, Any]:
        """Soft delete: hidden from the list, still in backups and exports (reversible)."""
        self._conversation(cid)
        with self.db.transaction() as c:
            c.execute("UPDATE conversations SET deleted = 1 WHERE id = ?", (cid,))
        return {"id": cid, "deleted": True}

    def _conversation(self, cid: str) -> dict[str, Any]:
        row = self.db.conn.execute("SELECT * FROM conversations WHERE id = ? AND deleted = 0", (cid,)).fetchone()
        if row is None:
            raise ChatError(f"conversazione inesistente: {cid}")
        return _conv(row)

    # -- messages -------------------------------------------------------------------

    def add_message(self, cid: str, role: str, content: str, *, status: str = "ok", engine: str | None = None,
                    task_type: str | None = None, ms: float | None = None) -> dict[str, Any]:
        mid, now = uuid.uuid4().hex, self._now()
        with self.db.transaction() as c:
            seq = c.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM messages WHERE conversation_id = ?", (cid,)).fetchone()[0]
            c.execute("INSERT INTO messages (id, conversation_id, seq, role, content, status, engine, task_type, ms, "
                      "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      (mid, cid, seq, role, content, status, engine, task_type, ms, now))
            c.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, cid))
            if role == "user" and seq == 1:  # first question names the conversation
                c.execute("UPDATE conversations SET title = ? WHERE id = ? AND title = 'Nuova conversazione'",
                          (_title(content), cid))
        return dict(self.db.conn.execute("SELECT * FROM messages WHERE id = ?", (mid,)).fetchone())

    # -- a turn -----------------------------------------------------------------------

    def prepare(self, cid: str, text: str) -> dict[str, Any]:
        """Store the question and decide how to answer. Returns either ``{"mode": "done", ...}`` (answered
        here, locally) or ``{"mode": "stream", "provider": ..., "messages": [...]}`` for the caller to stream."""
        conv = self._conversation(cid)
        text = (text or "").strip()
        if not text:
            raise ChatError("messaggio vuoto")
        if len(text) > MAX_MESSAGE:
            raise ChatError(f"messaggio troppo lungo (massimo {MAX_MESSAGE} caratteri)")
        private = bool(conv["private"])
        user = self.add_message(cid, "user", text)

        remember = REMEMBER.match(text)
        if remember:
            fact = remember.group("fact").strip().rstrip(".")
            saved = self.memory.remember(OWNER, fact, "permanent", tags=["chat"], source=f"chat:{cid}")
            answer = f"Ricordato. Lo userò nelle prossime risposte: «{saved['content']}»."
            return self._done(cid, user, answer, engine="memory", task_type="memory")

        task_type = self.router.classify(text)
        if task_type in DETERMINISTIC:  # verified local algorithms first: exact and instant
            try:
                result = self.router.route(Request(text, task_type, private))
                if result["verified"]:
                    return self._done(cid, user, result["output"], engine=result["engine"], task_type=task_type,
                                      ms=result["attempts"][-1]["ms"])
            except RouterError:
                pass

        provider, why = self.router.streamer(private)
        if provider is not None:
            return {"mode": "stream", "user": user, "provider": provider, "task_type": task_type,
                    "messages": self.build_messages(cid, text, private)}
        try:  # no conversational engine: whatever the router can still do for this single question
            result = self.router.route(Request(text, None, private))
            return self._done(cid, user, result["output"], engine=result["engine"], task_type=result["task_type"],
                              ms=result["attempts"][-1]["ms"])
        except RouterError:  # the technical reason is shown by /api/chat-status, not in the conversation
            return self._done(cid, user, NO_ENGINE, engine=None, task_type=task_type, status="error")

    def build_messages(self, cid: str, question: str, private: bool) -> list[dict[str, str]]:
        today = datetime.now().strftime("%d/%m/%Y")
        system = SYSTEM_PROMPT.format(today=today)
        try:
            context = self.memory.context(question, MEMORY_BUDGET)["context"]
        except Exception:  # no searchable words etc.: answer without memory rather than fail
            context = ""
        if context:
            system += ("\n\nCose che il proprietario ti ha chiesto di ricordare (usale solo se pertinenti):\n"
                       + context)
        rows = self.db.conn.execute("SELECT role, content FROM messages WHERE conversation_id = ? AND status = 'ok' "
                                    "ORDER BY seq DESC", (cid,)).fetchall()
        turns: list[dict[str, str]] = []
        used = 0
        for r in rows:  # newest first, until the budget is spent; the current question is always included
            if turns and used + len(r["content"]) > HISTORY_BUDGET:
                break
            turns.append({"role": r["role"], "content": r["content"]})
            used += len(r["content"])
        turns.reverse()
        while turns and turns[0]["role"] != "user":  # a conversation must start with the owner's turn
            turns.pop(0)
        return [{"role": "system", "content": system}, *turns]

    def finish(self, cid: str, provider: Provider, text: str, *, ok: bool, ms: float, chars: int,
               task_type: str, error: str | None = None) -> dict[str, Any]:
        """Store a streamed answer (or the failure) and record statistics + audit."""
        self.router.record_remote(provider, ok, ms, chars, task_type)
        if ok and text.strip():
            return self.add_message(cid, "assistant", text.strip(), engine=provider.spec.id, task_type=task_type, ms=ms)
        reason = redact(error or "risposta vuota")
        partial = f"{text.strip()}\n\n" if text.strip() else ""
        return self.add_message(cid, "assistant", f"{partial}⚠ Risposta interrotta: {reason}", status="error",
                                engine=provider.spec.id, task_type=task_type, ms=ms)

    def _done(self, cid: str, user: dict[str, Any], answer: str, *, engine: str | None, task_type: str | None,
              ms: float | None = None, status: str = "ok") -> dict[str, Any]:
        msg = self.add_message(cid, "assistant", answer, status=status, engine=engine, task_type=task_type, ms=ms)
        return {"mode": "done", "user": user, "message": msg}


def _title(text: str) -> str:
    line = " ".join((text or "").split())
    return line if len(line) <= TITLE_LEN else line[: TITLE_LEN - 1].rstrip() + "…"


def _conv(row: Any) -> dict[str, Any]:
    d = dict(row)
    d["private"] = bool(d["private"])
    d.pop("deleted", None)
    return d
