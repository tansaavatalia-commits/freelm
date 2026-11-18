"""Cervello finto e deterministico: prova l'intera catena (render incluso) senza rete né LLM."""
from __future__ import annotations

import itertools
from typing import Any, Dict


class OfflineBrain:
    def __init__(self) -> None:
        self.calls = 0
        self._n = itertools.count(1)

    async def ask_json(self, system: str, user: str, *, schema: str, max_tokens: int = 0) -> Dict[str, Any]:
        self.calls += 1
        n = next(self._n)
        if '"hot_topics"' in schema:
            return {"hot_topics": ["memoria", "sonno"], "viral_patterns": ["3 cose che"], "hook_formulas": ["Non crederai che..."],
                    "avoid": [], "data_quality": "nessuna"}
        if '"ideas"' in schema:
            return {"ideas": [{"topic": f"{['Sonno','Memoria','Api','Polpi','Vulcani','Marte','Sale','Luce','Suono','Neve'][i]} {n}: fatto sorprendente", "angle": "test",
                               "hook": "Il tuo cervello ti inganna ogni giorno", "why_viral": "test", "viral_score": 9 - i}
                              for i in range(8)]}
        if '"chapters"' in schema:
            return {"title_idea": "Video lungo di prova", "hook": "Ecco la storia.",
                    "chapters": [{"title": f"Capitolo {i}", "points": ["a"]} for i in range(1, 4)]}
        if '"scenes"' in schema:
            return {"title_idea": "Il cervello ti inganna", "cta": "Seguimi per altre curiosità.", "scenes": [
                {"text": t, "visual": "brain", "on_screen": o} for t, o in [
                    ("Il tuo cervello ti inganna ogni singolo giorno.", "TI INGANNA"),
                    ("Non vedi mai il tuo naso, eppure è sempre lì.", "IL NASO"),
                    ("Il cervello lo cancella perché è un'informazione inutile.", "CANCELLATO"),
                    ("Lo stesso fa con il rumore del frigorifero.", "IL FRIGO"),
                    ("Te ne accorgi solo quando si spegne.", "SILENZIO"),
                    ("Ora ci stai pensando, vero?", "ORA LO VEDI")]]}
        if '"verdict"' in schema:
            return {"score": 8, "hook_strength": 8, "originality": 8, "factual_risk": "basso", "policy_issues": [],
                    "verdict": "approve", "fixes": []}
        if '"thumbnail_text"' in schema:
            return {"title": f"Il tuo cervello ti inganna (prova {n})", "description": "Un fatto vero sul cervello.",
                    "tags": ["cervello", "curiosità"], "hashtags": ["#curiosità"], "thumbnail_text": "TI INGANNA",
                    "pinned_comment": "Tu lo sapevi?"}
        if '"lessons"' in schema:
            return {"winners": [], "losers": [], "lessons": ["hook con domanda diretta"]}
        if '"priorities"' in schema:
            return {"status": "canale nuovo", "eta": "n/d", "priorities": ["pubblicare con costanza"], "extra_revenue": []}
        return {}

    async def aclose(self) -> None:
        pass
