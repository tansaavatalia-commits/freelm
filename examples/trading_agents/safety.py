"""Seguridad operativa: no decidir con datos dudosos y dejar rastro de cada decisión.

- ``check_window``: valida la ventana de velas de un símbolo antes de usarla. Si
  algo no cuadra (huecos, velas fuera de orden, precios imposibles, saltos
  absurdos), el motor NO decide sobre ese símbolo en esa vela.
- ``check_fresh``: en vivo, la última vela cerrada tiene que ser reciente; si el
  exchange devuelve datos atrasados, no se opera.
- ``DecisionJournal``: diario auditable (JSONL, un archivo por día UTC) con cada
  decisión: veredicto de cada equipo, vetos y su motivo, probabilidad
  verificada, órdenes abiertas y cerradas, notas y avisos.
"""
from __future__ import annotations

import json
import math
import os
import time
from typing import Any, Dict, List, Optional, Sequence

from market import Candle

MAX_JUMP = 0.35  # un cierre que se mueve más de un 35 % en una sola vela se trata como dato corrupto


def candle_interval_ms(window: Sequence[Candle]) -> Optional[int]:
    """Intervalo típico (moda de las diferencias) de la ventana."""
    diffs = [window[i].time - window[i - 1].time for i in range(max(1, len(window) - 50), len(window))]
    diffs = [d for d in diffs if d > 0]
    if not diffs:
        return None
    return max(set(diffs), key=diffs.count)


def check_window(window: Sequence[Candle], lookback: int = 30) -> List[str]:
    """Lista de problemas (vacía = datos coherentes) en las últimas ``lookback`` velas."""
    problems: List[str] = []
    if len(window) < 2:
        return ["ventana demasiado corta"]
    iv = candle_interval_ms(window)
    tail = window[-lookback:]
    for i, c in enumerate(tail):
        vals = (c.open, c.high, c.low, c.close)
        if any((not math.isfinite(v)) or v <= 0 for v in vals) or not math.isfinite(c.volume) or c.volume < 0:
            problems.append(f"precio o volumen inválido en {c.time}")
            break
        if c.high < max(c.open, c.close) or c.low > min(c.open, c.close) or c.high < c.low:
            problems.append(f"vela incoherente (máximo/mínimo) en {c.time}")
            break
        if i:
            prev = tail[i - 1]
            gap = c.time - prev.time
            if gap <= 0:
                problems.append(f"velas fuera de orden o repetidas en {c.time}")
                break
            if iv and gap > iv * 1.5:
                problems.append(f"faltan {round(gap / iv) - 1} velas antes de {c.time}")
                break
            if abs(c.close / prev.close - 1) > MAX_JUMP:
                problems.append(f"salto de precio de {c.close / prev.close - 1:+.0%} en una vela ({c.time})")
                break
    return problems


def check_fresh(window: Sequence[Candle], interval_s: int, now_s: Optional[float] = None) -> Optional[str]:
    """En vivo: la última vela CERRADA debe haber abierto hace como mucho 2 intervalos."""
    now_s = time.time() if now_s is None else now_s
    age = now_s - window[-1].time / 1000
    if age > 2 * interval_s + 60:
        return f"datos atrasados: la última vela tiene {age / 60:.0f} min"
    return None


class DecisionJournal:
    """Diario de decisiones en JSONL (un archivo por día UTC). Nunca guarda claves."""

    def __init__(self, directory: str) -> None:
        self.dir = directory
        os.makedirs(directory, exist_ok=True)

    def _path(self, t_ms: int) -> str:
        return os.path.join(self.dir, "decisiones-" + time.strftime("%Y%m%d", time.gmtime(t_ms / 1000)) + ".jsonl")

    def write(self, t_ms: int, record: Dict[str, Any]) -> None:
        rec = {"t": t_ms, "utc": time.strftime("%Y-%m-%d %H:%M", time.gmtime(t_ms / 1000)), **record}
        with open(self._path(t_ms), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")

    def step(self, t_ms: int, rep: Any, prices: Dict[str, float], equity: float) -> None:
        """Una línea por símbolo con su decisión, y otra con el resumen de cartera."""
        for sym, d in rep.decisions.items():
            self.write(t_ms, {
                "tipo": "decision", "simbolo": sym, "precio": prices.get(sym), "regimen": d.regime,
                "consejo": round(d.score, 4), "acuerdo": round(d.agreement, 4), "clave": d.key,
                "equipos": {s.agent: round(s.score, 3) for s in d.teams},
                "vetos": d.vetoes, "aprobada": d.approved, "prob_verificada": round(d.p_win, 4),
                "perfil_objetivo_atr": d.exit_target,
            })
        for p in rep.opened:
            self.write(t_ms, {"tipo": "apertura", "simbolo": p.symbol, "entrada": p.entry, "cantidad": p.qty,
                              "stop": p.stop, "objetivo": p.target, "prob_verificada": p.p_win, "motivo": p.reason})
        for c in rep.closed:
            self.write(t_ms, {"tipo": "cierre", "simbolo": c.symbol, "entrada": c.entry, "salida": c.exit,
                              "resultado": round(c.pnl, 6), "r": round(c.r, 4), "motivo": c.why})
        self.write(t_ms, {"tipo": "cartera", "capital": round(equity, 6), "evento": rep.event, "notas": rep.notes,
                          "datos_invalidos": getattr(rep, "data_issues", {})})
