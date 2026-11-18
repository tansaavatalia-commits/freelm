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
    # sumas para el IC (coeficiente de información, como alphalens): correlación entre
    # lo que dijo el agente (score x confianza) y el retorno siguiente normalizado por volatilidad
    ic_n: int = 0
    sx: float = 0.0
    sy: float = 0.0
    sxx: float = 0.0
    syy: float = 0.0
    sxy: float = 0.0

    @property
    def hit_rate(self) -> float:
        return self.hits / self.n if self.n else 0.0

    def add_ic(self, x: float, y: float) -> None:
        self.ic_n += 1
        self.sx += x
        self.sy += y
        self.sxx += x * x
        self.syy += y * y
        self.sxy += x * y

    @property
    def ic(self) -> float:
        n = self.ic_n
        if n < 3:
            return 0.0
        vx = self.sxx - self.sx * self.sx / n
        vy = self.syy - self.sy * self.sy / n
        if vx <= 1e-12 or vy <= 1e-12:
            return 0.0
        return (self.sxy - self.sx * self.sy / n) / math.sqrt(vx * vy)

    @property
    def ic_t(self) -> float:
        """Significación del IC: |t| > 2 = poco probable que sea casualidad."""
        ic, n = self.ic, self.ic_n
        return ic * math.sqrt(max(n - 2, 0) / max(1e-12, 1 - ic * ic)) if n > 2 else 0.0


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
            st.add_ic(s.value, max(-5.0, min(5.0, ret / scale)))
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
            y = max(-5.0, min(5.0, m))  # retorno siguiente en unidades de volatilidad
            for a, s, c, r, v in zip(agents, scores, confs, rewards, values):
                st = self.stats[a]
                if c > 0 and s != 0:
                    st.n += 1
                    st.hits += (s > 0) == up
                st.reward += r
                st.add_ic(v, y)
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
    age: int = 0  # velas transcurridas (para medir cuánto se solapan las muestras)
    wait: int = 0  # >0: orden límite de entrada aún sin ejecutar (velas que le quedan)


def wilson_lower(wins: float, n: float, z: float) -> float:
    """Cota inferior de Wilson de una proporción: la probabilidad de acierto que se
    puede garantizar con confianza ``z`` (z=3 ~ 99,9 %), no la que salió por suerte."""
    if n <= 0:
        return 0.0
    p = wins / n
    den = 1 + z * z / n
    centre = p + z * z / (2 * n)
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (centre - spread) / den)


def profile_key(key: str, target_atr: float) -> str:
    return f"{key}#t{target_atr:g}"


