"""Online Engine adapter: free-tier models through the ``freelm`` library (in this repository / PyPI).

Disabled unless the owner sets both ``intelligence.remote_enabled`` and
``intelligence.remote_free_verified`` (after checking each provider's free terms,
see documentation/COST_POLICY.md). Keys come only from environment variables read
by freelm; GÉNESIS never stores them. Keyless public endpoints are never used.
"""

from __future__ import annotations

import time
from types import ModuleType
from typing import Any, Callable, Iterator

from ..security.redact import redact
from .base import EngineError, Provider, ProviderSpec, Request

STATUS_TTL = 60.0
# Only services whose free terms were verified (COST_POLICY.md) and whose freelm guard is free-only.
ALLOWED_SERVICES = ("openrouter",)


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
            id="freelm", name="OpenRouter, solo modelli gratuiti :free (tramite freelm)",
            version=getattr(module, "__version__", "non installato") if module else "non installato",
            kind="remote", capabilities=frozenset({"chat", "code", "reasoning", "math", "text.stats"}),
            cost="free", quality=3, method="modello esterno",
            requirements="libreria freelm e variabile d'ambiente OPENROUTER_API_KEY (chiave gratuita)",
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
            providers = _allowed(module)
        except Exception as exc:
            return False, redact(f"configurazione non valida: {exc}")
        if not providers:
            return False, "nessuna chiave OpenRouter (variabile OPENROUTER_API_KEY)"
        return True, "OpenRouter pronto (solo modelli gratuiti)"

    def _ensure_client(self) -> Any:
        if self._client is None:
            if self._factory:
                self._client = self._factory()
            else:
                module = _freelm()
                if module is None:
                    raise EngineError("libreria freelm non installata")
                providers = _allowed(module)
                if not providers:
                    raise EngineError("nessuna chiave OpenRouter (variabile OPENROUTER_API_KEY)")
                self._client = module.FreeLLM(providers=providers)
        return self._client

    def run(self, request: Request, task_type: str) -> str:
        if self._factory is None and _freelm() is None:
            raise EngineError("libreria freelm non installata")
        try:
            text = self._ensure_client().text(request.prompt)
        except EngineError:
            raise
        except Exception as exc:
            raise EngineError(redact(f"{type(exc).__name__}: {exc}")) from exc
        if not isinstance(text, str) or not text.strip():
            raise EngineError("risposta vuota")
        return text.strip()

    def stream(self, messages: list[dict[str, str]]) -> Iterator[str]:
        """Text deltas for a whole conversation (OpenAI-style messages). freelm fails over between free
        models before the first token only. Errors surface as EngineError, with secrets redacted."""
        try:
            for delta in self._ensure_client().stream(messages):
                if isinstance(delta, str) and delta:
                    yield delta
        except EngineError:
            raise
        except Exception as exc:
            raise EngineError(redact(f"{type(exc).__name__}: {exc}")) from exc


def _allowed(module: ModuleType) -> list[Any]:
    """Providers from the environment, restricted to verified services with freelm's free-only guard on."""
    return [p for p in module.providers_from_env(keyless=False)
            if getattr(p, "name", "") in ALLOWED_SERVICES and getattr(p, "free_only", False)]


def _freelm() -> ModuleType | None:
    try:
        import freelm
    except ImportError:
        return None
    return freelm
