"""Datos del cuadro de mando (Momentum Bot Monitor) a partir de la prueba en papel.

``python bot.py dashboard-data --dir <estado> --out <carpeta>`` escribe seis JSON
(una lista de filas cada uno) que el cuadro de mando de claude.ai muestra:

- ``paper.json``: días de la prueba en papel (capital, bot y cesta, caída);
- ``radar.json``: estado de cada moneda en el último cierre diario;
- ``scorecard_history.json`` / ``scorecard_live.json``: tarjeta de aciertos
  (historia con reglas fijas / señales registradas en vivo);
- ``backtest.json``: valor semanal de 1 € en el conjunto y en la cesta, 2019-2026;
- ``strategies.json``: resultados y validación de cada variante.

Usa la misma configuración que la prueba en papel (``momentum_paper.family_for``).
"""
from __future__ import annotations

import json
import math
import os
import time
from typing import Dict, List, Optional, Sequence

import momentum_paper as mp
import signals as sg
import strategies as st
import validation as v
from market import Candle

N_TRIALS = 106  # pruebas hechas en la investigación (se descuentan en el Deflated Sharpe)


def _day(ms: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ms / 1000))


def _card_rows(card: Dict[str, Dict[int, dict]]) -> List[dict]:
    out = []
    for k, hs in card.items():
        for h, r in hs.items():
            if not r["n"]:
                continue
            out.append({"signal": k, "horizon_days": int(h), "n": r["n"], "hit": round(r["hit"], 4),
                        "base": round(r["base"], 4), "edge": round(r["edge"], 5),
                        "edge_lo": round(r["edge_ci"][0], 5), "edge_hi": round(r["edge_ci"][1], 5),
                        "edge_real": bool(r["edge_real"])})
    return out


def build(state_dir: str, raw: Dict[str, Sequence[Candle]], symbols: Optional[Sequence[str]] = None) -> Dict[str, list]:
    """Filas de los seis conjuntos de datos. ``raw``: velas DIARIAS ya cerradas por moneda."""
    out: Dict[str, list] = {}
    state = {}
    sp = os.path.join(state_dir, "momentum_state.json")
    if os.path.exists(sp):
        with open(sp, encoding="utf-8") as fh:
            state = json.load(fh)
    cash0 = state.get("cash0", 100.0)
    track_path = os.path.join(state_dir, "momentum_track.jsonl")
    track = []
    if os.path.exists(track_path):
        with open(track_path, encoding="utf-8") as fh:
            track = [json.loads(x) for x in fh if x.strip()]
    peak, rows = 0.0, []
    for r in track:
        peak = max(peak, r["equity"])
        rows.append({"date": _day(r["t"] * 1000), "equity": round(r["equity"], 4),
                     "bot_pct": round(r["equity"] / cash0 - 1, 6), "basket_pct": round(r.get("basket", 0.0), 6),
                     "drawdown": round(1 - r["equity"] / peak, 6) if peak else 0.0})
    out["paper"] = rows

    pan = st.Panel(raw)
    fam = mp.family_for()
    t = pan.n - 1
    sig = sg.today_signals(pan, fam, t)
    radar = []
    for s in (symbols or pan.syms):
        c = pan.close[s]
        if not pan.has(s, t, 200):
            continue
        radar.append({"symbol": s.replace("USDT", ""), "price": c[t], "votes": sum(s in x for x in sig.values()),
                      "vs_sma50": round(c[t] / pan.sma(s, t, 50) - 1, 4), "vs_sma200": round(c[t] / pan.sma(s, t, 200) - 1, 4),
                      "ret_7d": round(c[t] / c[t - 7] - 1, 4), "ret_28d": round(c[t] / c[t - 28] - 1, 4),
                      "vol_30d": round(pan.vol(s, t, 30) * math.sqrt(365), 4)})
    out["radar"] = radar

    start = max(c.warmup for c in fam.values())
    out["scorecard_history"] = _card_rows(sg.score_history(pan, fam, start))
    recs = [r for r in sg.load(os.path.join(state_dir, "senales.jsonl")) if r["day"] >= state.get("start_day", 0)]
    out["scorecard_live"] = _card_rows(sg.score_records(recs)) if recs else []

    res = {k: st.simulate_fast(pan, c, start) for k, c in fam.items()}
    ens = st.ensemble(res)
    eq = ens["equity"]
    bt, pk = [], 1.0
    first = [s for s in pan.syms if pan.close[s][start] == pan.close[s][start]]
    for i in range(len(eq)):
        pk = max(pk, eq[i])
        if i % 7 and i != len(eq) - 1:
            continue
        ti = min(start + max(i - 1, 0), pan.n - 1)
        vals = [pan.close[s][ti] / pan.close[s][start] for s in first if pan.close[s][ti] == pan.close[s][ti]]
        bt.append({"date": _day(pan.times[ti]), "bot": round(eq[i], 5), "drawdown": round(1 - eq[i] / pk, 5),
                   "basket": round(sum(vals) / len(vals), 5) if vals else None})
    out["backtest"] = bt

    years = max((pan.n - start) / 365, 1e-9)
    rep = v.judge({**res, "conjunto": ens}, st.neighbours(fam), N_TRIALS)
    out["strategies"] = [{"strategy": k, "annual": round((1 + x["return"]) ** (1 / years) - 1, 4),
                          "total": round(x["return"], 4), "max_drawdown": round(x["max_drawdown"], 4),
                          "trades": x["trades"], "win_rate": round(x["win_rate"], 4), "dsr": round(x["dsr"], 3),
                          "passes_all_tests": bool(x["validated"])} for k, x in rep["strategies"].items()]
    return out


def write(out_dir: str, data: Dict[str, list]) -> List[str]:
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for name, rows in data.items():
        p = os.path.join(out_dir, name + ".json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, separators=(",", ":"))
        paths.append(p)
    return paths
