"""Informe de rendimiento al estilo quantstats (github.com/ranaroussi/quantstats),
sin pandas ni dependencias: las métricas que usan los fondos para juzgar una
estrategia, no solo «cuánto ganó».

- Sortino: rentabilidad por unidad de riesgo a la baja (solo cuentan las caídas).
- Calmar: rentabilidad anual / caída máxima.
- Duración de la peor caída: cuánto tardó en recuperar el máximo anterior.
- Rendimiento por días y por meses: % de días positivos, mejor y peor día.
- Operaciones: esperanza por operación, ratio ganancia/pérdida, rachas.
"""
from __future__ import annotations

import math
import time
from typing import Dict, List, Optional, Sequence


def _day(ms: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ms / 1000))


def performance(equity: Sequence[float], times_ms: Sequence[float], periods_per_year: int,
                trades: Optional[Sequence[object]] = None) -> Dict[str, object]:
    """``equity`` y ``times_ms`` alineados (una entrada por vela)."""
    n = len(equity)
    if n < 2:
        return {}
    rets = [equity[i] / equity[i - 1] - 1 for i in range(1, n) if equity[i - 1] > 0]
    mean = sum(rets) / len(rets)
    downside = math.sqrt(sum(min(0.0, r) ** 2 for r in rets) / len(rets))
    sortino = mean / downside * math.sqrt(periods_per_year) if downside > 0 else 0.0
    total = equity[-1] / equity[0] - 1
    years = (n - 1) / periods_per_year
    annual = (1 + total) ** (1 / years) - 1 if total > -1 and years > 0 else -1.0

    # caída máxima y su duración (en velas, hasta recuperar el máximo)
    peak, peak_i, mdd, longest, cur_start = equity[0], 0, 0.0, 0, None
    for i, e in enumerate(equity):
        if e >= peak:
            if cur_start is not None:
                longest = max(longest, i - cur_start)
                cur_start = None
            peak, peak_i = e, i
        else:
            mdd = max(mdd, 1 - e / peak)
            if cur_start is None:
                cur_start = peak_i
    if cur_start is not None:
        longest = max(longest, n - 1 - cur_start)
    calmar = annual / mdd if mdd > 0 else 0.0

    # por días y por meses (último valor de cada periodo)
    last_by_day: Dict[str, float] = {}
    for e, t in zip(equity, times_ms):
        last_by_day[_day(t)] = e
    days = list(last_by_day.items())
    day_rets = [(d, days[i][1] / days[i - 1][1] - 1) for i, (d, _) in enumerate(days) if i > 0]
    months: Dict[str, List[float]] = {}
    prev = equity[0]
    for d, e in days:
        m = d[:7]
        months.setdefault(m, [prev, e])[1] = e
        prev = e
    monthly = {m: v[1] / v[0] - 1 for m, v in months.items()}

    out: Dict[str, object] = {
        "total": total, "annual": annual, "sortino": sortino, "calmar": calmar, "max_drawdown": mdd,
        "dd_days": longest / (periods_per_year / 365), "monthly": monthly,
        "pos_days": sum(1 for _, r in day_rets if r > 0) / len(day_rets) if day_rets else 0.0,
        "best_day": max(day_rets, key=lambda x: x[1]) if day_rets else None,
        "worst_day": min(day_rets, key=lambda x: x[1]) if day_rets else None,
    }
    if trades:
        pnl = [float(getattr(t, "pnl", 0.0)) for t in trades]
        wins = [p for p in pnl if p > 0]
        losses = [-p for p in pnl if p <= 0]
        streak_w = streak_l = cw = cl = 0
        for p in pnl:
            cw, cl = (cw + 1, 0) if p > 0 else (0, cl + 1)
            streak_w, streak_l = max(streak_w, cw), max(streak_l, cl)
        out.update({
            "expectancy": sum(pnl) / len(pnl),
            "payoff": (sum(wins) / len(wins)) / (sum(losses) / len(losses)) if wins and losses else 0.0,
            "win_streak": streak_w, "loss_streak": streak_l,
        })
    return out


def format_performance(p: Dict[str, object], currency: str = "€") -> List[str]:
    if not p:
        return ["  (sin datos suficientes para el informe)"]
    lines = [
        f"  Sortino {p['sortino']:.2f} · Calmar {p['calmar']:.2f} · rentabilidad anual {p['annual']:+.1%}",
        f"  peor caída {p['max_drawdown']:.2%}, tardó {p['dd_days']:.0f} días en recuperarse"
        f" · días positivos {p['pos_days']:.0%}",
    ]
    if p.get("best_day"):
        (bd, br), (wd, wr) = p["best_day"], p["worst_day"]  # type: ignore[misc]
        lines.append(f"  mejor día {bd} {br:+.2%} · peor día {wd} {wr:+.2%}")
    if "expectancy" in p:
        lines.append(f"  por operación: esperanza {p['expectancy']:+.2f} {currency}, ganancia/pérdida media "
                     f"{p['payoff']:.2f}, rachas máx. {p['win_streak']} ganadoras / {p['loss_streak']} perdedoras")
    monthly = p.get("monthly") or {}
    if monthly:
        lines.append("  por meses: " + " · ".join(f"{m} {r:+.1%}" for m, r in list(monthly.items())[-12:]))
    return lines
