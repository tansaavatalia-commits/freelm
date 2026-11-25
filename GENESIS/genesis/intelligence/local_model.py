"""Local model provider: an OpenAI-compatible server running on THIS computer (llama.cpp server,
Ollama, LM Studio...). GÉNESIS does not install or download anything: the owner runs the server.

* only loopback endpoints are accepted (the data never leaves the PC: private requests may use it);
* disabled on profiles without local models (lite-4gb) unless the owner sets allow_on_lite;
* it is an external model, not GÉNESIS's own intelligence: answers are "not verified".
"""

from __future__ import annotations

import ipaddress
import json
import urllib.error
import urllib.request
from typing import Any, Mapping
from urllib.parse import urlsplit

from ..security.redact import redact
from .base import EngineError, Provider, ProviderSpec, Request

LOOPBACK_NAMES = {"localhost"}


def is_loopback(url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    if parts.hostname in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(parts.hostname).is_loopback
    except ValueError:
        return False


class LocalModelProvider(Provider):
    def __init__(self, config: Mapping[str, Any] | None, profile_allows: bool) -> None:
        self.config = dict(config or {})
        self.profile_allows = profile_allows

    @property
    def spec(self) -> ProviderSpec:  # type: ignore[override]
        model = self.config.get("model", "non configurato")
        return ProviderSpec("local-model", f"Modello locale ({model})", str(model), "local",
                            frozenset({"chat", "code", "reasoning"}), "free", 2, "modello locale",
                            "un server compatibile OpenAI su questo PC (es. llama.cpp, Ollama) in [models.local]")

    def status(self) -> tuple[bool, str]:
        if not self.config:
            return False, "nessun modello locale configurato ([models.local] in genesis.toml)"
        if not is_loopback(self.config["endpoint"]):
            return False, "endpoint rifiutato: solo indirizzi locali (127.0.0.1, localhost)"
        if not self.profile_allows and not self.config.get("allow_on_lite", False):
            return False, "profilo senza modelli locali (lite-4gb): impostare allow_on_lite = true per forzare"
        return True, f"pronto su {self.config['endpoint']}"

    def run(self, request: Request, task_type: str) -> str:
        ok, reason = self.status()
        if not ok:
            raise EngineError(reason)
        body = json.dumps({"model": self.config["model"], "temperature": 0.2, "max_tokens": 512,
                           "messages": [{"role": "user", "content": request.prompt}]}).encode("utf-8")
        url = self.config["endpoint"].rstrip("/") + "/chat/completions"
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # loopback: never via a proxy
        try:
            with opener.open(req, timeout=self.config.get("timeout", 120)) as resp:
                data = json.loads(resp.read(2_000_000).decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise EngineError(redact(f"modello locale non raggiungibile: {exc}")) from exc
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise EngineError("risposta del modello locale in formato inatteso") from exc
        if not isinstance(text, str) or not text.strip():
            raise EngineError("risposta vuota")
        return text.strip()
