"""Tarjeta de aciertos de las señales: cuánto acierta cada señal, se opere o no.

La cartera puede estar en liquidez semanas enteras (mercado bajista), y entonces
la prueba en papel no dice nada sobre las señales. Aquí se mide cada señal por
separado, se opere o no:

- Cada día y para cada moneda, cada variante dice «largo» (la compraría) o «fuera».
- A *h* días vista (1, 7 y 30) se mira si la moneda subió.
- **Acierto** = % de señales «largo» tras las que la moneda subió.
- **Tasa base** = % de veces que la moneda subió sin señal (todas las monedas y días).
  Una señal solo vale si **acierta más que la tasa base**; acertar el 55 % no
  significa nada si las monedas suben el 55 % de los días de todas formas.
- **Ventaja** = retorno medio tras «largo» menos retorno medio tras «fuera».
- Intervalo de Wilson del 95 % del acierto, con la cuenta de muestras efectiva:
  los retornos a *h* días se solapan, así que n_eff = n / h.

Dos modos:

1. ``score_history``: toda la historia disponible. No hay nada que ajustar: las
   reglas son fijas.
2. Registro en vivo (``record`` + ``score_records``): cada día se guardan las
   señales de hoy y, cuando pasan *h* días, se puntúan con precios nuevos. Esa es
   la prueba fuera de muestra de verdad.
"""
from __future__ import annotations

import json
import math
import os
from typing import Dict, List, Sequence, Tuple

from strategies import Panel, StratConfig, fast_targets

HORIZONS = (1, 7, 30)
_Z95 = 1.959963984540054


def wilson(k: float, n: float, z: float = _Z95) -> Tuple[float, float]:
    if n <= 0:
        return 0.0, 1.0
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, mid - half), min(1.0, mid + half)


class _Acc:
    __slots__ = ("n", "up", "sum", "sq")

    def __init__(self) -> None:
        self.n, self.up, self.sum, self.sq = 0, 0, 0.0, 0.0

    def add(self, r: float) -> None:
        self.n += 1
        self.up += r > 0
        self.sum += r
        self.sq += r * r

    @property
    def var(self) -> float:
        return max(self.sq / self.n - self.mean ** 2, 0.0) if self.n else 0.0

    @property
    def mean(self) -> float:
        return self.sum / self.n if self.n else 0.0

    @property
    def rate(self) -> float:
        return self.up / self.n if self.n else 0.0


def _row(long: _Acc, flat: _Acc, base: _Acc, h: int) -> dict:
    n_eff = long.n / h
    lo, hi = wilson(long.rate * n_eff, n_eff)
    edge = long.mean - flat.mean
    # error típico de la diferencia de medias con muestras efectivas (retornos solapados)
    nl, nf = max(long.n / h, 1e-9), max(flat.n / h, 1e-9)
    se = math.sqrt(long.var / nl + flat.var / nf) if long.n and flat.n else float("inf")
    return {"n": long.n, "n_eff": n_eff, "hit": long.rate, "hit_ci": (lo, hi), "base": base.rate,
            "lift": long.rate - base.rate, "mean_long": long.mean, "mean_flat": flat.mean,
            "edge": edge, "edge_ci": (edge - _Z95 * se, edge + _Z95 * se), "beats_base": lo > base.rate,
            "edge_real": edge - _Z95 * se > 0}


def today_signals(panel: Panel, family: Dict[str, StratConfig], t: int) -> Dict[str, List[str]]:
    """{variante: [monedas en «largo»]} con datos hasta el cierre ``t``."""
    return {k: sorted(fast_targets(panel, t, c)) for k, c in family.items()}