@dataclass
class Calibrator:
    """Mide en la sombra, por tipo de señal y por perfil de salida, la probabilidad de
    cerrar en positivo (tras comisiones y deslizamiento) y la esperanza en R.

    Cada señal candidata se «opera» sin dinero con varios objetivos a la vez
    (``record`` con ``profiles``). ``choose`` solo aprueba un perfil si:

    - la cota inferior de Wilson de su tasa de acierto es >= ``min_win_prob`` (77 %),
      con ``z`` corregido por pruebas múltiples (muchos tipos x perfiles = muchas
      oportunidades de que uno salga bien por azar);
    - las muestras se cuentan como **efectivas**: si las operaciones en la sombra se
      solapan en el tiempo, valen menos (n_eff = n x separación / duración media);
    - la esperanza conservadora (media - 1 error estándar) es positiva.

    Todo es punto-en-el-tiempo: una decisión solo usa sombras ya cerradas antes de ella.
    """
    min_samples: int = 40
    min_edge: float = 0.15  # (modo clásico) exige al menos +0.15R netos de media
    horizon: int = 48
    fee: float = 0.001
    sample_gap: int = 6     # velas entre dos sombras del mismo símbolo
    # costes por lado (fracción del precio). None = usar ``fee`` en ambos lados (modo clásico)
    entry_cost: Optional[float] = None
    target_cost: Optional[float] = None
    stop_cost: Optional[float] = None
    limit_offset: Optional[float] = None  # None = entrada a mercado; si no, límite a close - offset x ATR
    limit_wait: int = 2                   # velas que la orden límite espera antes de cancelarse
    missed: Dict[str, int] = field(default_factory=dict)  # órdenes límite que no se ejecutaron
    results: Dict[str, List[float]] = field(default_factory=dict)  # key -> [n, ΣR, ΣR², ganadas, Σduración]
    open: Dict[str, List[Shadow]] = field(default_factory=dict)  # por símbolo

    def record(self, symbol: str, key: str, entry: float, stop: float, target: float = 0.0,
               atr: Optional[float] = None, profiles: Sequence[float] = ()) -> None:
        """Sin ``profiles``: una sombra con ese stop/objetivo (clave = ``key``).
        Con ``profiles`` (múltiplos de ATR del objetivo) y ``atr``: una sombra por perfil."""
        book = self.open.setdefault(symbol, [])
        if len(book) >= 400:
            return
        if profiles and atr:
            if self.limit_offset is not None:
                # entrada con orden límite: se ejecuta (o no) en las velas SIGUIENTES
                lim = entry - self.limit_offset * atr
                dist = entry - stop
                for tm in profiles:
                    book.append(Shadow(profile_key(key, tm), lim, lim - dist, lim + tm * atr, self.horizon,
                                       wait=self.limit_wait))
                return
            for tm in profiles:
                book.append(Shadow(profile_key(key, tm), entry, stop, entry + tm * atr, self.horizon))
        else:
            book.append(Shadow(key, entry, stop, target, self.horizon))

    def update(self, symbol: str, high: float, low: float, close: float) -> None:
        keep = []
        ce = self.fee if self.entry_cost is None else self.entry_cost
        ct = self.fee if self.target_cost is None else self.target_cost
        cs = self.fee if self.stop_cost is None else self.stop_cost
        for s in self.open.get(symbol, []):
            fill_candle = False
            if s.wait > 0:
                # supuesto conservador: la orden límite solo se ejecuta si el precio la ATRAVIESA
                # (tocarla no basta: en la cola puede haber órdenes delante)
                if low < s.entry:
                    s.wait = 0
                    fill_candle = True
                else:
                    s.wait -= 1
                    if s.wait <= 0:
                        base = s.key.split("#")[0]
                        self.missed[base] = self.missed.get(base, 0) + 1
                    else:
                        keep.append(s)
                    continue
            s.expires -= 1
            s.age += 1
            risk = s.entry - s.stop
            if low <= s.stop:
                exit_px, c_exit = s.stop, cs
            elif high >= s.target and not fill_candle:  # en la vela de entrada no se sabe el orden: pesimista
                exit_px, c_exit = s.target, ct
            elif s.expires <= 0:
                exit_px, c_exit = close, cs
            else:
                keep.append(s)
                continue
            r = (exit_px - s.entry - ce * s.entry - c_exit * exit_px) / risk
            st = self.results.setdefault(s.key, [0, 0.0, 0.0, 0, 0.0])
            if len(st) < 5:  # memorias antiguas sin duración
                st.append(st[0] * self.horizon / 2)
            st[0] += 1
            st[1] += r
            st[2] += r * r
            st[3] += int(r > 0)
            st[4] += s.age
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

    def effective_n(self, key: str) -> float:
        st = self.results.get(key)
        if not st or not st[0]:
            return 0.0
        avg_dur = (st[4] / st[0]) if len(st) > 4 and st[4] else self.horizon / 2
        return st[0] * min(1.0, self.sample_gap / max(1.0, avg_dur))

    def win_prob(self, key: str, z: float) -> Tuple[float, float, float]:
        """(acierto medido, cota inferior verificable, muestras efectivas)."""
        st = self.results.get(key)
        if not st or not st[0]:
            return 0.0, 0.0, 0.0
        n_eff = self.effective_n(key)
        rate = st[3] / st[0]
        return rate, wilson_lower(rate * n_eff, n_eff, z), n_eff

    def choose(self, key: str, profiles: Sequence[float], min_win_prob: float, z: float,
               min_edge: float = 0.0) -> Tuple[bool, str, Optional[float], float]:
        """Mejor perfil de salida que cumple TODO; (ok, motivo, objetivo_ATR, prob_verificada)."""
        best: Optional[Tuple[float, float, float]] = None  # (edge, target, p_lb)
        best_seen = (0.0, 0.0, 0.0, "")
        for tm in profiles:
            pk = profile_key(key, tm)
            rate, p_lb, n_eff = self.win_prob(pk, z)
            e, _ = self.edge(pk)
            if p_lb > best_seen[0]:
                best_seen = (p_lb, rate, n_eff, f"{tm:g}")
            if n_eff >= self.min_samples and p_lb >= min_win_prob and e > min_edge:
                if best is None or e > best[0]:
                    best = (e, tm, p_lb)
        if best:
            return True, f"acierto verificado ≥{best[2]:.0%}, esperanza {best[0]:+.2f}R", best[1], best[2]
        p_lb, rate, n_eff, tm = best_seen
        if n_eff < self.min_samples:
            return False, f"sin historial suficiente ({n_eff:.0f}/{self.min_samples} efectivas)", None, p_lb
        return False, f"probabilidad no verificada ({p_lb:.0%} < {min_win_prob:.0%}; medida {rate:.0%})", None, p_lb

    def approved(self, key: str) -> Tuple[bool, str]:
        e, n = self.edge(key)
        if n < self.min_samples:
            return False, f"sin historial suficiente ({n}/{self.min_samples})"
        if e < self.min_edge:
            return False, f"sin ventaja demostrada ({e:+.2f}R)"
        return True, f"ventaja {e:+.2f}R en {n} casos"

    def table(self, z: float = 3.0) -> List[tuple]:
        """(tipo, casos, R medio, acierto, esperanza conservadora, acierto verificable)."""
        rows = []
        for k, st in self.results.items():
            e, n = self.edge(k)
            _, p_lb, _ = self.win_prob(k, z)
            rows.append((k, n, st[1] / st[0], st[3] / st[0], e, p_lb))
        return sorted(rows, key=lambda r: (-r[5], -r[4]))

    def to_dict(self) -> dict:
        return {"results": self.results, "missed": self.missed}

    @classmethod
    def from_dict(cls, d: Optional[dict], **kw: float) -> "Calibrator":
        c = cls(**kw)  # type: ignore[arg-type]
        if d:
            c.results = {k: list(v) for k, v in d.get("results", {}).items()}
            c.missed = dict(d.get("missed", {}))
        return c
