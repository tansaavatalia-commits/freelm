"""Cervello finto e deterministico: prova l'intera catena (render incluso) senza rete né LLM."""
from __future__ import annotations

import itertools
from typing import Any, Dict

TOPICS = ["Sonno", "Memoria", "Api", "Polpi", "Vulcani", "Marte", "Sale", "Luce", "Suono", "Neve", "Ghiaccio", "Rame"]
LINES = [("Il tuo cervello ti inganna ogni singolo giorno.", "TI INGANNA"),
         ("Non vedi mai il tuo naso, eppure è sempre lì.", "IL NASO"),
         ("Il cervello lo cancella perché è un'informazione inutile.", "CANCELLATO"),
         ("Lo stesso fa con il rumore del frigorifero.", "IL FRIGO"),
         ("Te ne accorgi solo quando si spegne.", "SILENZIO"),
         ("Ora ci stai pensando, vero?", "ORA LO VEDI")]


class OfflineBrain:
    def __init__(self) -> None:
        self.calls = 0
        self._n = itertools.count(1)

    async def ask_json(self, system: str, user: str, *, schema: str, max_tokens: int = 0,
                       model: Any = None, temperature: float = 0.0) -> Dict[str, Any]:
        self.calls += 1
        n = next(self._n)
        if '"blueprints"' in schema:
            return {"blueprints": [{"reference": "x", "demand": "stupore", "how_to_beat_it": "fatto migliore"}],
                    "hot_topics": ["memoria"], "saturated": [], "data_quality": "none"}
        if '"gaps"' in schema:
            return {"questions": ["perché succede?"], "desires": [], "frustrations": [], "gaps": ["spiegazione chiara"]}
        if '"concepts"' in schema:
            return {"concepts": [{"topic": f"{TOPICS[(n + i) % len(TOPICS)]} {n}-{i}: fatto sorprendente",
                                  "upgrade": "più chiaro", "viral_score": 9 - i} for i in range(8)]}
        if '"hooks"' in schema:
            return {"hooks": ["Il tuo cervello ti inganna ogni giorno", "Non vedi il tuo naso", "Ecco un segreto"]}
        if '"scores"' in schema:
            return {"scores": [9, 6, 5], "best": 0, "why": "test"}
        if '"chapters"' in schema:
            return {"title_idea": "Video lungo di prova", "hook": "Ecco la storia.",
                    "chapters": [{"title": f"Capitolo {i}", "points": ["a"]} for i in range(1, 4)]}
        if '"scenes"' in schema:
            return {"title_idea": "Il cervello ti inganna", "cta": "Seguimi per altre curiosità.",
                    "scenes": [{"text": t, "on_screen": o} for t, o in LINES]}
        if '"claims"' in schema:
            return {"claims": []}
        if '"results"' in schema:
            return {"results": []}
        if '"verdict"' in schema:
            return {"score": 8, "factual_risk": "low", "policy_issues": [], "verdict": "approve", "fixes": []}
        if '"shots"' in schema:
            return {"shots": [{"scene": i, "image_prompt": "brain", "stock_query": "brain"} for i in range(6)]}
        if '"thumbnail_text"' in schema:
            return {"titles": ["a", "b", "c"], "title": f"Il tuo cervello ti inganna (prova {n})",
                    "description": "Un fatto vero sul cervello.", "tags": ["cervello", "curiosità"],
                    "hashtags": ["#curiosità"], "thumbnail_text": "TI INGANNA", "pinned_comment": "Tu lo sapevi?"}
        if '"lessons"' in schema:
            return {"winners": [], "losers": [], "lessons": ["hook con domanda diretta"]}
        if '"priorities"' in schema:
            return {"status": "canale nuovo", "eta": "n/d", "priorities": ["pubblicare con costanza"], "extra_revenue": []}
        return {}

    async def aclose(self) -> None:
        pass
