"""Genesis Research Engine: extractive summaries and keywords computed by an algorithm (no model).
Web pages are read through the web.fetch tool (permission-checked, untrusted data); the source is recorded."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Any, Callable

from .. import __version__
from ..core.clock import utcnow
from .base import Component, EngineOpError, GenesisEngine, Operation, text_arg

STOPWORDS = set("""
a ad al alla alle allo agli ai anche che chi con come da dal dalla dalle dei del della delle dello degli di e ed
è era essere fa gli ha hanno ho i il in io la le lo loro ma mi ne nel nella nelle nei negli no non o per più può
quale quando questo questa quello quella se si sia sono su sua suo sue suoi tra fra un una uno vi the of and to in
is it for on that this with as are was be by at or an from which their its not but have has had they you we
""".split())
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[a-zà-ÿ0-9]+", re.I)


def keywords(text: str, top: int = 10) -> list[dict[str, Any]]:
    words = [w.lower() for w in _WORD.findall(text)]
    counts = Counter(w for w in words if w not in STOPWORDS and len(w) > 2 and not w.isdigit())
    return [{"word": w, "count": c} for w, c in counts.most_common(top)]


def summarize(text: str, sentences: int = 3) -> dict[str, Any]:
    parts = [s.strip() for s in _SENTENCE.split(" ".join(text.split())) if len(s.strip()) > 20]
    if not parts:
        raise EngineOpError("testo troppo breve per un riassunto")
    freq = Counter(w.lower() for w in _WORD.findall(text) if w.lower() not in STOPWORDS and len(w) > 2)
    top = max(freq.values(), default=1)

    def score(s: str) -> float:
        ws = [w.lower() for w in _WORD.findall(s)]
        return sum(freq.get(w, 0) / top for w in ws) / (len(ws) ** 0.5 or 1)

    ranked = sorted(range(len(parts)), key=lambda i: (-score(parts[i]), i))[:max(1, sentences)]
    return {"summary": " ".join(parts[i] for i in sorted(ranked)), "sentences_total": len(parts),
            "keywords": keywords(text, 8), "method": "estrattivo per frequenza delle parole (nessun modello)"}


class ResearchEngine(GenesisEngine):
    id, name, version = "research", "Genesis Research Engine", f"1.0@{__version__}"
    description = "Riassunti estrattivi, parole chiave e tracciamento delle fonti."
    components = (
        Component("riassunto estrattivo", "algoritmo", "sceglie le frasi con le parole più frequenti"),
        Component("parole chiave", "algoritmo", "frequenze senza parole vuote (italiano e inglese)"),
        Component("web.fetch", "strumento", "lettura di pagine pubbliche con permessi; dati non fidati"),
    )
    operations = (
        Operation("summarize", 1, "riassume un testo, un file o una pagina web",
                  '{"text": "..."} | {"path": "..."} | {"url": "https://..."}, "sentences": 3'),
        Operation("keywords", 1, "parole chiave di un testo o di un file", '{"text": "..."} | {"path": "..."}'),
    )

    def __init__(self, read_file: Callable[[str], str] | None = None,
                 fetch: Callable[[str, str], dict[str, Any]] | None = None) -> None:
        self._read, self._fetch = read_file, fetch

    def _text(self, payload: dict[str, Any], principal: str) -> tuple[str, dict[str, Any]]:
        if "url" in payload:
            if self._fetch is None:
                raise EngineOpError("lettura del web non disponibile")
            page = self._fetch(str(payload["url"]), principal)
            text = page["text"]
            return text, {"url": page.get("url"), "retrieved_at": utcnow(), "untrusted": True,
                          "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
        if "path" in payload:
            if self._read is None:
                raise EngineOpError("lettura di file non disponibile")
            return self._read(str(payload["path"])), {"path": payload["path"]}
        return text_arg(payload), {}

    def run(self, op: str, payload: dict[str, Any], principal: str = "owner") -> Any:
        text, source = self._text(payload, principal)
        if op == "summarize":
            n = payload.get("sentences", 3)
            if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= 20:
                raise EngineOpError("sentences deve essere tra 1 e 20")
            return {**summarize(text, n), "source": source}
        if op == "keywords":
            return {"keywords": keywords(text, 15), "source": source}
        raise EngineOpError(f"operazione sconosciuta: {op}")
