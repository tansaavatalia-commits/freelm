"""Catalog of open-weight models. Figures come from the authors' model cards as known when the entry
was written; they are NOT verified at runtime. Check license and size on the model card before use.
Owners can add entries as JSON files in <home>/models/*.json."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..errors import GenesisError

ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,60}$")
CHECK_NOTE = "NON VERIFICATO al 2026-11-25: verificare licenza e dimensioni sulla scheda del modello prima dell'uso"


@dataclass(frozen=True)
class ModelCard:
    id: str
    family: str
    params_b: float
    license: str
    context: int
    source: str
    notes: str = ""
    builtin: bool = True
    verification: str = CHECK_NOTE


BUILTIN: tuple[ModelCard, ...] = (
    ModelCard("smollm2-360m-instruct", "SmolLM2", 0.36, "Apache-2.0", 8192,
              "https://huggingface.co/HuggingFaceTB/SmolLM2-360M-Instruct", "molto piccolo, soprattutto inglese"),
    ModelCard("qwen2.5-0.5b-instruct", "Qwen2.5", 0.49, "Apache-2.0", 32768,
              "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct", "multilingue"),
    ModelCard("tinyllama-1.1b-chat", "TinyLlama", 1.1, "Apache-2.0", 2048,
              "https://huggingface.co/TinyLlama/TinyLlama-1.1B-Chat-v1.0", "contesto breve"),
    ModelCard("llama-3.2-1b-instruct", "Llama 3.2", 1.24, "Llama 3.2 Community License", 131072,
              "https://huggingface.co/meta-llama/Llama-3.2-1B-Instruct", "licenza con condizioni d'uso proprie"),
    ModelCard("qwen2.5-1.5b-instruct", "Qwen2.5", 1.54, "Apache-2.0", 32768,
              "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct", "multilingue"),
    ModelCard("smollm2-1.7b-instruct", "SmolLM2", 1.71, "Apache-2.0", 8192,
              "https://huggingface.co/HuggingFaceTB/SmolLM2-1.7B-Instruct", "soprattutto inglese"),
    ModelCard("gemma-2-2b-it", "Gemma 2", 2.61, "Gemma Terms of Use", 8192,
              "https://huggingface.co/google/gemma-2-2b-it", "termini d'uso propri"),
    ModelCard("qwen2.5-3b-instruct", "Qwen2.5", 3.09, "Qwen Research License (non Apache)", 32768,
              "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct", "licenza di ricerca: verificare l'uso consentito"),
    ModelCard("llama-3.2-3b-instruct", "Llama 3.2", 3.21, "Llama 3.2 Community License", 131072,
              "https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct", "licenza con condizioni d'uso proprie"),
    ModelCard("phi-3.5-mini-instruct", "Phi-3.5", 3.82, "MIT", 131072,
              "https://huggingface.co/microsoft/Phi-3.5-mini-instruct", ""),
    ModelCard("mistral-7b-instruct-v0.3", "Mistral", 7.25, "Apache-2.0", 32768,
              "https://huggingface.co/mistralai/Mistral-7B-Instruct-v0.3", ""),
    ModelCard("qwen2.5-7b-instruct", "Qwen2.5", 7.62, "Apache-2.0", 32768,
              "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct", "multilingue"),
)


def load_catalog(home: Path) -> dict[str, ModelCard]:
    cards = {c.id: c for c in BUILTIN}
    folder = Path(home) / "models"
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise GenesisError(f"{path}: scheda illeggibile ({exc})") from exc
        required = {"id", "family", "params_b", "license", "context", "source"}
        if not isinstance(raw, dict) or not required <= set(raw) or set(raw) - required - {"notes"}:
            raise GenesisError(f"{path}: campi richiesti {sorted(required)} (facoltativo: notes)")
        if not isinstance(raw["id"], str) or not ID_RE.match(raw["id"]) or raw["id"] in cards:
            raise GenesisError(f"{path}: id non valido o già presente")
        if not isinstance(raw["params_b"], (int, float)) or not 0.01 <= raw["params_b"] <= 2000:
            raise GenesisError(f"{path}: params_b (miliardi di parametri) tra 0.01 e 2000")
        if not isinstance(raw["context"], int) or raw["context"] < 128:
            raise GenesisError(f"{path}: context deve essere un intero >= 128")
        cards[raw["id"]] = ModelCard(raw["id"], str(raw["family"]), float(raw["params_b"]), str(raw["license"]),
                                     raw["context"], str(raw["source"]), str(raw.get("notes", "")), builtin=False,
                                     verification="aggiunto dal proprietario")
    return cards


def card_dict(card: ModelCard) -> dict[str, Any]:
    return asdict(card)
