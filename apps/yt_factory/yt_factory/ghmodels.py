"""GitHub Models come provider in più per freelm: LLM gratuiti e forti (GPT-4.1, Llama 3.3 70B, DeepSeek V3...).

Dentro GitHub Actions basta il token automatico del repository (permesso `models: read`), passato come
GITHUB_MODELS_TOKEN: nessuna chiave da creare. Fuori da Actions va bene un token GitHub personale con
permesso "Models". Il provider vive nell'app, non nella libreria freelm (che resta identica in Python e TS).

Limiti del piano gratuito (docs.github.com/github-models, verificati 2026-11): per modello ~10-15 richieste/minuto
e 50-150 al giorno; max ~8000 token in ingresso e 4000 in uscita per richiesta. Più modelli = più quota totale,
e freelm passa al successivo quando uno è esaurito.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from freelm.providers.base import Provider
from freelm.registry import ModelSpec

MAX_OUTPUT = 4000


class GitHubModels(Provider):
    name = "github"
    base_url = "https://models.github.ai/inference"
    TIERS: Dict[str, Dict[str, Any]] = {"free": {"rpm": 10, "rpd": None}}
    DEFAULT_MODELS = [
        ModelSpec("openai/gpt-4.1", ("chat", "large", "tools"), ctx=8000, priority=0),
        ModelSpec("deepseek/DeepSeek-V3-0324", ("chat", "large"), ctx=8000, priority=1),
        ModelSpec("meta/Llama-3.3-70B-Instruct", ("chat", "large", "tools"), ctx=8000, priority=2),
        ModelSpec("openai/gpt-4.1-mini", ("chat", "fast", "small", "tools"), ctx=8000, priority=3),
        ModelSpec("openai/gpt-4o-mini", ("chat", "fast", "small", "tools"), ctx=8000, priority=4),
    ]

    def rate_limit_scope(self, body: str) -> str:
        return "model"  # i limiti di GitHub Models sono per modello

    def adapt_payload(self, body: Dict[str, Any]) -> Dict[str, Any]:
        body = dict(body)
        if int(body.get("max_tokens") or 0) > MAX_OUTPUT:  # oltre il limite la richiesta verrebbe rifiutata
            body["max_tokens"] = MAX_OUTPUT
        return body


def github_models_providers() -> List[Provider]:
    token: Optional[str] = os.environ.get("GITHUB_MODELS_TOKEN")
    return [GitHubModels(token)] if token else []
