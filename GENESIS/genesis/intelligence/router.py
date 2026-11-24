"""Intelligent Router: classify → requirements → filter → select → execute → fallback → record.

Hard rules (tested): a paid engine is never selected, not even as a fallback; a
remote engine is used only when the owner enabled remote engines *and* declared
their free terms verified; a private request never leaves this computer.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Iterable

from ..errors import GenesisError
from ..security.audit import AuditLog
from ..security.redact import redact
from .base import TASK_TYPES, EngineError, Provider, Request
from .local import classify

MAX_ATTEMPTS = 3


class RouterError(GenesisError):
    """No engine could serve the request."""


class Router:
    def __init__(
        self,
        providers: Iterable[Provider],
        *,
        remote_enabled: bool = False,
        remote_free_verified: bool = False,
        audit: AuditLog | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.providers = list(providers)
        self.remote_enabled = remote_enabled
        self.remote_free_verified = remote_free_verified
        self.audit = audit
        self._clock = clock
        self._stats: dict[str, dict[str, Any]] = {p.spec.id: {"ok": 0, "fail": 0, "ms": None} for p in self.providers}

    def _policy(self, provider: Provider, private: bool) -> tuple[bool, str]:
        spec = provider.spec
        if spec.cost == "paid":
            return False, "a pagamento: mai usato"
        if spec.kind == "remote":
            if private:
                return False, "richiesta privata: resta su questo computer"
            if not self.remote_enabled:
                return False, "motori online disattivati (intelligence.remote_enabled)"
            if not self.remote_free_verified:
                return False, "gratuità non confermata dal proprietario (intelligence.remote_free_verified)"
            if spec.cost != "free":
                return False, "costo non verificato"
        return True, "ammesso"

    def describe(self) -> list[dict[str, Any]]:
        out = []
        for p in self.providers:
            spec = p.spec
            allowed, reason = self._policy(p, private=False)
            available, status = p.status()
            out.append({
                "id": spec.id, "name": spec.name, "version": spec.version, "kind": spec.kind, "cost": spec.cost,
                "method": spec.method, "quality": spec.quality, "capabilities": sorted(spec.capabilities),
                "requirements": spec.requirements, "allowed": allowed, "available": available,
                "usable": allowed and available, "reason": reason if not allowed else status,
                "stats": dict(self._stats[spec.id]),
            })
        return out

    def plan(self, request: Request) -> tuple[str, list[Provider], list[dict[str, str]]]:
        task_type = request.task_type or classify(request.prompt)
        if task_type not in TASK_TYPES:
            raise RouterError(f"tipo di richiesta sconosciuto: {task_type} (ammessi: {', '.join(TASK_TYPES)})")
        chosen, rejected = [], []
        for p in self.providers:
            if task_type not in p.spec.capabilities:
                rejected.append({"id": p.spec.id, "reason": f"non gestisce '{task_type}'"})
                continue
            ok, reason = self._policy(p, request.private)
            if ok:
                ok, reason = p.status()
            if ok:
                chosen.append(p)
            else:
                rejected.append({"id": p.spec.id, "reason": reason})
        chosen.sort(key=self._score)
        return task_type, chosen[:MAX_ATTEMPTS], rejected

    def _score(self, p: Provider) -> tuple[float, int, float, float]:
        st = self._stats[p.spec.id]
        total = st["ok"] + st["fail"]
        reliability = st["ok"] / total if total else 1.0
        return (-p.spec.quality, 0 if p.spec.kind == "local" else 1, -reliability, st["ms"] or 1e9)

    def route(self, request: Request) -> dict[str, Any]:
        if not request.prompt.strip():
            raise RouterError("richiesta vuota")
        task_type, chosen, rejected = self.plan(request)
        if not chosen:
            reasons = "; ".join(f"{r['id']}: {r['reason']}" for r in rejected) or "nessun motore registrato"
            raise RouterError(f"nessun motore disponibile per '{task_type}' ({reasons})")
        attempts: list[dict[str, Any]] = []
        for p in chosen:
            start = self._clock()
            try:
                output = p.run(request, task_type)
                error = None
            except Exception as exc:  # EngineError or an unexpected bug in an adapter: try the next engine
                output, error = None, str(exc) if isinstance(exc, EngineError) else redact(f"{type(exc).__name__}: {exc}")
            ms = round((self._clock() - start) * 1000, 1)
            self._record(p, ok=error is None, ms=ms)
            if p.spec.kind == "remote" and self.audit is not None:  # data left this computer: always audited
                self.audit.record("system", "intelligence.remote_call", "ok" if error is None else "failed", 1,
                                  {"provider": p.spec.id, "task_type": task_type, "chars_sent": len(request.prompt)})
            attempts.append({"engine": p.spec.id, "ok": error is None, "ms": ms, "error": error})
            if error is None:
                return {"task_type": task_type, "engine": p.spec.id, "method": p.spec.method,
                        "verified": p.spec.method == "deterministico", "output": output,
                        "attempts": attempts, "rejected": rejected}
        raise RouterError("tutti i motori hanno fallito: " + "; ".join(f"{a['engine']}: {a['error']}" for a in attempts))

    def _record(self, p: Provider, *, ok: bool, ms: float) -> None:
        st = self._stats[p.spec.id]
        st["ok" if ok else "fail"] += 1
        if ok:
            st["ms"] = ms if st["ms"] is None else round(0.7 * st["ms"] + 0.3 * ms, 1)
