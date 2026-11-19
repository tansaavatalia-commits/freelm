"""Momentum combinado en PAPEL: prueba de 20 días sin dinero real.

La estrategia es el «conjunto» de ``strategies.py``: las 10 variantes de
momentum (5 de tendencia, 5 relativas) a partes iguales, sin elegir ninguna,
con covarianza real y volatilidad objetivo del 5 %. Es la candidata más sólida
de ``classic`` (2019-2026, estable en todos los días de inicio), pero NO está
validada de forma robusta (el PBO de la familia depende del calendario), el sesgo
de supervivencia no está descartado y falta probarla con datos nuevos. Solo papel.

Una vez al día, tras el cierre de la vela diaria (00:00 UTC):

1. Se comprueban los datos (integridad y frescura). Con datos dudosos, ese día no se opera.
2. Cada variante actualiza sus pesos con el movimiento de precios del día y se
   reequilibra según su regla: tendencia a diario, relativo cada 7 días.
3. La cartera en papel es la media de las 10. Paga comisión y deslizamiento
   por lo que de verdad rota, una vez netas las compras y ventas entre variantes.
4. Si la caída desde el máximo supera el 10 %, se pasa todo a liquidez y se detiene.

El estado vive en ``momentum_state.json`` y la curva en ``momentum_track.jsonl``.
Cada día se procesa una sola vez (idempotente). Nunca envía órdenes a ningún exchange.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import replace
from typing import Dict, List, Optional, Sequence, Tuple

from market import Candle
from strategies import Panel, StratConfig, default_family, fast_targets

DAY_MS = 86_400_000
PAPER_DAYS = 20
MAX_DD = 0.10


def closed_daily(candles: Sequence[Candle], now_ms: int) -> List[Candle]:
    """Quita la vela diaria que aún no ha cerrado."""
    return [c for c in candles if c.time + DAY_MS <= now_ms]


def signature(family: Dict[str, StratConfig]) -> str:
    """Huella de la configuración: si cambia, la prueba en papel empieza de cero."""
    return json.dumps(sorted((k, sorted(c.__dict__.items())) for k, c in family.items()), default=str)


def new_state(cash: float, family: Dict[str, StratConfig]) -> dict:
    return {"cash0": cash, "equity": cash, "peak": cash, "last_day": None, "start_day": None, "halted": False,
            "books": {k: {} for k in family}, "weights": {}, "turnover": 0.0, "days": 0, "basket0": {},
            "config": signature(family)}


def _drift(w: Dict[str, float], rets: Dict[str, float]) -> Dict[str, float]:
    if not w:
        return {}
    pr = sum(x * rets.get(s, 0.0) for s, x in w.items())
    return {s: x * (1 + rets.get(s, 0.0)) / (1 + pr) for s, x in w.items()}


def step(state: dict, data: Dict[str, List[Candle]], family: Dict[str, StratConfig]) -> Tuple[dict, dict]:
    """Procesa el último día cerrado de ``data`` (cada moneda con su historia, sin recortar).
    Devuelve (estado, informe del día)."""
    panel = Panel(data)
    closes = panel.close
    t = panel.n - 1
    day = panel.times[t]
    rep = {"day": day, "skipped": None, "trades": [], "weights": {}}
    if state["last_day"] is not None and day <= state["last_day"]:
        rep["skipped"] = "día ya procesado"
        return state, rep
    if t < max(c.warmup for c in family.values()):
        rep["skipped"] = "historia insuficiente"
        return state, rep
    first = state["last_day"] is None
    prev_t = None if first else next((i for i in range(t, -1, -1) if panel.times[i] == state["last_day"]), None)
    old = dict(state["weights"])
    # 1) movimiento desde el último día procesado (si faltan días, el retorno los cubre)
    if not first and prev_t is not None and old:
        rets = {s: closes[s][t] / closes[s][prev_t] - 1 for s in closes}
        pr = sum(x * rets[s] for s, x in old.items())
        state["equity"] *= 1 + pr
        old = _drift(old, rets)
        state["books"] = {k: _drift(w, rets) for k, w in state["books"].items()}
    state["peak"] = max(state["peak"], state["equity"])
    dd = 1 - state["equity"] / state["peak"]
    if state["halted"] or dd > MAX_DD:
        if not state["halted"]:
            rep["trades"] = [(s, "venta (caída > 10 %)", x) for s, x in old.items()]
            state["equity"] *= 1 - sum(old.values()) * (family[next(iter(family))].fee
                                                         + family[next(iter(family))].slippage)
        state.update(halted=True, weights={}, books={k: {} for k in family})
        rep["skipped"] = f"detenido: caída {dd:.1%} > {MAX_DD:.0%}"
        state["last_day"] = day
        return state, rep
    # 2) cada variante decide con datos hasta el cierre de hoy (incluido)
    state["start_day"] = state["start_day"] or day
    n_day = (day - state["start_day"]) // DAY_MS
    for k, cfg in family.items():
        if n_day % cfg.rebalance:
            continue
        tgt = fast_targets(panel, t, cfg)
        w = state["books"].get(k, {})
        new = dict(w)
        for s in set(w) | set(tgt):
            cur, want = w.get(s, 0.0), tgt.get(s, 0.0)
            if (want == 0.0) != (cur == 0.0) or abs(want - cur) >= cfg.band:
                if want == 0.0:
                    new.pop(s, None)
                else:
                    new[s] = want
        state["books"][k] = new
    # 3) cartera = media de las variantes; se paga solo la rotación neta
    combined: Dict[str, float] = {}
    for w in state["books"].values():
        for s, x in w.items():
            combined[s] = combined.get(s, 0.0) + x / len(family)
    cost = family[next(iter(family))].fee + family[next(iter(family))].slippage
    turnover = sum(abs(combined.get(s, 0.0) - old.get(s, 0.0)) for s in set(old) | set(combined))
    state["equity"] *= 1 - turnover * cost
    state["turnover"] += turnover
    for s in sorted(set(old) | set(combined)):
        d = combined.get(s, 0.0) - old.get(s, 0.0)
        if abs(d) > 1e-9:
            rep["trades"].append((s, "compra" if d > 0 else "venta", abs(d)))
    state["weights"] = {s: x for s, x in combined.items() if x > 1e-9}
    if first:
        state["basket0"] = {s: closes[s][t] for s in closes}
    state["last_day"] = day
    state["days"] += 0 if first else 1
    state["peak"] = max(state["peak"], state["equity"])
    rep["weights"] = dict(state["weights"])
    rep["basket"] = (sum(closes[s][t] / state["basket0"][s] - 1 for s in state["basket0"] if s in closes)
                     / max(1, len(state["basket0"])))
    return state, rep


def summary(state: dict, track: Sequence[dict]) -> dict:
    eq = [r["equity"] for r in track] or [state["equity"]]
    peak, mdd = eq[0], 0.0
    for e in eq:
        peak = max(peak, e)
        mdd = max(mdd, 1 - e / peak)
    ret = state["equity"] / state["cash0"] - 1
    basket = track[-1].get("basket", 0.0) if track else 0.0
    done = state["days"] >= PAPER_DAYS
    passed = done and ret > 0 and mdd <= MAX_DD and not state["halted"]
    return {"days": state["days"], "return": ret, "max_drawdown": mdd, "basket": basket, "done": done,
            "passed": passed, "halted": state["halted"], "weights": state["weights"]}


def load(path: str, cash: float, family: Dict[str, StratConfig]) -> dict:
    """Estado guardado; si se guardó con otra configuración, uno nuevo con ``restarted``."""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            st = json.load(fh)
        if st.get("config") == signature(family):
            return st
        fresh = new_state(cash, family)
        fresh["restarted"] = f"configuración cambiada (antes: día {st.get('days', 0)})"
        return fresh
    return new_state(cash, family)


def save(path: str, state: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def family_for(target_vol: float = 0.05, fee: Optional[float] = None, risk_model: str = "cov") -> Dict[str, StratConfig]:
    """Por defecto, la configuración VALIDADA por ``classic`` (covarianza, volatilidad 5 %)."""
    fam = default_family()
    return {k: replace(c, target_vol=target_vol, risk_model=risk_model, **({"fee": fee} if fee is not None else {}))
            for k, c in fam.items()}


def utc(day_ms: int) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(day_ms / 1000))
