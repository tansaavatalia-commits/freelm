"""Online Engine adapter: free-tier models through the ``freelm`` library (in this repository / PyPI).

Disabled unless the owner sets both ``intelligence.remote_enabled`` and
``intelligence.remote_free_verified`` (after checking each provider's free terms,
see documentation/COST_POLICY.md). Keys come only from environment variables read
by freelm; GÉNESIS never stores them. Keyless public endpoints are never used.
"""

from __future__ import annotations

import time
from types import ModuleType
from typing import Any, Callable

from ..security.redact import redact
from .base import EngineError, Provider, ProviderSpec, Request

STATUS_TTL = 60.0


class FreelmProvider(Provider):
    def __init__(self, factory: Callable[[], Any] | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        self._factory = factory
        self._client: Any = None
        self._clock = clock
        self._status: tuple[float, tuple[bool, str]] | None = None

    @property
    def spec(self) -> ProviderSpec:  # type: ignore[override]
        module = _freelm()
        return ProviderSpec(
            id="freelm", name="freelm: livelli gratuiti (OpenRouter :free, Gemini, Groq, …)",
            version=getattr(module, "__version__", "non installato") if module else "non installato",
            kind="remote", capabilities=frozenset({"chat", "code", "reasoning", "math", "text.stats"}),
            cost="free", quality=3, method="modello esterno",
            requirements="libreria freelm (pip install freelm) e chiavi API gratuite nelle variabili d'ambiente",
        )

    def status(self) -> tuple[bool, str]:
        now = self._clock()
        if self._status and now - self._status[0] < STATUS_TTL:
            return self._status[1]
        result = self._check()
        self._status = (now, result)
        return result

    def _check(self) -> tuple[bool, str]:
        module = _freelm()
        if module is None:
            return False, "libreria freelm non installata"
        try:
            providers = module.providers_from_env(keyless=False)
        except Exception as exc:
            return False, redact(f"configurazione non valida: {exc}")
        if not providers:
            return False, "nessuna chiave API nelle variabili d'ambiente"
        return True, f"{len(providers)} provider con chiave"

    def run(self, request: Request, task_type: str) -> str:
        module = _freelm()
        if module is None:
            raise EngineError("libreria freelm non installata")
        try:
            if self._client is None:
                self._client = self._factory() if self._factory else module.FreeLLM.from_env(keyless=False)
            text = self._client.text(request.prompt)
        except Exception as exc:
            raise EngineError(redact(f"{type(exc).__name__}: {exc}")) from exc
        if not isinstance(text, str) or not text.strip():
            raise EngineError("risposta vuota")
        return text.strip()


def _freelm() -> ModuleType | None:
    try:
        import freelm
    except ImportError:
        return None
    return freelm
