"""Estrategias clásicas con respaldo académico, para validarlas con ``validation.judge``.

Los ~105 agentes técnicos no superaron la validación estadística (ver README).
Aquí se prueban, con las mismas exigencias, las dos familias con más evidencia
publicada en cripto y en otros mercados, en su forma más simple (pocos
parámetros = menos sobreajuste):

- ``tsmom`` (momentum de serie temporal / seguimiento de tendencia; Moskowitz,
  Ooi y Pedersen 2012; en cripto, Liu y Tsyvinski 2021): se compra una moneda
  cuando su cierre está por encima de su media de ``lookback`` días.
- ``xsmom`` (momentum relativo con filtro absoluto, «dual momentum»; Jegadeesh
  y Titman 1993, Antonacci 2014): cada ``rebalance`` días se compran las
  ``max_positions`` monedas que más subieron en ``lookback`` días, si subieron.

Reglas comunes, alineadas con lo pedido: solo spot y solo largo, como mucho 4
posiciones, cada una ≤ 1/4 del capital. La exposición total se reduce para
apuntar a una volatilidad anual de ``target_vol``: con correlación 1 supuesta,
es una estimación prudente, y así se mantiene la caída dentro del 10 %. Se
decide con el cierre del día t y se ejecuta a ese precio. Paga comisión y
deslizamiento por cada unidad de rotación, y ignora los cambios de peso
menores de ``band`` para no pagar comisiones por ruido. Sin mirar el futuro: todo
lo que usa el día t es de t o anterior.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Sequence

from market import Candle


@dataclass(frozen=True)
class StratConfig:
    kind: str = "tsmom"          # "tsmom" o "xsmom"
    lookback: int = 100          # días de la media (tsmom) o del retorno (xsmom)
    max_positions: int = 4
    rebalance: int = 1           # cada cuántos días se revisa la cartera
    target_vol: float = 0.12     # volatilidad anual objetivo de la cartera
    vol_window: int = 30
    fee: float = 0.001
    slippage: float = 0.0005
    band: float = 0.02           # cambio mínimo de peso que justifica operar

    @property
    def name(self) -> str:
        return f"{self.kind}·{self.lookback}"

    @property
    def warmup(self) -> int:
        return max(self.lookback, self.vol_window) + 1


def _vol(closes: Sequence[float], t: int, n: int) -> float:
    rs = [math.log(closes[i] / closes[i - 1]) for i in range(t - n + 1, t + 1)]
    m = sum(rs) / n
    return math.sqrt(sum((r - m) ** 2 for r in rs) / max(1, n - 1))


def targets(closes: Dict[str, Sequence[float]], t: int, cfg: StratConfig, periods_per_year: int = 365) -> Dict[str, float]:
    """Pesos objetivo (fracción del capital) con datos hasta el cierre ``t`` incluido."""
    scores: Dict[str, float] = {}
    for s, c in closes.items():
        if cfg.kind == "tsmom":
            sma = sum(c[t - cfg.lookback + 1:t + 1]) / cfg.lookback
            if c[t] > sma:
                scores[s] = c[t] / sma - 1
        elif cfg.kind == "xsmom":
            r = c[t] / c[t - cfg.lookback] - 1
            if r > 0:
                scores[s] = r
        else:
            raise ValueError(f"estrategia desconocida: {cfg.kind}")
    chosen = sorted(scores, key=lambda s: -scores[s])[:cfg.max_positions]
    if not chosen:
        return {}
    w = {s: 1.0 / cfg.max_positions for s in chosen}
    port_vol = sum(w[s] * _vol(closes[s], t, cfg.vol_window) for s in chosen) * math.sqrt(periods_per_year)
    k = min(1.0, cfg.target_vol / port_vol) if port_vol > 0 else 1.0
    return {s: x * k for s, x in w.items()}


def simulate(data: Dict[str, List[Candle]], cfg: StratConfig, trade_from: int = 0,
             periods_per_year: int = 365) -> dict:
    """Simula desde ``trade_from`` (o el calentamiento) hasta el final. Devuelve lo que
    ``validation.judge`` espera: curva de capital, retorno de cada operación cerrada
    (entrada -> salida, neto de costes) y caída máxima."""
    syms = list(data)
    closes = {s: [x.close for x in data[s]] for s in syms}
    n = min(len(v) for v in closes.values())
    start = max(cfg.warmup, trade_from)
    cost = cfg.fee + cfg.slippage
    eq, peak, mdd = 1.0, 1.0, 0.0
    equity = [eq]
    w: Dict[str, float] = {}
    entry: Dict[str, float] = {}
    trades: List[float] = []
    for t in range(start, n):
        if t > start and w:
            rets = {s: closes[s][t] / closes[s][t - 1] - 1 for s in w}
            pr = sum(w[s] * rets[s] for s in w)
            eq *= 1 + pr
            w = {s: x * (1 + rets[s]) / (1 + pr) for s, x in w.items()}
        if (t - start) % cfg.rebalance == 0:
            tgt = targets(closes, t, cfg, periods_per_year)
            new = dict(w)
            turnover = 0.0
            for s in set(w) | set(tgt):
                cur, want = w.get(s, 0.0), tgt.get(s, 0.0)
                # se entra o se sale siempre; los reajustes pequeños se ignoran
                if (want == 0.0) != (cur == 0.0) or abs(want - cur) >= cfg.band:
                    turnover += abs(want - cur)
                    if want == 0.0:
                        new.pop(s, None)
                        trades.append(closes[s][t] / entry.pop(s) * (1 - cost) / (1 + cost) - 1)
                    else:
                        if cur == 0.0:
                            entry[s] = closes[s][t]
                        new[s] = want
            eq *= 1 - turnover * cost
            w = new
        equity.append(eq)
        peak = max(peak, eq)
        mdd = max(mdd, 1 - eq / peak)
    bh = sum(closes[s][n - 1] / closes[s][start] - 1 for s in syms) / len(syms) if n > start else 0.0
    return {"equity": equity, "r": trades, "max_drawdown": mdd, "buy_hold": bh, "start": start, "n": n,
            "open": sorted(w)}


def default_family(lookbacks_ts: Sequence[int] = (20, 50, 100, 150, 200),
                   lookbacks_xs: Sequence[int] = (7, 14, 28, 56, 90)) -> Dict[str, StratConfig]:
    fam = {}
    for lb in lookbacks_ts:
        c = StratConfig("tsmom", lb)
        fam[c.name] = c
    for lb in lookbacks_xs:
        c = StratConfig("xsmom", lb, rebalance=7)
        fam[c.name] = c
    return fam


def neighbours(family: Dict[str, StratConfig]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    by_kind: Dict[str, List[StratConfig]] = {}
    for c in family.values():
        by_kind.setdefault(c.kind, []).append(c)
    for cs in by_kind.values():
        cs.sort(key=lambda c: c.lookback)
        for i, c in enumerate(cs):
            out[c.name] = [cs[j].name for j in (i - 1, i + 1) if 0 <= j < len(cs)]
    return out


def ensemble(results: Dict[str, dict]) -> dict:
    """Las variantes a partes iguales, sin elegir ninguna: el capital se reparte entre
    todas y se reequilibra cada periodo. Es el remedio clásico cuando una familia
    entera gana, pero elegir «la mejor» sería sobreajuste (PBO alto)."""
    runs = list(results.values())
    t = min(len(r["equity"]) for r in runs)
    eq = [1.0]
    for i in range(1, t):
        eq.append(eq[-1] * (1 + sum(r["equity"][i] / r["equity"][i - 1] - 1 for r in runs) / len(runs)))
    peak, mdd = eq[0], 0.0
    for e in eq:
        peak = max(peak, e)
        mdd = max(mdd, 1 - e / peak)
    return {"equity": eq, "r": [x for r in runs for x in r["r"]], "max_drawdown": mdd,
            "buy_hold": runs[0]["buy_hold"] if runs else 0.0}
