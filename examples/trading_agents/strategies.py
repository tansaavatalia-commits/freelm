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
from typing import Dict, List, Sequence, Tuple

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
    # --- mejoras (por defecto apagadas: reproducen exactamente la versión validada antes)
    risk_model: str = "corr1"    # "corr1" = correlación 1 supuesta; "cov" = covarianza real con shrinkage
    shrink: float = 0.5          # intensidad del shrinkage hacia correlación constante (Ledoit-Wolf)
    dd_budget: float = 0.0       # control de caída (CPPI): 0 = apagado; 0.10 = la caída máxima acordada
    dd_start: float = 0.5        # fracción del presupuesto a partir de la cual se empieza a reducir exposición
    dd_window: int = 0           # días del máximo de referencia de la caída (0 = máximo histórico)

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


# --------------------------------------------------------------------------- motor rápido
#
# Idea de vectorbt (calcular una vez, simular muchas veces), sin numpy: un ``Panel``
# precalcula sumas acumuladas de precios, retornos logarítmicos y productos cruzados.
# Así la media móvil, la volatilidad y la covarianza de cualquier ventana cuestan O(1)
# en vez de O(ventana), y el mismo panel sirve para todas las variantes de la familia.
# Admite universos desiguales: cada moneda entra cuando empieza a cotizar.


class Panel:
    def __init__(self, data: Dict[str, Sequence[Candle]]) -> None:
        times = sorted({c.time for cs in data.values() for c in cs})
        self.times = times
        self.syms = list(data)
        idx = {t: i for i, t in enumerate(times)}
        n = len(times)
        nan = float("nan")
        self.close = {s: [nan] * n for s in self.syms}
        for s, cs in data.items():
            row = self.close[s]
            for c in cs:
                row[idx[c.time]] = c.close
        self.n = n
        # sumas acumuladas (índice i = suma de [0, i)); validez = número de datos presentes
        self.pc: Dict[str, List[float]] = {}
        self.pv: Dict[str, List[int]] = {}
        self.pr: Dict[str, List[float]] = {}
        self.pr2: Dict[str, List[float]] = {}
        self.ret: Dict[str, List[float]] = {}
        for s in self.syms:
            c = self.close[s]
            pc, pv, pr, pr2, ret = [0.0], [0], [0.0], [0.0], [0.0]
            for i in range(n):
                ok = c[i] == c[i]
                pc.append(pc[-1] + (c[i] if ok else 0.0))
                pv.append(pv[-1] + ok)
                r = math.log(c[i] / c[i - 1]) if i and ok and c[i - 1] == c[i - 1] else 0.0
                ret.append(r)
                pr.append(pr[-1] + r)
                pr2.append(pr2[-1] + r * r)
            self.pc[s], self.pv[s], self.pr[s], self.pr2[s], self.ret[s] = pc, pv, pr, pr2, ret[1:]
        self._px: Dict[Tuple[str, str], List[float]] = {}

    def has(self, s: str, t: int, n: int) -> bool:
        """¿Hay ``n`` + 1 precios seguidos hasta ``t`` (incluido)?"""
        return t - n >= 0 and self.pv[s][t + 1] - self.pv[s][t - n] == n + 1

    def sma(self, s: str, t: int, n: int) -> float:
        return (self.pc[s][t + 1] - self.pc[s][t + 1 - n]) / n

    def vol(self, s: str, t: int, n: int) -> float:
        a = self.pr[s][t + 1] - self.pr[s][t + 1 - n]
        b = self.pr2[s][t + 1] - self.pr2[s][t + 1 - n]
        return math.sqrt(max(b - a * a / n, 0.0) / max(1, n - 1))

    def cov(self, a: str, b: str, t: int, n: int) -> float:
        if a == b:
            v = self.vol(a, t, n)
            return v * v
        key = (a, b) if a < b else (b, a)
        px = self._px.get(key)
        if px is None:
            ra, rb = self.ret[key[0]], self.ret[key[1]]
            px = [0.0]
            for x, y in zip(ra, rb):
                px.append(px[-1] + x * y)
            self._px[key] = px
        sa = self.pr[a][t + 1] - self.pr[a][t + 1 - n]
        sb = self.pr[b][t + 1] - self.pr[b][t + 1 - n]
        sab = px[t + 1] - px[t + 1 - n]
        return (sab - sa * sb / n) / max(1, n - 1)


def portfolio_vol(panel: Panel, w: Dict[str, float], t: int, cfg: StratConfig, ppy: int) -> float:
    """Volatilidad anual de la cartera ``w``. Con ``risk_model="cov"``, covarianza con
    shrinkage hacia correlación constante (Ledoit y Wolf, 2004): estable con pocas
    observaciones y sin suponer que todo se mueve igual."""
    syms = list(w)
    n = cfg.vol_window
    if cfg.risk_model != "cov" or len(syms) < 2:
        return sum(w[s] * panel.vol(s, t, n) for s in syms) * math.sqrt(ppy)
    sd = {s: panel.vol(s, t, n) for s in syms}
    cov = {(a, b): panel.cov(a, b, t, n) for i, a in enumerate(syms) for b in syms[i:]}
    corrs = [cov[(a, b)] / (sd[a] * sd[b]) for i, a in enumerate(syms) for b in syms[i + 1:] if sd[a] * sd[b] > 0]
    rho = sum(corrs) / len(corrs) if corrs else 0.0
    var = 0.0
    for i, a in enumerate(syms):
        for b in syms[i:]:
            c = (1 - cfg.shrink) * cov[(a, b)] + cfg.shrink * (rho * sd[a] * sd[b] if a != b else sd[a] ** 2)
            var += (1 if a == b else 2) * w[a] * w[b] * c
    return math.sqrt(max(var, 0.0) * ppy)


