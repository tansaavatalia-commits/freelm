"""Indicadores técnicos clásicos, puros (listas de floats, sin dependencias).

Son los mismos bloques que usan las estrategias más populares de GitHub
(freqtrade, jesse, backtrader, TA-Lib): EMA, RSI de Wilder, MACD, Bandas de
Bollinger, ATR y OBV. Cada función devuelve una lista del mismo largo que la
entrada; los primeros valores sin datos suficientes son ``None``.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

Series = List[Optional[float]]


def sma(values: Sequence[float], period: int) -> Series:
    out: Series = [None] * len(values)
    acc = 0.0
    for i, v in enumerate(values):
        acc += v
        if i >= period:
            acc -= values[i - period]
        if i >= period - 1:
            out[i] = acc / period
    return out


def ema(values: Sequence[float], period: int) -> Series:
    out: Series = [None] * len(values)
    if len(values) < period:
        return out
    k = 2.0 / (period + 1)
    prev = sum(values[:period]) / period  # semilla = SMA, como TA-Lib
    out[period - 1] = prev
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(closes: Sequence[float], period: int = 14) -> Series:
    """RSI con suavizado de Wilder."""
    out: Series = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains = losses = 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    avg_g, avg_l = gains / period, losses / period

    def _val(g: float, l_: float) -> float:
        if l_ == 0:
            return 100.0 if g > 0 else 50.0
        return 100.0 - 100.0 / (1.0 + g / l_)

    out[period] = _val(avg_g, avg_l)
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        avg_g = (avg_g * (period - 1) + max(d, 0.0)) / period
        avg_l = (avg_l * (period - 1) + max(-d, 0.0)) / period
        out[i] = _val(avg_g, avg_l)
    return out


def macd(closes: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[Series, Series, Series]:
    ef, es = ema(closes, fast), ema(closes, slow)
    line: Series = [f - s if f is not None and s is not None else None for f, s in zip(ef, es)]
    start = next((i for i, v in enumerate(line) if v is not None), len(line))
    sig_tail = ema([v for v in line[start:] if v is not None], signal)
    sig: Series = [None] * start + sig_tail
    hist: Series = [m - s if m is not None and s is not None else None for m, s in zip(line, sig)]
    return line, sig, hist


def bollinger(closes: Sequence[float], period: int = 20, k: float = 2.0) -> Tuple[Series, Series, Series]:
    mid = sma(closes, period)
    up: Series = [None] * len(closes)
    lo: Series = [None] * len(closes)
    s2 = 0.0  # suma móvil de cuadrados: varianza = E[x²] - media²  (O(n) en vez de O(n·period))
    for i, x in enumerate(closes):
        s2 += x * x
        if i >= period:
            s2 -= closes[i - period] ** 2
        m = mid[i]
        if m is not None:
            sd = math.sqrt(max(0.0, s2 / period - m * m))
            up[i], lo[i] = m + k * sd, m - k * sd
    return lo, mid, up


def atr(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14) -> Series:
    out: Series = [None] * len(closes)
    if len(closes) <= period:
        return out
    trs = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    prev = sum(trs[1: period + 1]) / period
    out[period] = prev
    for i in range(period + 1, len(closes)):
        prev = (prev * (period - 1) + trs[i]) / period
        out[i] = prev
    return out


def obv(closes: Sequence[float], volumes: Sequence[float]) -> List[float]:
    out = [0.0] * len(closes)
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            out[i] = out[i - 1] + volumes[i]
        elif closes[i] < closes[i - 1]:
            out[i] = out[i - 1] - volumes[i]
        else:
            out[i] = out[i - 1]
    return out


def slope(values: Sequence[float], lookback: int) -> Optional[float]:
    """Pendiente media relativa de las últimas ``lookback`` velas (regresión lineal)."""
    if len(values) < lookback or lookback < 2:
        return None
    ys = list(values[-lookback:])
    n = len(ys)
    mx = (n - 1) / 2
    my = sum(ys) / n
    num = sum((i - mx) * (y - my) for i, y in enumerate(ys))
    den = sum((i - mx) ** 2 for i in range(n))
    scale = sum(abs(y) for y in ys) / n or 1.0
    return num / den / scale