def score_history(panel: Panel, family: Dict[str, StratConfig], start: int,
                  horizons: Sequence[int] = HORIZONS) -> Dict[str, Dict[int, dict]]:
    """Tarjeta de aciertos de cada variante (y del «conjunto»: largo si alguna variante lo está)."""
    close = panel.close
    acc: Dict[str, Dict[int, Tuple[_Acc, _Acc]]] = {k: {h: (_Acc(), _Acc()) for h in horizons}
                                                    for k in list(family) + ["conjunto"]}
    base = {h: _Acc() for h in horizons}
    for t in range(start, panel.n - min(horizons)):
        sig = today_signals(panel, family, t)
        anyl = set().union(*sig.values()) if sig else set()
        for s in panel.syms:
            c0 = close[s][t]
            if c0 != c0:
                continue
            fwd = {}
            for h in horizons:
                if t + h < panel.n and close[s][t + h] == close[s][t + h]:
                    fwd[h] = close[s][t + h] / c0 - 1
            if not fwd:
                continue
            for h, r in fwd.items():
                base[h].add(r)
                for k, coins in list(sig.items()) + [("conjunto", sorted(anyl))]:
                    (acc[k][h][0] if s in coins else acc[k][h][1]).add(r)
    return {k: {h: _row(acc[k][h][0], acc[k][h][1], base[h], h) for h in horizons} for k in acc}


# --------------------------------------------------------------------------- registro en vivo

def record(path: str, day_ms: int, signals: Dict[str, List[str]], prices: Dict[str, float]) -> bool:
    """Añade las señales del día (una vez por día). Devuelve False si ya estaba."""
    rows = load(path)
    if any(r["day"] == day_ms for r in rows):
        return False
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"day": day_ms, "signals": signals, "prices": prices}, ensure_ascii=False) + "\n")
    return True


def load(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def score_records(rows: Sequence[dict], horizons: Sequence[int] = HORIZONS) -> Dict[str, Dict[int, dict]]:
    """Puntúa las señales registradas en vivo con los precios registrados días después."""
    by_day = {r["day"]: r for r in rows}
    day = 86_400_000
    names = sorted({k for r in rows for k in r["signals"]}) + ["conjunto"]
    acc = {k: {h: (_Acc(), _Acc()) for h in horizons} for k in names}
    base = {h: _Acc() for h in horizons}
    for r in rows:
        anyl = set().union(*r["signals"].values()) if r["signals"] else set()
        for h in horizons:
            later = by_day.get(r["day"] + h * day)
            if not later:
                continue
            for s, p0 in r["prices"].items():
                p1 = later["prices"].get(s)
                if not p0 or not p1:
                    continue
                ret = p1 / p0 - 1
                base[h].add(ret)
                for k in names:
                    coins = anyl if k == "conjunto" else set(r["signals"].get(k, []))
                    (acc[k][h][0] if s in coins else acc[k][h][1]).add(ret)
    return {k: {h: _row(acc[k][h][0], acc[k][h][1], base[h], h) for h in horizons} for k in names}


def format_card(card: Dict[str, Dict[int, dict]], horizons: Sequence[int] = HORIZONS) -> List[str]:
    lines = ["  señal       " + "".join(f"| a {h:>2} d: acierto (IC95 %)  base  ventaja (IC95 %)       "
                                        for h in horizons)]
    for k, rows in card.items():
        cells = []
        for h in horizons:
            r = rows.get(h)
            if not r or r["n"] == 0:
                cells.append("| " + "sin datos".ljust(48))
                continue
            mark = "✔" if r["beats_base"] else " "
            emark = "✔" if r["edge_real"] else " "
            cells.append(f"| {r['hit']:5.0%} ({r['hit_ci'][0]:.0%}-{r['hit_ci'][1]:.0%}){mark} {r['base']:4.0%} "
                         f"{r['edge']:+6.2%} ({r['edge_ci'][0]:+.1%}, {r['edge_ci'][1]:+.1%}){emark}  ")
        lines.append(f"  {k:<11} " + "".join(cells))
    lines.append("  ✔ tras el acierto: supera la tasa base con un 95 % de confianza; ✔ tras la ventaja: el retorno "
                 "tras «largo» supera al de «fuera» con un 95 % de confianza (muestras efectivas n/h)")
    return lines
