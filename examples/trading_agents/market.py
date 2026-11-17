"""Datos de mercado: velas OHLCV públicas (sin claves), CSV o sintéticas.

- Binance: endpoint público de solo lectura ``data-api.binance.vision``, con
  paginación para descargar varios miles de velas.
- CSV propio: columnas ``time,open,high,low,close,volume``.
- Sintético: paseo aleatorio con regímenes. Con ``structure`` > 0 se añade
  algo de inercia en las tendencias y de vuelta a la media en los laterales,
  justo lo que los agentes saben explotar. Sirve para comprobar que el
  aprendizaje *encuentra* una ventaja cuando la hay. El mercado real es mucho
  más difícil: los resultados sintéticos no son una promesa.
"""
from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass
from typing import Dict, List, Sequence

import httpx

BINANCE_URL = "https://data-api.binance.vision/api/v3/klines"
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT"]


@dataclass
class Candle:
    time: int  # ms epoch de apertura
    open: float
    high: float
    low: float
    close: float
    volume: float


def fetch_binance(symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 1000, timeout: float = 15) -> List[Candle]:
    """Últimas ``limit`` velas (pagina hacia atrás de 1000 en 1000)."""
    out: List[Candle] = []
    end = None
    with httpx.Client(timeout=timeout) as http:
        while len(out) < limit:
            params = {"symbol": symbol.upper(), "interval": interval, "limit": min(1000, limit - len(out))}
            if end is not None:
                params["endTime"] = end
            r = http.get(BINANCE_URL, params=params)
            r.raise_for_status()
            page = [Candle(int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5]))
                    for k in r.json()]
            if not page:
                break
            out = page + out
            end = page[0].time - 1
            if len(page) < params["limit"]:
                break
    return out[-limit:]


def load_csv(path: str) -> List[Candle]:
    with open(path, newline="") as fh:
        return [Candle(int(float(row["time"])), float(row["open"]), float(row["high"]), float(row["low"]),
                       float(row["close"]), float(row["volume"])) for row in csv.DictReader(fh)]


def synthetic(n: int = 1500, seed: int = 7, start: float = 30_000.0, structure: float = 0.0) -> List[Candle]:
    rng = random.Random(seed)
    # (deriva, volatilidad, autocorrelación por unidad de ``structure``)
    regimes = [(0.0010, 0.008, 1.0), (0.0, 0.006, -1.0), (-0.0012, 0.014, 0.5), (0.0006, 0.010, 1.0)]
    drift, vol, ac = regimes[0]
    price, out, t, prev = start, [], 1_600_000_000_000, 0.0
    for i in range(n):
        if i % 200 == 0:
            drift, vol, ac = rng.choice(regimes)
        ret = drift + structure * ac * 0.15 * prev + rng.gauss(0, vol)
        prev = ret - drift
        o = price
        c = max(1e-6, o * math.exp(ret))
        h = max(o, c) * (1 + abs(rng.gauss(0, vol / 2)))
        lo = min(o, c) * (1 - abs(rng.gauss(0, vol / 2)))
        v = abs(rng.gauss(100, 30)) * (1 + 20 * abs(ret))
        out.append(Candle(t, o, h, lo, c, v))
        price, t = c, t + 3_600_000
    return out


def align(series: Dict[str, Sequence[Candle]]) -> Dict[str, List[Candle]]:
    """Recorta todos los símbolos a las marcas de tiempo comunes."""
    common = set.intersection(*(set(c.time for c in cs) for cs in series.values())) if series else set()
    return {s: [c for c in cs if c.time in common] for s, cs in series.items()}
