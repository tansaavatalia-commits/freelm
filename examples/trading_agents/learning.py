"""Aprendizaje: en quién confiar (Coordinator) y qué señales tienen ventaja real (Calibrator).

Coordinator: algoritmo *Hedge* (pesos multiplicativos, Freund & Schapire) con
*fixed share* (Herbster & Warmuth) y pesos separados por **régimen de mercado**.
Tras cada vela, cada agente recibe ``value * retorno / volatilidad``: acertar
con convicción suma, fallar con convicción resta, ``w *= exp(eta * r)``. La
mezcla uniforme ``alpha`` deja que un agente castigado se recupere cuando el
mercado cambia. Se usa en dos niveles: dentro de cada equipo (agentes) y en
el consejo (equipos).

Calibrator: el filtro anti-"señales sin sentido". Cada señal candidata se
opera **en la sombra** (con el mismo stop y objetivo que una real, y
comisiones) aunque no se ejecute. El resultado, en múltiplos de riesgo R, se
acumula por (régimen, fuerza, acuerdo). Solo se permite operar de verdad un
tipo de señal cuando su esperanza neta está demostrada con suficientes muestras.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from agents import Signal
from features import Features

REGIMES = ("tendencia", "lateral", "volátil")


def detect_regime(f: Features, lookback: int = 30) -> str:
    closes = f.closes
    if len(closes) <= lookback:
        return "lateral"
    tail = closes[-lookback - 1:]
    path = sum(abs(tail[i] - tail[i - 1]) for i in range(1, len(tail))) or 1e-12
    er = abs(tail[-1] - tail[0]) / path  # efficiency ratio de Kaufman: 1 = tendencia limpia, 0 = ruido
    if len(closes) > 2 * lookback and f.vol(lookback) > 1.5 * f.vol(len(closes) - 1):
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
            for a in [a for a in w if a not in self.agents]:
                del w[a]
            self._normalize(reg)
        for a in self.agents:
            self.stats.setdefault(a, AgentStats())

    def combine(self, signals: Sequence[Signal], regime: str) -> Tuple[float, float]:
        """Devuelve (decisión en [-1, 1], acuerdo ponderado en [0, 1])."""
        w = self.weights[regime]
        num = den = 0.0
        for s in signals:
            wi = w.get(s.agent, 0.0)
            num += wi * s.value
            den += wi
        score = max(-1.0, min(1.0, num / (den or 1.0)))
        if score == 0:
            return 0.0, 0.0
        agree = tot = 0.0
        for s in signals:
            wi = w.get(s.agent, 0.0) * s.confidence
            tot += wi
            if s.score * score > 0:
                agree += wi
        return score, agree / (tot or 1.0)

    def learn(self, signals: Sequence[Signal], regime: str, ret: float, vol: float) -> None:
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

    # Versiones por índice (orden = self.agents): sin objetos Signal, para la
    # caché de señales del optimizador, que repite miles de simulaciones.
    # ``values`` = score * confidence de cada agente (precalculado en la caché).
    def combine_arrays(self, scores: Sequence[float], confs: Sequence[float], regime: str,
                       values: Optional[Sequence[float]] = None) -> Tuple[float, float]:
        w = self.weights[regime]
        ws = [w[a] for a in self.agents]
        if values is None:
            values = [s * c for s, c in zip(scores, confs)]
        num = sum([wi * v for wi, v in zip(ws, values)])
        score = num / (sum(ws) or 1.0)
        score = 1.0 if score > 1.0 else -1.0 if score < -1.0 else score
        if score == 0:
            return 0.0, 0.0
        wc = [wi * c for wi, c in zip(ws, confs)]
        tot = sum(wc)
        agree = sum([x for x, s in zip(wc, scores) if s * score > 0])
        return score, agree / (tot or 1.0)

    def learn_arrays(self, scores: Sequence[float], confs: Sequence[float], regime: str, ret: float,
                     vol: float, track: bool = True, values: Optional[Sequence[float]] = None) -> None:
        """Hedge + fixed share en una sola pasada (sin dos bucles de normalización)."""
        w = self.weights[regime]
        agents = self.agents
        if values is None:
            values = [s * c for s, c in zip(scores, confs)]
        m = ret / (vol if vol > 1e-4 else 1e-4)
        eta, exp = self.eta, math.exp
        rewards = [v * m for v in values]
        rewards = [3.0 if r > 3.0 else -3.0 if r < -3.0 else r for r in rewards]
        new = [w[a] * exp(eta * r) for a, r in zip(agents, rewards)]
        n = len(new)
        k, b = (1 - self.alpha) / (sum(new) or 1.0), self.alpha / n
        for a, x in zip(agents, new):
            w[a] = x * k + b
        if track:
            up = ret > 0
            for a, s, c, r in zip(agents, scores, confs, rewards):
                st = self.stats[a]
                if c > 0 and s != 0:
                    st.n += 1
                    st.hits += (s > 0) == up
                st.reward += r
        self.updates += 1

    def _normalize(self, regime: str) -> None:
        w = self.weights[regime]
        tot = sum(w.values()) or 1.0
        for a in w:
            w[a] /= tot

    def ranking(self, regime: str) -> List[tuple]:
        return sorted(self.weights[regime].items(), key=lambda kv: -kv[1])

    def to_dict(self) -> dict:
        return {"eta": self.eta, "alpha": self.alpha, "updates": self.updates, "weights": self.weights,
                "stats": {a: vars(s) for a, s in self.stats.items()}}

    @classmethod
    def from_dict(cls, d: Optional[dict], agents: List[str], **kw: float) -> "Coordinator":
        if not d:
            return cls(agents, **kw)
        stats = {a: AgentStats(**s) for a, s in d.get("stats", {}).items() if a in agents}
        weights = {reg: dict(ws) for reg, ws in d.get("weights", {}).items()}
        return cls(agents, eta=d.get("eta", kw.get("eta", 0.5)), alpha=d.get("alpha", kw.get("alpha", 0.02)),
                   weights=weights, stats=stats, updates=d.get("updates", 0))


def bucket(regime: str, strength: float, agreement: float) -> str:
    s = 0 if strength < 0.3 else 1 if strength < 0.45 else 2
    a = "alto" if agreement >= 0.75 else "medio"
    return f"{regime}|f{s}|{a}"


@dataclass
class Shadow:
    key: str
    entry: float
    stop: float
    target: float
    expires: int  # velas restantes


@dataclass
class Calibrator:
    """Esperanza neta (en R) de cada tipo de señal, medida en la sombra."""
    min_samples: int = 40
    min_edge: float = 0.15  # exige al menos +0.15R netos de media
    horizon: int = 48
    fee: float = 0.001
    results: Dict[str, List[float]] = field(default_factory=dict)  # key -> [n, suma_R, suma_R2, ganadas]
    open: Dict[str, List[Shadow]] = field(default_factory=dict)  # por símbolo

    def record(self, symbol: str, key: str, entry: float, stop: float, target: float) -> None:
        book = self.open.setdefault(symbol, [])
        if len(book) < 200:
            book.append(Shadow(key, entry, stop, target, self.horizon))

    def update(self, symbol: str, high: float, low: float, close: float) -> None:
        keep = []
        for s in self.open.get(symbol, []):
            s.expires -= 1
            risk = s.entry - s.stop
            if low <= s.stop:
                exit_px = s.stop
            elif high >= s.target:
                exit_px = s.target
            elif s.expires <= 0:
                exit_px = close
            else:
                keep.append(s)
                continue
            r = (exit_px - s.entry - self.fee * (s.entry + exit_px)) / risk
            st = self.results.setdefault(s.key, [0, 0.0, 0.0, 0])
            st[0] += 1
            st[1] += r
            st[2] += r * r
            st[3] += int(r > 0)
        self.open[symbol] = keep

    def edge(self, key: str) -> Tuple[float, int]:
        """(esperanza conservadora en R, muestras). Resta un error estándar: solo
        cuenta la ventaja que sobrevive a la mala suerte."""
        st = self.results.get(key)
        if not st or st[0] < 2:
            return 0.0, int(st[0]) if st else 0
        n, s, s2 = st[0], st[1], st[2]
        mean = s / n
        sd = math.sqrt(max(0.0, s2 / n - mean * mean))
        return mean - sd / math.sqrt(n), int(n)

    def approved(self, key: str) -> Tuple[bool, str]:
        e, n = self.edge(key)
        if n < self.min_samples:
            return False, f"sin historial suficiente ({n}/{self.min_samples})"
        if e < self.min_edge:
            return False, f"sin ventaja demostrada ({e:+.2f}R)"
        return True, f"ventaja {e:+.2f}R en {n} casos"

    def table(self) -> List[tuple]:
        rows = []
        for k, st in self.results.items():
            e, n = self.edge(k)
            rows.append((k, n, st[1] / st[0], st[3] / st[0], e))
        return sorted(rows, key=lambda r: -r[4])

    def to_dict(self) -> dict:
        return {"results": self.results}

    @classmethod
    def from_dict(cls, d: Optional[dict], **kw: float) -> "Calibrator":
        c = cls(**kw)  # type: ignore[arg-type]
        if d:
            c.results = {k: list(v) for k, v in d.get("results", {}).items()}
        return c