def fast_targets(panel: Panel, t: int, cfg: StratConfig, ppy: int = 365) -> Dict[str, float]:
    scores: Dict[str, float] = {}
    need = max(cfg.lookback, cfg.vol_window)
    for s in panel.syms:
        if not panel.has(s, t, need):
            continue
        c = panel.close[s][t]
        if cfg.kind == "tsmom":
            sma = panel.sma(s, t, cfg.lookback)
            if c > sma:
                scores[s] = c / sma - 1
        elif cfg.kind == "xsmom":
            r = c / panel.close[s][t - cfg.lookback] - 1
            if r > 0:
                scores[s] = r
        else:
            raise ValueError(f"estrategia desconocida: {cfg.kind}")
    chosen = sorted(scores, key=lambda s: -scores[s])[:cfg.max_positions]
    if not chosen:
        return {}
    w = {s: 1.0 / cfg.max_positions for s in chosen}
    pv = portfolio_vol(panel, w, t, cfg, ppy)
    k = min(1.0, cfg.target_vol / pv) if pv > 0 else 1.0
    return {s: x * k for s, x in w.items()}


def dd_multiplier(dd: float, cfg: StratConfig) -> float:
    """Control de caída tipo CPPI (Grossman y Zhou, 1993): exposición completa hasta
    ``dd_start`` x presupuesto y después proporcional al colchón que queda, hasta 0 en el
    presupuesto. La caída máxima acordada pasa a ser parte de la estrategia, no solo un freno."""
    if cfg.dd_budget <= 0:
        return 1.0
    lo = cfg.dd_budget * cfg.dd_start
    if dd <= lo:
        return 1.0
    return max(0.0, (cfg.dd_budget - dd) / (cfg.dd_budget - lo))


def simulate_fast(panel: Panel, cfg: StratConfig, start: int, ppy: int = 365) -> dict:
    """Igual que ``simulate`` (mismos costes, banda y reglas) sobre un ``Panel``; con las
    mejoras apagadas da exactamente el mismo resultado (test de equivalencia)."""
    from collections import deque
    cost = cfg.fee + cfg.slippage
    eq, peak, mdd = 1.0, 1.0, 0.0
    equity = [eq]
    # máximo móvil (cola monótona): con ``dd_window`` > 0 la referencia de la caída se
    # renueva, y el control de caída no se queda en liquidez para siempre
    win: deque = deque([(0, 1.0)])
    w: Dict[str, float] = {}
    base: Dict[str, float] = {}
    entry: Dict[str, float] = {}
    trades: List[float] = []
    close = panel.close
    for t in range(start, panel.n):
        if t > start and w:
            rets = {s: close[s][t] / close[s][t - 1] - 1 for s in w}
            pr = sum(w[s] * rets[s] for s in w)
            eq *= 1 + pr
            w = {s: x * (1 + rets[s]) / (1 + pr) for s, x in w.items()}
            peak = max(peak, eq)
        rebalance = (t - start) % cfg.rebalance == 0
        if rebalance:
            base = fast_targets(panel, t, cfg, ppy)
        if cfg.dd_window > 0:
            k = t - start
            while win and win[-1][1] <= eq:
                win.pop()
            win.append((k, eq))
            while win[0][0] <= k - cfg.dd_window:
                win.popleft()
            ref = win[0][1]
        else:
            ref = peak
        m = dd_multiplier(1 - eq / ref, cfg)
        if rebalance or cfg.dd_budget > 0:
            tgt = {s: x * m for s, x in base.items() if x * m > 1e-12}
            new = dict(w)
            turnover = 0.0
            for s in set(w) | set(tgt):
                cur, want = w.get(s, 0.0), tgt.get(s, 0.0)
                if (want == 0.0) != (cur == 0.0) or abs(want - cur) >= cfg.band:
                    turnover += abs(want - cur)
                    if want == 0.0:
                        new.pop(s, None)
                        trades.append(close[s][t] / entry.pop(s) * (1 - cost) / (1 + cost) - 1)
                    else:
                        if cur == 0.0:
                            entry[s] = close[s][t]
                        new[s] = want
            eq *= 1 - turnover * cost
            w = new
        equity.append(eq)
        peak = max(peak, eq)
        mdd = max(mdd, 1 - eq / peak)
    live = [s for s in panel.syms if close[s][start] == close[s][start] and close[s][-1] == close[s][-1]]
    bh = sum(close[s][-1] / close[s][start] - 1 for s in live) / len(live) if live else 0.0
    return {"equity": equity, "r": trades, "max_drawdown": mdd, "buy_hold": bh, "start": start, "n": panel.n,
            "open": sorted(w)}
