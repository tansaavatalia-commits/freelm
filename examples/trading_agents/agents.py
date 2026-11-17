"""Los agentes: un enjambre de ~100 especialistas por símbolo, en 7 equipos.

Cada agente mira la misma ventana (vía ``Features``, con caché) y emite una
``Signal``:

    score       en [-1, 1]  (-1 = vender fuerte, 0 = neutral, +1 = comprar fuerte)
    confidence  en [0, 1]
    reason      texto corto y legible

Las familias son las estrategias que más se repiten en los proyectos de
trading open source más conocidos de GitHub (freqtrade, jesse, backtrader,
hummingbot, Lean). Cada familia se instancia con muchos parámetros distintos:
nadie sabe de antemano qué EMA o qué RSI funciona en cada mercado, así que se
ponen a competir y el aprendizaje decide.

    tendencia      cruces de EMA, MACD, pendiente
    reversión      RSI, Bandas de Bollinger, estocástico, distancia a VWAP
    flujo          OBV, rupturas Donchian ("tortugas"), momentum ROC
    volatilidad    compresión/expansión de bandas ("squeeze"), ATR
    multi-marco    tendencia en marcos temporales 4x-24x mayores
    mercado        fuerza relativa entre monedas, amplitud, BTC líder, sentimiento
    ia             analista LLM gratuito vía freelm (opcional)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, List, Optional

import indicators as ta
from features import Features


@dataclass
class Signal:
    agent: str
    score: float
    confidence: float
    reason: str

    def __post_init__(self) -> None:
        self.score = max(-1.0, min(1.0, float(self.score)))
        self.confidence = max(0.0, min(1.0, float(self.confidence)))

    @property
    def value(self) -> float:
        return self.score * self.confidence


def _neutral(name: str, why: str = "sin datos") -> Signal:
    return Signal(name, 0.0, 0.0, why)


def _clip(x: float) -> float:
    return max(-1.0, min(1.0, x))


class Agent:
    name = "agent"
    team = "general"
    warmup = 50

    def analyze(self, f: Features) -> Signal:  # pragma: no cover - interfaz
        raise NotImplementedError


# ------------------------------------------------------------------ tendencia

class EmaCrossAgent(Agent):
    team = "tendencia"

    def __init__(self, fast: int = 12, slow: int = 26) -> None:
        self.fast, self.slow = fast, slow
        self.name, self.warmup = f"ema_{fast}_{slow}", slow + 5

    def analyze(self, f: Features) -> Signal:
        a, b = f.ema(self.fast)[-1], f.ema(self.slow)[-1]
        if a is None or b is None:
            return _neutral(self.name)
        gap = (a - b) / b
        return Signal(self.name, _clip(gap * 50), min(1.0, abs(gap) * 80 + 0.2),
                      f"EMA{self.fast} {'>' if gap > 0 else '<'} EMA{self.slow} ({gap:+.2%})")


class MacdAgent(Agent):
    team = "tendencia"

    def __init__(self, fast: int = 12, slow: int = 26, sig: int = 9) -> None:
        self.p = (fast, slow, sig)
        self.name, self.warmup = f"macd_{fast}_{slow}_{sig}", slow + sig + 5

    def analyze(self, f: Features) -> Signal:
        _, _, hist = f.macd(*self.p)
        h, prev = hist[-1], hist[-2] if len(hist) > 1 else None
        if h is None or prev is None:
            return _neutral(self.name)
        norm = h / f.price
        accel = h - prev
        return Signal(self.name, _clip(norm * 300 + (0.3 if accel > 0 else -0.3)), 0.5 + min(0.5, abs(norm) * 200),
                      f"histograma {h:+.2f} ({'acelera' if accel > 0 else 'frena'})")


class SlopeAgent(Agent):
    team = "tendencia"

    def __init__(self, ema: int = 50, lookback: int = 10) -> None:
        self.ema, self.lb = ema, lookback
        self.name, self.warmup = f"slope_{ema}_{lookback}", ema + lookback + 2

    def analyze(self, f: Features) -> Signal:
        e = f.ema(self.ema)
        tail = [x for x in e[-self.lb:] if x is not None]
        s = ta.slope(tail, self.lb)
        if s is None:
            return _neutral(self.name)
        return Signal(self.name, _clip(s * 400), min(1.0, abs(s) * 600 + 0.2), f"pendiente EMA{self.ema} {s:+.4%}")


# ------------------------------------------------------------------ reversión

class RsiAgent(Agent):
    team = "reversión"

    def __init__(self, period: int = 14, low: float = 30, high: float = 70) -> None:
        self.period, self.low, self.high = period, low, high
        self.name, self.warmup = f"rsi_{period}_{int(low)}", period + 5

    def analyze(self, f: Features) -> Signal:
        r = f.rsi(self.period)[-1]
        if r is None:
            return _neutral(self.name)
        span = (self.high - self.low) / 2 or 1
        conf = 0.9 if (r < self.low or r > self.high) else 0.25
        return Signal(self.name, _clip((50 - r) / span), conf, f"RSI{self.period} {r:.1f}")


class BollingerAgent(Agent):
    team = "reversión"

    def __init__(self, period: int = 20, k: float = 2.0) -> None:
        self.period, self.k = period, k
        self.name, self.warmup = f"bb_{period}_{k:g}", period + 5

    def analyze(self, f: Features) -> Signal:
        lo, mid, up = f.bollinger(self.period, self.k)
        if lo[-1] is None or up[-1] is None or mid[-1] is None:
            return _neutral(self.name)
        pos = (f.price - lo[-1]) / ((up[-1] - lo[-1]) or 1e-9)
        return Signal(self.name, _clip((0.5 - pos) * 2), 0.3 + min(0.7, abs(pos - 0.5)), f"%B {pos:.2f}")


class StochAgent(Agent):
    team = "reversión"

    def __init__(self, period: int = 14) -> None:
        self.period = period
        self.name, self.warmup = f"stoch_{period}", period + 2

    def analyze(self, f: Features) -> Signal:
        k = f.stoch(self.period)
        return Signal(self.name, _clip((50 - k) / 40), 0.8 if k < 15 or k > 85 else 0.25, f"%K {k:.0f}")


class VwapAgent(Agent):
    team = "reversión"

    def __init__(self, period: int = 48) -> None:
        self.period = period
        self.name, self.warmup = f"vwap_{period}", period + 2

    def analyze(self, f: Features) -> Signal:
        v = f.vwap(self.period)
        dev = (f.price - v) / v
        vol = f.vol() or 0.01
        z = dev / (vol * 3)
        return Signal(self.name, _clip(-z), min(1.0, abs(z) * 0.5 + 0.1), f"precio {dev:+.2%} vs VWAP{self.period}")


# ------------------------------------------------------------------ flujo

class ObvAgent(Agent):
    team = "flujo"

    def __init__(self, lookback: int = 20) -> None:
        self.lb = lookback
        self.name, self.warmup = f"obv_{lookback}", lookback + 5

    def analyze(self, f: Features) -> Signal:
        so, sp = ta.slope(f.obv()[-self.lb:], self.lb), ta.slope(f.closes, self.lb)
        if so is None or sp is None:
            return _neutral(self.name)
        diverge = (so > 0) != (sp > 0)
        return Signal(self.name, _clip(so * 5), 0.7 if diverge else 0.4,
                      f"OBV {'sube' if so > 0 else 'baja'}{' (divergencia)' if diverge else ''}")


class BreakoutAgent(Agent):
    team = "flujo"

    def __init__(self, period: int = 20) -> None:
        self.period = period
        self.name, self.warmup = f"donchian_{period}", period + 2

    def analyze(self, f: Features) -> Signal:
        p = self.period
        if len(f) <= p:
            return _neutral(self.name)
        hi, lo = max(f.highs[-p - 1:-1]), min(f.lows[-p - 1:-1])
        if f.price > hi:
            return Signal(self.name, 1.0, 0.8, f"rompe máximo de {p} velas")
        if f.price < lo:
            return Signal(self.name, -1.0, 0.8, f"rompe mínimo de {p} velas")
        pos = (f.price - lo) / ((hi - lo) or 1e-9)
        return Signal(self.name, _clip((pos - 0.5) * 0.6), 0.2, f"dentro del canal ({pos:.0%})")


class RocAgent(Agent):
    team = "flujo"

    def __init__(self, period: int = 12) -> None:
        self.period = period
        self.name, self.warmup = f"roc_{period}", period + 2

    def analyze(self, f: Features) -> Signal:
        roc = f.price / f.closes[-self.period - 1] - 1
        unit = (f.vol() or 0.01) * self.period ** 0.5
        z = roc / unit
        return Signal(self.name, _clip(z / 2), min(1.0, abs(z) / 3 + 0.1), f"ROC{self.period} {roc:+.2%}")


# ------------------------------------------------------------------ volatilidad

class SqueezeAgent(Agent):
    """Bandas estrechas = energía acumulada; se opera la dirección de salida."""
    team = "volatilidad"

    def __init__(self, period: int = 20, memory: int = 100) -> None:
        self.period, self.mem = period, memory
        self.name, self.warmup = f"squeeze_{period}_{memory}", period + memory

    def analyze(self, f: Features) -> Signal:
        lo, mid, up = f.bollinger(self.period, 2.0)
        widths = [(u - lo_) / m for lo_, m, u in zip(lo[-self.mem:], mid[-self.mem:], up[-self.mem:])
                  if lo_ is not None and m and u is not None]
        if len(widths) < self.mem // 2 or mid[-1] is None:
            return _neutral(self.name)
        rank = sum(1 for w in widths if w < widths[-1]) / len(widths)
        direction = 1.0 if f.price > mid[-1] else -1.0
        if rank < 0.2:  # compresión: preparado, poca convicción
            return Signal(self.name, direction * 0.3, 0.3, f"compresión (percentil {rank:.0%})")
        if rank > 0.8 and widths[-2] < widths[-1]:  # expansión en curso
            return Signal(self.name, direction, 0.7, f"expansión (percentil {rank:.0%})")
        return Signal(self.name, direction * 0.1, 0.1, f"ancho percentil {rank:.0%}")


class AtrTrendAgent(Agent):
    """Precio frente a media ± k·ATR (estilo Keltner / Supertrend)."""
    team = "volatilidad"

    def __init__(self, period: int = 20, k: float = 1.5) -> None:
        self.period, self.k = period, k
        self.name, self.warmup = f"keltner_{period}_{k:g}", period + 15

    def analyze(self, f: Features) -> Signal:
        m, a = f.ema(self.period)[-1], f.atr(14)[-1]
        if m is None or not a:
            return _neutral(self.name)
        z = (f.price - m) / (self.k * a)
        conf = 0.8 if abs(z) > 1 else 0.2
        return Signal(self.name, _clip(z), conf, f"{z:+.2f} bandas Keltner")


# ------------------------------------------------------------------ multi-marco

class MtfTrendAgent(Agent):
    """Tendencia en un marco temporal ``k`` veces mayor (p. ej. 1h -> 4h, 1d)."""
    team = "multi-marco"

    def __init__(self, k: int = 4, fast: int = 5, slow: int = 15) -> None:
        self.k, self.fast, self.slow = k, fast, slow
        self.name, self.warmup = f"mtf_{k}x_{fast}_{slow}", k * (slow + 2)

    def analyze(self, f: Features) -> Signal:
        rs = f.resampled(self.k)
        a, b = ta.ema(rs, self.fast)[-1] if rs else None, ta.ema(rs, self.slow)[-1] if rs else None
        if a is None or b is None:
            return _neutral(self.name)
        gap = (a - b) / b
        return Signal(self.name, _clip(gap * 30), min(1.0, abs(gap) * 40 + 0.3),
                      f"marco {self.k}x: EMA{self.fast} {'>' if gap > 0 else '<'} EMA{self.slow}")


# ------------------------------------------------------------------ mercado (todas las monedas a la vez)

class RelStrengthAgent(Agent):
    """Momentum transversal: comprar las monedas que mejor lo hacen frente al
    resto. Es de los efectos más estudiados y persistentes en cripto."""
    team = "mercado"

    def __init__(self, lookback: int = 72) -> None:
        self.lb = lookback
        self.name, self.warmup = f"fuerza_rel_{lookback}", lookback + 2

    def analyze(self, f: Features) -> Signal:
        r = (f.ctx.get("rank") or {}).get(self.lb)
        if r is None or f.ctx.get("n", 1) < 3:
            return _neutral(self.name, "universo demasiado pequeño")
        return Signal(self.name, _clip((r - 0.5) * 2), 0.4 + abs(r - 0.5),
                      f"puesto {r:.0%} de {f.ctx['n']} a {self.lb} velas")


class BreadthAgent(Agent):
    """Amplitud: cuando casi todo el mercado sube, las compras salen mejor."""
    team, name, warmup = "mercado", "amplitud", 52

    def analyze(self, f: Features) -> Signal:
        b = f.ctx.get("breadth")
        if b is None:
            return _neutral(self.name)
        return Signal(self.name, _clip((b - 0.5) * 2.5), 0.3 + abs(b - 0.5), f"{b:.0%} de monedas sobre su media 50")


class BtcLeaderAgent(Agent):
    """BTC arrastra al resto: su tendencia de fondo y su último día."""
    team, name, warmup = "mercado", "btc_lider", 202

    def analyze(self, f: Features) -> Signal:
        g, r = f.ctx.get("btc_gap"), f.ctx.get("btc_ret24")
        if g is None:
            return _neutral(self.name)
        score = _clip(g * 15 + (r or 0) * 10)
        return Signal(self.name, score, min(1.0, 0.3 + abs(g) * 8), f"BTC {g:+.1%} vs media 200, 24 h {r or 0:+.1%}")


class SentimentAgent(Agent):
    """Contrarian con el Fear & Greed: el miedo extremo suele ser buena compra y
    la codicia extrema, mal momento para entrar."""
    team, name, warmup = "mercado", "sentimiento", 2

    def analyze(self, f: Features) -> Signal:
        v = f.ctx.get("fng")
        if v is None:
            return _neutral(self.name, "sin dato de sentimiento")
        extreme = v <= 25 or v >= 75
        return Signal(self.name, _clip((50 - v) / 40), 0.6 if extreme else 0.15, f"Fear & Greed {v}")


# ------------------------------------------------------------------ ia

_JSON = re.compile(r"\{.*\}", re.S)


class LLMAnalystAgent(Agent):
    """Analista con un LLM gratuito (freelm reparte la carga entre proveedores
    gratis con failover). Recibe el resumen técnico y el veredicto de los demás
    equipos y devuelve JSON. Sin LLM disponible se queda neutral: el bot nunca
    se cae por culpa de la IA."""
    team = "ia"
    warmup = 40

    def __init__(self, llm: Any, model: str = "chat:fast", symbol: str = "") -> None:
        self.llm, self.model, self.symbol = llm, model, symbol
        self.name = "llm_analyst"
        self.peer_signals: List[Signal] = []
        self.last_error: Optional[str] = None

    def _snapshot(self, f: Features) -> dict:
        r, a = f.rsi(14)[-1], f.atr(14)[-1]
        _, _, hist = f.macd(12, 26, 9)

        def chg(n: int) -> Optional[float]:
            return round(f.price / f.closes[-n - 1] - 1, 4) if len(f) > n else None

        return {
            "symbol": f.symbol or self.symbol, "price": round(f.price, 6),
            "change_1": chg(1), "change_6": chg(6), "change_24": chg(24),
            "rsi14": round(r, 1) if r is not None else None,
            "macd_hist": round(hist[-1], 6) if hist[-1] is not None else None,
            "atr_pct": round(a / f.price, 4) if a else None,
            "teams": [{"team": s.agent, "score": round(s.score, 2), "confidence": round(s.confidence, 2)}
                      for s in self.peer_signals],
        }

    def analyze(self, f: Features) -> Signal:
        prompt = (
            "Eres un gestor de riesgo cuantitativo muy prudente: prefieres no operar a operar sin ventaja clara. "
            "Con estos datos y el veredicto de los equipos, responde SOLO con un JSON: "
            '{"score": número entre -1 (vender) y 1 (comprar), "confidence": 0..1, "reason": "máx 15 palabras"}.\n'
            f"{json.dumps(self._snapshot(f), ensure_ascii=False)}"
        )
        try:
            r = self.llm.chat([{"role": "user", "content": prompt}], model=self.model, temperature=0.2, max_tokens=300)
            m = _JSON.search(r.text or "")
            if not m:
                raise ValueError("respuesta sin JSON")
            d = json.loads(m.group(0))
            self.last_error = None
            return Signal(self.name, float(d["score"]), float(d.get("confidence", 0.5)),
                          f"{str(d.get('reason', ''))[:120]} [{r.provider}]")
        except Exception as e:  # noqa: BLE001 - la IA es opcional, nunca tumba el bot
            self.last_error = f"{type(e).__name__}: {e}"
            return _neutral(self.name, f"LLM no disponible ({type(e).__name__})")


# ------------------------------------------------------------------ enjambre

def agent_swarm() -> List[Agent]:
    """~100 agentes por símbolo con parámetros variados."""
    out: List[Agent] = []
    for fa, sl in [(5, 20), (8, 21), (9, 30), (12, 26), (10, 40), (20, 50), (15, 60), (21, 55), (5, 35), (30, 100),
                   (50, 200), (13, 48)]:
        out.append(EmaCrossAgent(fa, sl))
    for p in [(12, 26, 9), (8, 17, 9), (5, 35, 5), (19, 39, 9), (24, 52, 18), (6, 13, 5)]:
        out.append(MacdAgent(*p))
    for e in (20, 50, 100):
        for lb in (5, 10, 20):
            out.append(SlopeAgent(e, lb))
    for p in (7, 14, 21):
        for lo, hi in ((30, 70), (25, 75), (20, 80)):
            out.append(RsiAgent(p, lo, hi))
    for p in (14, 20, 30):
        for k in (1.5, 2.0, 2.5):
            out.append(BollingerAgent(p, k))
    out += [StochAgent(p) for p in (5, 9, 14, 21, 34)]
    out += [VwapAgent(p) for p in (12, 24, 48, 96)]
    out += [ObvAgent(lb) for lb in (10, 20, 40, 60)]
    out += [BreakoutAgent(p) for p in (10, 20, 30, 40, 55, 100)]
    out += [RocAgent(p) for p in (3, 6, 12, 24, 48, 96)]
    out += [SqueezeAgent(p, m) for p in (14, 20, 30) for m in (60, 120)]
    out += [AtrTrendAgent(p, k) for p in (10, 20, 50) for k in (1.0, 1.5, 2.5)]
    for k in (2, 4, 6, 12, 24):
        for fa, sl in ((3, 8), (5, 15)):
            out.append(MtfTrendAgent(k, fa, sl))
    out += [RelStrengthAgent(lb) for lb in (24, 72, 168)]
    out += [BreadthAgent(), BtcLeaderAgent(), SentimentAgent()]
    return out


default_agents = agent_swarm
