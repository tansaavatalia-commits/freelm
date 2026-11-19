"""Validación estadística de estrategias: ¿la ventaja es real o es suerte/sobreajuste?

Se usa para una FAMILIA de estrategias (todas las variantes probadas), porque
probar muchas y quedarse con la mejor es la causa principal de backtests que
luego fallan en real. Pruebas (todas sin dependencias):

- **Walk-forward**: el motor aprende solo con el pasado (en línea, sin mirar el
  futuro) y opera en un tramo largo nunca visto, partido en varios sub-tramos.
- **Deflated Sharpe Ratio** (Bailey y López de Prado, 2014): probabilidad de que
  el Sharpe sea mayor que el que saldría *por azar* siendo el mejor de N
  pruebas, corrigiendo asimetría y colas gruesas.
- **PBO, Probability of Backtest Overfitting** (Bailey, Borwein, López de Prado
  y Zhu, 2014), por CSCV: con qué frecuencia la mejor estrategia dentro de
  muestra queda por debajo de la mediana fuera de muestra.
- **Sensibilidad**: los parámetros vecinos también tienen que ganar; si solo
  gana un valor exacto, es casualidad.
- **Bootstrap** del resultado medio por operación (en R): intervalo del 95 %.
"""
from __future__ import annotations

import itertools
import math
import random
import statistics
from typing import Dict, List, Optional, Sequence, Tuple

_N = statistics.NormalDist()
EULER = 0.5772156649015329

# criterios para declarar una estrategia VALIDADA (todos a la vez)
MIN_TRADES = 30
MAX_DD = 0.10
MIN_DSR = 0.95
MAX_PBO = 0.25
MIN_POSITIVE_SEGMENTS = 0.75  # fracción de sub-tramos del walk-forward con resultado positivo


def returns_from_equity(equity: Sequence[float]) -> List[float]:
    return [equity[i] / equity[i - 1] - 1 for i in range(1, len(equity)) if equity[i - 1] > 0]


def moments(rets: Sequence[float]) -> Tuple[float, float, float, float]:
    """(media, desviación, asimetría, curtosis NO en exceso: normal = 3)."""
    n = len(rets)
    if n < 2:
        return 0.0, 0.0, 0.0, 3.0
    m = sum(rets) / n
    var = sum((r - m) ** 2 for r in rets) / n
    sd = math.sqrt(var)
    if sd <= 1e-15:
        return m, 0.0, 0.0, 3.0
    skew = sum((r - m) ** 3 for r in rets) / n / sd ** 3
    kurt = sum((r - m) ** 4 for r in rets) / n / sd ** 4
    return m, sd, skew, kurt


def sharpe(rets: Sequence[float]) -> float:
    """Sharpe por periodo (sin anualizar), como lo usan PSR y DSR."""
    m, sd, _, _ = moments(rets)
    return m / sd if sd > 0 else 0.0


def probabilistic_sharpe(rets: Sequence[float], sr_benchmark: float = 0.0) -> float:
    """PSR: probabilidad de que el Sharpe verdadero supere ``sr_benchmark``."""
    n = len(rets)
    m, sd, skew, kurt = moments(rets)
    if n < 3 or sd <= 0:
        return 0.0
    sr = m / sd
    den = 1 - skew * sr + (kurt - 1) / 4 * sr * sr
    if den <= 0:
        return 0.0
    return _N.cdf((sr - sr_benchmark) * math.sqrt(n - 1) / math.sqrt(den))


def expected_max_sharpe(n_trials: int, var_sr: float) -> float:
    """Sharpe esperado del MEJOR de ``n_trials`` estrategias sin ventaja (Sharpe real 0)."""
    if n_trials < 2 or var_sr <= 0:
        return 0.0
    a = _N.inv_cdf(1 - 1 / n_trials)
    b = _N.inv_cdf(1 - 1 / (n_trials * math.e))
    return math.sqrt(var_sr) * ((1 - EULER) * a + EULER * b)


def deflated_sharpe(rets: Sequence[float], n_trials: int, var_sr: float) -> float:
    """DSR = PSR contra el Sharpe que daría el azar tras ``n_trials`` pruebas."""
    return probabilistic_sharpe(rets, expected_max_sharpe(n_trials, var_sr))


