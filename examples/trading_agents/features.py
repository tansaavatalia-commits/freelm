"""Caché de indicadores por ventana: cientos de agentes comparten los cálculos.

Un enjambre de ~150 agentes por símbolo pide muchas veces lo mismo (EMA 20,
RSI 14...). ``Features`` calcula cada indicador una sola vez por ventana y lo
memoriza: así el bot procesa miles de señales por segundo en Python puro.
"""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Sequence

import indicators as ta
from market import Candle


class Features:
    def __init__(self, candles: Sequence[Candle], symbol: str = "") -> None:
        self.candles = candles
        self.symbol = symbol
        self.closes: List[float] = [c.close for c in candles]
        self.highs: List[float] = [c.high for c in candles]
        self.lows: List[float] = [c.low for c in candles]
        self.volumes: List[float] = [c.volume for c in candles]
        self._memo: Dict[tuple, Any] = {}

    def __len__(self) -> int:
        return len(self.closes)

    @property
    def price(self) -> float:
        return self.closes[-1]

    def _get(self, key: tuple, fn: Callable[[], Any]) -> Any:
        v = self._memo.get(key)
        if v is None:
            v = self._memo[key] = fn()
        return v

    def ema(self, p: int) -> ta.Series:
        return self._get(("ema", p), lambda: ta.ema(self.closes, p))

    def sma(self, p: int) -> ta.Series:
        return self._get(("sma", p), lambda: ta.sma(self.closes, p))

    def rsi(self, p: int) -> ta.Series:
        return self._get(("rsi", p), lambda: ta.rsi(self.closes, p))

    def macd(self, f: int, s: int, g: int) -> tuple:
        return self._get(("macd", f, s, g), lambda: ta.macd(self.closes, f, s, g))

    def bollinger(self, p: int, k: float) -> tuple:
        return self._get(("bb", p, k), lambda: ta.bollinger(self.closes, p, k))

    def atr(self, p: int = 14) -> ta.Series:
        return self._get(("atr", p), lambda: ta.atr(self.highs, self.lows, self.closes, p))

    def obv(self) -> List[float]:
        return self._get(("obv",), lambda: ta.obv(self.closes, self.volumes))

    def stoch(self, p: int) -> float:
        def calc() -> float:
            hi, lo = max(self.highs[-p:]), min(self.lows[-p:])
            return (self.price - lo) / ((hi - lo) or 1e-12) * 100
        return self._get(("stoch", p), calc)

    def vwap(self, p: int) -> float:
        def calc() -> float:
            v = self.volumes[-p:]
            tp = [(h + lo + c) / 3 for h, lo, c in zip(self.highs[-p:], self.lows[-p:], self.closes[-p:])]
            return sum(a * b for a, b in zip(tp, v)) / (sum(v) or 1e-12)
        return self._get(("vwap", p), calc)

    def resampled(self, k: int) -> List[float]:
        """Cierres de un marco temporal ``k`` veces mayor (multi-timeframe)."""
        return self._get(("rs", k), lambda: self.closes[(len(self.closes) - 1) % k::k])

    def vol(self, n: int = 30) -> float:
        def calc() -> float:
            xs = self.closes[-n - 1:]
            rets = [math.log(xs[i] / xs[i - 1]) for i in range(1, len(xs))]
            return math.sqrt(sum(r * r for r in rets) / len(rets)) if rets else 0.01
        return self._get(("vol", n), calc)
