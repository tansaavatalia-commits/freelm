"""Datos de mercado: velas OHLCV públicas (sin claves) o sintéticas.

Fuentes:
- Binance (endpoint público de solo lectura ``data-api.binance.vision``).
- Un CSV propio con columnas ``time,open,high,low,close,volume``.
- Un generador sintético con regímenes (tendencia / lateral / pánico) para
  probar todo sin red.
"""
from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass
from typing import List

import httpx

BINANCE_URL = "https://data-api.binance.vision/api/v3/klines"


@dataclass
class Candle:
    time: int  # ms epoch de apertura
    open: float
    high: float
    low: float
    close: float
    volume: float


def fetch_binance(symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 1000, timeout: float = 15) -> List[Candle]:
    r = httpx.get(BINANCE_URL, params={"symbol": symbol.upper(), "interval": interval, "limit": min(limit, 1000)},
                  timeout=timeout)
    r.raise_for_status()
    return [Candle(int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])) for k in r.json()]


def load_csv(path: str) -> List[Candle]:
    with open(path, newline="") as fh:
        return [Candle(int(float(row["time"])), float(row["open"]), float(row["high"]), float(row["low"]),
                       float(row["close"]), float(row["volume"])) for row in csv.DictReader(fh)]


def synthetic(n: int = 1500, seed: int = 7, start: float = 30_000.0) -> List[Candle]:
    """Paseo aleatorio geométrico con cambios de régimen: suficiente para que
    algunos agentes acierten y otros fallen, y el aprendizaje tenga qué medir."""
    rng = random.Random(seed)
    regimes = [(0.0012, 0.008), (0.0, 0.006), (-0.0015, 0.014), (0.0008, 0.01)]  # (drift, vol)
    drift, vol = regimes[0]
    price, out, t = start, [], 1_600_000_000_000
    for i in range(n):
        if i % 200 == 0:
            drift, vol = rng.choice(regimes)
        ret = rng.gauss(drift, vol)
        o = price
        c = max(1e-6, o * math.exp(ret))
        h = max(o, c) * (1 + abs(rng.gauss(0, vol / 2)))
        lo = min(o, c) * (1 - abs(rng.gauss(0, vol / 2)))
        v = abs(rng.gauss(100, 30)) * (1 + 20 * abs(ret))
        out.append(Candle(t, o, h, lo, c, v))
        price, t = c, t + 3_600_000
    return out