def pbo_cscv(matrix: Sequence[Sequence[float]], blocks: int = 16) -> Optional[float]:
    """PBO por validación cruzada combinatoria simétrica.

    ``matrix``: filas = periodos, columnas = estrategias (retornos por periodo).
    Se parte en ``blocks`` bloques; para cada forma de elegir la mitad como
    «dentro de muestra», se toma la mejor estrategia ahí y se mira su puesto
    relativo en la otra mitad. PBO = fracción de veces que queda en la mitad
    peor. 0 = la selección generaliza; ~0,5 = da igual elegir al azar.
    Devuelve None si no hay al menos 2 estrategias distintas."""
    t = len(matrix)
    n = len(matrix[0]) if t else 0
    if n < 2 or t < blocks * 2:
        return None
    blocks -= blocks % 2
    size = t // blocks
    # sumas por bloque y estrategia: cada Sharpe sale de sumas, sin recorrer las filas otra vez
    s1 = [[0.0] * n for _ in range(blocks)]
    s2 = [[0.0] * n for _ in range(blocks)]
    for b in range(blocks):
        for row in matrix[b * size:(b + 1) * size]:
            for j, r in enumerate(row):
                s1[b][j] += r
                s2[b][j] += r * r
    cols = [[row[j] for row in matrix] for j in range(n)]
    if all(c == cols[0] for c in cols[1:]):
        return None

    def perf(sel: Sequence[int]) -> List[float]:
        cnt = size * len(sel)
        out = []
        for j in range(n):
            a = sum(s1[b][j] for b in sel)
            q = sum(s2[b][j] for b in sel)
            m = a / cnt
            var = max(q / cnt - m * m, 0.0)
            out.append(m / math.sqrt(var) if var > 1e-18 else 0.0)
        return out

    below = total = 0
    every = list(range(blocks))
    for ins in itertools.combinations(every, blocks // 2):
        outs = [b for b in every if b not in ins]
        p_in, p_out = perf(ins), perf(outs)
        best = max(range(n), key=lambda j: p_in[j])
        # puesto relativo (con empates repartidos) de la elegida fuera de muestra
        worse = sum(1 for x in p_out if x < p_out[best])
        ties = sum(1 for x in p_out if x == p_out[best]) - 1
        omega = (worse + 0.5 * ties + 1) / (n + 1)
        total += 1
        below += math.log(omega / (1 - omega)) <= 0
    return below / total if total else None


def bootstrap_mean_ci(xs: Sequence[float], n_boot: int = 4000, seed: int = 0,
                      level: float = 0.95) -> Tuple[float, float]:
    if len(xs) < 2:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    k = len(xs)
    xs = list(xs)
    # random.choices (en C): el mismo remuestreo con reemplazo, ~20 veces más rápido
    # que un bucle de rng.choice en Python
    means = sorted(sum(rng.choices(xs, k=k)) / k for _ in range(n_boot))
    lo = means[int(n_boot * (1 - level) / 2)]
    hi = means[min(n_boot - 1, int(n_boot * (1 + level) / 2))]
    return lo, hi


def segment_returns(equity: Sequence[float], k: int = 4) -> List[float]:
    n = len(equity) - 1
    if n < k:
        return [equity[-1] / equity[0] - 1]
    cuts = [round(i * n / k) for i in range(k + 1)]
    return [equity[cuts[i + 1]] / equity[cuts[i]] - 1 for i in range(k)]


def judge(results: Dict[str, dict], neighbours: Dict[str, List[str]], n_trials: int,
          blocks: int = 16) -> dict:
    """Aplica todas las pruebas a una familia de resultados de walk-forward.

    ``results[nombre]`` = {"equity": [...], "r": [R de cada operación], "max_drawdown": x}.
    Devuelve el PBO de la familia y, por estrategia, métricas, DSR y veredicto."""
    names = list(results)
    rets = {k: returns_from_equity(results[k]["equity"]) for k in names}
    t = min(len(v) for v in rets.values()) if rets else 0
    srs = [sharpe(rets[k]) for k in names if results[k]["r"]]
    var_sr = statistics.pvariance(srs) if len(srs) > 1 else 0.0
    matrix = [[rets[k][i] for k in names] for i in range(t)]
    pbo = pbo_cscv(matrix, blocks) if t else None
    out: Dict[str, dict] = {}
    for k in names:
        r = results[k]
        eq = r["equity"]
        total = eq[-1] / eq[0] - 1
        segs = segment_returns(eq)
        dsr = deflated_sharpe(rets[k], n_trials, var_sr) if r["r"] else 0.0
        ci = bootstrap_mean_ci(r["r"]) if len(r["r"]) >= 10 else (float("nan"), float("nan"))
        nb = [results[x]["equity"][-1] / results[x]["equity"][0] - 1 for x in neighbours.get(k, [])]
        why: List[str] = []
        if len(r["r"]) < MIN_TRADES:
            why.append(f"pocas operaciones ({len(r['r'])} < {MIN_TRADES})")
        if total <= 0:
            why.append(f"no gana ({total:+.2%})")
        if r["max_drawdown"] > MAX_DD:
            why.append(f"caída {r['max_drawdown']:.1%} > {MAX_DD:.0%}")
        pos = sum(1 for s in segs if s > 0) / len(segs)
        if pos < MIN_POSITIVE_SEGMENTS:
            why.append(f"solo {pos:.0%} de los tramos en positivo")
        if dsr < MIN_DSR:
            why.append(f"Deflated Sharpe {dsr:.2f} < {MIN_DSR}")
        if not (ci[0] > 0):
            why.append("el intervalo del 95 % de la media por operación incluye pérdidas" if ci[0] == ci[0]
                       else "sin operaciones suficientes para el intervalo")
        if nb and min(nb) <= 0:
            why.append(f"parámetros vecinos pierden ({min(nb):+.2%})")
        if pbo is None or pbo > MAX_PBO:
            why.append("sobreajuste de la familia " + ("no medible" if pbo is None else f"PBO {pbo:.0%} > {MAX_PBO:.0%}"))
        out[k] = {"return": total, "max_drawdown": r["max_drawdown"], "trades": len(r["r"]),
                  "win_rate": sum(1 for x in r["r"] if x > 0) / len(r["r"]) if r["r"] else 0.0,
                  "mean_r": sum(r["r"]) / len(r["r"]) if r["r"] else 0.0, "ci_r": ci,
                  "segments": segs, "sharpe": sharpe(rets[k]), "dsr": dsr, "neighbours": nb,
                  "validated": not why, "why": why}
    return {"pbo": pbo, "n_trials": n_trials, "var_sr": var_sr, "periods": t, "strategies": out}
