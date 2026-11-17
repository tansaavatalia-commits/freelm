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
import sys
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence

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


FALLBACK_EXCHANGES = ("okx", "bybit", "kraken")


def fetch_ccxt(symbol: str, interval: str = "1h", limit: int = 1000, exchange_id: str = "okx",
               client: object = None) -> List[Candle]:
    """Velas de cualquier exchange de ccxt (datos públicos, sin claves)."""
    if client is None:
        import ccxt  # type: ignore[import-not-found]
        client = getattr(ccxt, exchange_id)({"enableRateLimit": True})
    s = symbol.upper()
    market = s if "/" in s else f"{s[:-4]}/USDT" if s.endswith("USDT") else s
    rows = client.fetch_ohlcv(market, interval, limit=min(limit, 1000))  # type: ignore[attr-defined]
    return [Candle(int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5] or 0)) for r in rows]


def fetch_candles(symbol: str, interval: str = "1h", limit: int = 1000, retries: int = 3,
                  primary: Optional[Callable[..., List[Candle]]] = None, sleep: Callable[[float], None] = time.sleep,
                  fallbacks: Sequence[str] = FALLBACK_EXCHANGES) -> List[Candle]:
    """Binance con reintentos (espera 2, 4, 8 s...). Si sigue fallando y ccxt está
    instalado, prueba otros exchanges. Un corte de red no deja al bot sin datos."""
    primary = primary or fetch_binance
    err: Optional[Exception] = None
    for i in range(retries):
        try:
            out = primary(symbol, interval, limit)
            if out:
                return out
        except Exception as e:  # noqa: BLE001 - se reintenta y se informa al final
            err = e
        if i < retries - 1:
            sleep(2 ** (i + 1))
    for ex in fallbacks:
        try:
            out = fetch_ccxt(symbol, interval, limit, ex)
            if out:
                print(f"[datos] {symbol}: Binance falló ({type(err).__name__ if err else 'vacío'}), "
                      f"usando {ex}", file=sys.stderr)
                return out
        except Exception:  # noqa: BLE001 - siguiente respaldo
            continue
    raise RuntimeError(f"sin datos para {symbol}: {type(err).__name__ if err else 'respuesta vacía'}: {err}")


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
