"""El aprendizaje: un coordinador que aprende en línea cuánto fiarse de cada agente.

Algoritmo: *Hedge* (pesos multiplicativos, Freund & Schapire) con *fixed share*
(Herbster & Warmuth), y pesos separados por **régimen de mercado**:

1. En cada vela, cada agente da su ``Signal``.
2. La decisión es la media ponderada de ``score * confidence``.
3. Cuando llega la vela siguiente se conoce el retorno real ``r``. La
   recompensa de cada agente es ``value * r / volatilidad`` (acierta la
   dirección y con convicción → gana; se equivoca con convicción → pierde).
4. ``w_i *= exp(eta * recompensa_i)`` y luego se mezcla una fracción ``alpha``
   uniforme: así un agente castigado puede recuperarse cuando el mercado
   cambia (lo que en finanzas pasa siempre).

El régimen se detecta con el *efficiency ratio* de Kaufman: en tendencia ganan
peso los seguidores de tendencia; en lateral, los de reversión. Nadie lo
programa: lo descubre el propio bot.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from agents import Signal
from market import Candle

REGIMES = ("tendencia", "lateral", "volátil")


def detect_regime(candles: Sequence[Candle], lookback: int = 30) -> str:
    if len(candles) <= lookback:
        return "lateral"
    all_closes = [c.close for c in candles]
    closes = all_closes[-lookback - 1:]
    path = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes))) or 1e-12
    er = abs(closes[-1] - closes[0]) / path  # 1 = tendencia perfecta, 0 = ruido

    def _vol(xs: Sequence[float]) -> float:
        rets = [math.log(xs[i] / xs[i - 1]) for i in range(1, len(xs))]
        return math.sqrt(sum(x * x for x in rets) / len(rets))

    # volátil = la volatilidad reciente supera 1.5x la de toda la ventana
    if len(all_closes) > 2 * lookback and _vol(closes) > 1.5 * _vol(all_closes):
        return "volátil"
    return "tendencia" if er > 0.3 else "lateral"


@dataclass
class AgentStats:
    n: int = 0
    hits: int = 0
    reward: float = 0.0

    @property
    def hit_rate(self) -> float:
        return self.hits / self.n if self.n else 0.0


@dataclass
class Coordinator:
    agents: List[str]
    eta: float = 0.5
    alpha: float = 0.02
    weights: Dict[str, Dict[str, float]] = field(default_factory=dict)
    stats: Dict[str, AgentStats] = field(default_factory=dict)
    updates: int = 0

    def __post_init__(self) -> None:
        for reg in REGIMES:
            w = self.weights.setdefault(reg, {})
            for a in self.agents:
                w.setdefault(a, 1.0 / len(self.agents))
            self._normalize(reg)
        for a in self.agents:
            self.stats.setdefault(a, AgentStats())

    # -- decisión -----------------------------------------------------------
    def combine(self, signals: Sequence[Signal], regime: str) -> float:
        w = self.weights[regime]
        num = sum(w.get(s.agent, 0.0) * s.value for s in signals)
        den = sum(w.get(s.agent, 0.0) for s in signals) or 1.0
        return max(-1.0, min(1.0, num / den))

    # -- aprendizaje --------------------------------------------------------
    def learn(self, signals: Sequence[Signal], regime: str, ret: float, vol: float) -> None:
        """``ret``: retorno logarítmico realizado; ``vol``: volatilidad típica por vela."""
        scale = max(vol, 1e-4)
        w = self.weights[regime]
        for s in signals:
            if s.agent not in w:
                continue
            reward = max(-3.0, min(3.0, s.value * ret / scale))
            w[s.agent] *= math.exp(self.eta * reward)
            st = self.stats[s.agent]
            if s.confidence > 0 and s.score != 0:
                st.n += 1
                st.hits += int((s.score > 0) == (ret > 0))
            st.reward += reward
        self._normalize(regime)
        n = len(w)
        for a in w:
            w[a] = (1 - self.alpha) * w[a] + self.alpha / n
        self.updates += 1

    def _normalize(self, regime: str) -> None:
        w = self.weights[regime]
        tot = sum(w.values()) or 1.0
        for a in w:
            w[a] /= tot

    def ranking(self, regime: str) -> List[tuple]:
        return sorted(self.weights[regime].items(), key=lambda kv: -kv[1])

    # -- memoria ------------------------------------------------------------
    def to_dict(self) -> dict:
        return {"eta": self.eta, "alpha": self.alpha, "updates": self.updates, "weights": self.weights,
                "stats": {a: vars(s) for a, s in self.stats.items()}}

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(self.to_dict(), fh, indent=2, ensure_ascii=False)
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: Optional[str], agents: List[str], **kw: float) -> "Coordinator":
        if path and os.path.exists(path):
            with open(path) as fh:
                d = json.load(fh)
            weights = {reg: {a: v for a, v in ws.items() if a in agents} for reg, ws in d.get("weights", {}).items()}
            stats = {a: AgentStats(**s) for a, s in d.get("stats", {}).items() if a in agents}
            return cls(agents, eta=d.get("eta", kw.get("eta", 0.5)), alpha=d.get("alpha", kw.get("alpha", 0.02)),
                       weights=weights, stats=stats, updates=d.get("updates", 0))
        return cls(agents, **kw)
