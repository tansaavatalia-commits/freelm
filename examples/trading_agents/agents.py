"""Los agentes. Cada uno mira la misma ventana de velas y emite una ``Signal``:

    score       en [-1, 1]  (-1 = vender fuerte, 0 = neutral, +1 = comprar fuerte)
    confidence  en [0, 1]
    reason      texto corto y legible

Están agrupados en equipos inspirados en las familias de estrategias más
usadas en los proyectos de trading open source más conocidos de GitHub
(freqtrade, jesse, backtrader, hummingbot...):

    tendencia  -> cruce de EMAs, MACD
    reversión  -> RSI, Bandas de Bollinger
    flujo      -> OBV / volumen, ruptura de rango (Donchian / "turtle")
    ia         -> un analista LLM gratuito vía freelm (opcional)

Ningún agente es "el bueno": el ``Coordinator`` (learning.py) aprende con la
experiencia cuánto pesa cada uno.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import indicators as ta
from market import Candle


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


def _neutral(name: str, why: str) -> Signal:
    return Signal(name, 0.0, 0.0, why)


def _clip(x: float) -> float:
    return max(-1.0, min(1.0, x))


class Agent:
    name = "agent"
    team = "general"
    warmup = 50

    def analyze(self, candles: Sequence[Candle]) -> Signal:  # pragma: no cover - interfaz
        raise NotImplementedError


class EmaCrossAgent(Agent):
    """Cruce EMA rápida/lenta (la "sample strategy" clásica de freqtrade)."""
    name, team = "ema_cross", "tendencia"

    def __init__(self, fast: int = 12, slow: int = 26) -> None:
        self.fast, self.slow = fast, slow
        self.warmup = slow + 5

    def analyze(self, candles: Sequence[Candle]) -> Signal:
        closes = [c.close for c in candles]
        f, s = ta.ema(closes, self.fast)[-1], ta.ema(closes, self.slow)[-1]
        if f is None or s is None:
            return _neutral(self.name, "sin datos")
        gap = (f - s) / s
        score = _clip(gap * 50)  # 2% de separación ~ señal máxima
        return Signal(self.name, score, min(1.0, abs(gap) * 80 + 0.2),
                      f"EMA{self.fast} {'>' if gap > 0 else '<'} EMA{self.slow} ({gap:+.2%})")


class MacdAgent(Agent):
    name, team, warmup = "macd", "tendencia", 40

    def analyze(self, candles: Sequence[Candle]) -> Signal:
        closes = [c.close for c in candles]
        _, _, hist = ta.macd(closes)
        h, prev = hist[-1], hist[-2] if len(hist) > 1 else None
        if h is None or prev is None:
            return _neutral(self.name, "sin datos")
        norm = h / closes[-1]
        accel = h - prev
        score = _clip(norm * 300 + (0.3 if accel > 0 else -0.3))
        return Signal(self.name, score, 0.5 + min(0.5, abs(norm) * 200),
                      f"histograma {h:+.2f} ({'acelera' if accel > 0 else 'frena'})")


class RsiAgent(Agent):
    """Reversión a la media: sobreventa compra, sobrecompra vende."""
    name, team, warmup = "rsi", "reversión", 20

    def __init__(self, period: int = 14, low: float = 30, high: float = 70) -> None:
        self.period, self.low, self.high = period, low, high

    def analyze(self, candles: Sequence[Candle]) -> Signal:
        r = ta.rsi([c.close for c in candles], self.period)[-1]
        if r is None:
            return _neutral(self.name, "sin datos")
        score = _clip((50 - r) / 25)  # RSI 25 -> +1, RSI 75 -> -1
        conf = 0.9 if (r < self.low or r > self.high) else 0.3
        return Signal(self.name, score, conf, f"RSI {r:.1f}")


class BollingerAgent(Agent):
    name, team, warmup = "bollinger", "reversión", 25

    def analyze(self, candles: Sequence[Candle]) -> Signal:
        closes = [c.close for c in candles]
        lo, mid, up = ta.bollinger(closes)
        if lo[-1] is None or up[-1] is None or mid[-1] is None:
            return _neutral(self.name, "sin datos")
        width = up[-1] - lo[-1] or 1e-9
        pos = (closes[-1] - lo[-1]) / width  # 0 = banda inferior, 1 = superior
        return Signal(self.name, _clip((0.5 - pos) * 2), 0.4 + min(0.6, abs(pos - 0.5)),
                      f"%B {pos:.2f}, ancho {width / mid[-1]:.2%}")


class VolumeFlowAgent(Agent):
    """Dinero que entra o sale: pendiente del OBV contra la del precio."""
    name, team, warmup = "obv_flow", "flujo", 30

    def analyze(self, candles: Sequence[Candle]) -> Signal:
        closes = [c.close for c in candles]
        o = ta.obv(closes, [c.volume for c in candles])
        so, sp = ta.slope(o[-20:], 20), ta.slope(closes, 20)
        if so is None or sp is None:
            return _neutral(self.name, "sin datos")
        score = _clip(so * 5)
        diverge = (so > 0) != (sp > 0)
        return Signal(self.name, score, 0.7 if diverge else 0.4,
                      f"OBV {'sube' if so > 0 else 'baja'}{' (divergencia)' if diverge else ''}")


class BreakoutAgent(Agent):
    """Ruptura de canal Donchian de 20 velas (las "tortugas")."""
    name, team, warmup = "breakout", "flujo", 25

    def __init__(self, period: int = 20) -> None:
        self.period = period

    def analyze(self, candles: Sequence[Candle]) -> Signal:
        if len(candles) <= self.period:
            return _neutral(self.name, "sin datos")
        prev = candles[-self.period - 1: -1]
        hi, lo = max(c.high for c in prev), min(c.low for c in prev)
        px = candles[-1].close
        if px > hi:
            return Signal(self.name, 1.0, 0.8, f"rompe máximo de {self.period} velas")
        if px < lo:
            return Signal(self.name, -1.0, 0.8, f"rompe mínimo de {self.period} velas")
        pos = (px - lo) / ((hi - lo) or 1e-9)
        return Signal(self.name, _clip((pos - 0.5) * 0.6), 0.2, f"dentro del canal ({pos:.0%})")


_JSON = re.compile(r"\{.*\}", re.S)


class LLMAnalystAgent(Agent):
    """Un analista que razona con un LLM gratuito (freelm reparte la carga entre
    proveedores gratis con failover). Recibe el resumen técnico y la opinión de
    los demás equipos, y devuelve un JSON. Si no hay LLM disponible, se queda
    neutral: el bot nunca se cae por culpa de la IA."""
    name, team, warmup = "llm_analyst", "ia", 40

    def __init__(self, llm: Any, model: str = "chat:fast", symbol: str = "BTCUSDT") -> None:
        self.llm, self.model, self.symbol = llm, model, symbol
        self.peer_signals: List[Signal] = []
        self.last_error: Optional[str] = None

    def _snapshot(self, candles: Sequence[Candle]) -> Dict[str, Any]:
        closes = [c.close for c in candles]
        r = ta.rsi(closes)[-1]
        _, _, hist = ta.macd(closes)
        a = ta.atr([c.high for c in candles], [c.low for c in candles], closes)[-1]

        def chg(n: int) -> Optional[float]:
            return round(closes[-1] / closes[-n - 1] - 1, 4) if len(closes) > n else None

        return {
            "symbol": self.symbol, "price": round(closes[-1], 6),
            "change_1": chg(1), "change_6": chg(6), "change_24": chg(24),
            "rsi14": round(r, 1) if r is not None else None,
            "macd_hist": round(hist[-1], 6) if hist[-1] is not None else None,
            "atr_pct": round(a / closes[-1], 4) if a else None,
            "peers": [{"agent": s.agent, "score": round(s.score, 2), "why": s.reason} for s in self.peer_signals],
        }

    def analyze(self, candles: Sequence[Candle]) -> Signal:
        prompt = (
            "Eres un analista cuantitativo prudente. Con estos datos de mercado y las opiniones de otros "
            "agentes, responde SOLO con un JSON: "
            '{"score": número entre -1 (vender) y 1 (comprar), "confidence": 0..1, "reason": "máx 15 palabras"}.\n'
            f"{json.dumps(self._snapshot(candles), ensure_ascii=False)}"
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


def default_agents() -> List[Agent]:
    return [EmaCrossAgent(), MacdAgent(), RsiAgent(), BollingerAgent(), VolumeFlowAgent(), BreakoutAgent()]
