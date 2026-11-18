"""Mejora automática: un optimizador evolutivo que no se deja engañar por el pasado.

Los datos se dividen en tres tramos consecutivos:

    [ aprender 40% ][ validación 40%, en 3 tramos ][ examen final 20% ]

1. Una población de configuraciones (``Config``) evoluciona: se cruzan, mutan y
   se seleccionan por su resultado en **validación**, puntuando la constancia
   en los 3 tramos (mediana + peor tramo), no un único golpe de suerte.
2. Objetivo acordado: **máximo rendimiento con una caída máxima del 10 %**. Toda
   configuración que caiga más del 10 % queda descalificada, gane lo que gane.
   También se exige un mínimo de operaciones: diez aciertos de suerte no
   demuestran nada.
3. La mejor configuración solo sustituye a la campeona actual si también gana
   en el **examen final**, un tramo que el optimizador nunca vio. Así se
   combate el sobreajuste, el error número uno de los bots de trading.

Cada ejecución queda registrada en ``optimize_history.jsonl``. Con un ``cron``
diario, en 20 días tienes 20 rondas de mejora documentadas.

Truco de velocidad: las señales de los 94 agentes no dependen de la
configuración, así que se calculan una sola vez (caché) y cada simulación
solo repite el aprendizaje y las decisiones.
"""
from __future__ import annotations

import gc
import json
import math
import multiprocessing as mp
import os
import random
import statistics
import time
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import replace
from typing import Callable, Dict, List, Optional, Tuple

from engine import WINDOW, Config, Engine, group_swarm, metrics, run_backtest, stress_test, trade_stats
from market import Candle

MAX_DD = 0.10
BOUNDS: Dict[str, Tuple[float, float]] = {
    "enter": (0.05, 0.40), "min_agreement": (0.50, 0.90), "min_edge": (0.0, 0.50),
    "min_samples": (15, 120), "risk_per_trade": (0.003, 0.02), "stop_atr": (1.0, 3.0),
    "max_positions": (1, 6), "max_exposure": (0.15, 0.50),
    "exit_score": (-0.6, 0.0), "team_eta": (0.05, 1.0), "council_eta": (0.05, 1.0),
    "shadow_horizon": (12, 96), "riskoff_breadth": (0.2, 0.5), "max_heat": (0.01, 0.06),
    "learn_horizon": (1, 36),
}
INTS = {"min_samples", "max_positions", "shadow_horizon", "learn_horizon"}
BOOLS = ("block_volatile", "trend_filter", "riskoff")
FOLDS = 3


def _fix(cfg: Config) -> Config:
    kw = {}
    for k, (lo, hi) in BOUNDS.items():
        v = min(hi, max(lo, getattr(cfg, k)))
        kw[k] = int(round(v)) if k in INTS else round(v, 4)
    # el objetivo de salida lo elige el calibrador entre los perfiles medidos; el 77 % es
    # un requisito del usuario: el optimizador nunca puede rebajarlo
    kw["min_win_prob"] = max(cfg.min_win_prob, 0.77)
    return replace(cfg, **kw, max_drawdown=MAX_DD)


def mutate(cfg: Config, rng: random.Random, teams: List[str], rate: float = 0.35) -> Config:
    kw = {}
    for k, (lo, hi) in BOUNDS.items():
        if rng.random() < rate:
            kw[k] = getattr(cfg, k) + rng.gauss(0, (hi - lo) * 0.15)
    for k in BOOLS:
        if rng.random() < rate / 3:
            kw[k] = not getattr(cfg, k)
    if rng.random() < rate / 2:
        active = set(cfg.teams or teams)
        t = rng.choice(teams)
        active.symmetric_difference_update({t})
        if len(active) >= 2:
            kw["teams"] = tuple(sorted(active)) if len(active) < len(teams) else ()
    return _fix(replace(cfg, **kw))


def crossover(a: Config, b: Config, rng: random.Random) -> Config:
    kw = {k: getattr(a if rng.random() < 0.5 else b, k) for k in list(BOUNDS) + list(BOOLS) + ["teams"]}
    return _fix(replace(a, **kw))


def fitness(m: Dict[str, float], n_trades: int, min_trades: int,
            folds: Optional[List[float]] = None, dd_p95: float = 0.0) -> float:
    """Caída máxima como límite duro; después, **constancia**: la mitad de la
    nota es el tramo mediano y la otra mitad el PEOR tramo. Una configuración que
    gana mucho en un tramo y pierde en otro (suerte) puntúa peor que una que
    gana algo en todos."""
    if m["max_drawdown"] > MAX_DD:
        return -1.0 - m["max_drawdown"]
    if n_trades < min_trades:
        return -0.6 + 0.01 * min(n_trades, 9)  # nivel «pocas operaciones»: siempre en [-0,6, -0,51]
    base = 0.5 * statistics.median(folds) + 0.5 * min(folds) if folds else m["return"]
    # prueba de estrés: si en una mala racha (peor 5 %) la caída superaría el 10 %, se penaliza
    penalty = min(0.4, 2.0 * max(0.0, dd_p95 - MAX_DD))
    # una configuración válida nunca puntúa por debajo de los niveles «pocas operaciones» (-0,5)
    # ni «descalificada» (< -1): el orden de los límites duros se mantiene
    return max(-0.5, base - penalty)


def fold_returns(equity: List[float], k: int = FOLDS) -> List[float]:
    n = len(equity) - 1
    if n < k:
        return [equity[-1] / equity[0] - 1]
    cuts = [round(i * n / k) for i in range(k + 1)]
    return [equity[cuts[i + 1]] / equity[cuts[i]] - 1 for i in range(k)]


MIN_HOLDOUT_TRADES = 3
MAX_AUTO_WORKERS = 4  # cada proceso acaba copiando parte de la caché (~400 MB con 8 monedas x 5000 velas)


def _usable_cpus() -> int:
    """CPUs que este proceso puede usar de verdad (en contenedores, ``os.cpu_count``
    devuelve las del servidor entero)."""
    if hasattr(os, "process_cpu_count"):
        return os.process_cpu_count() or 1  # Python 3.13+
    if hasattr(os, "sched_getaffinity"):
        return len(os.sched_getaffinity(0)) or 1
    return os.cpu_count() or 1


def should_accept(cand: dict, champ: dict) -> bool:
    """Una aspirante sustituye a la campeona solo si, en el examen final (datos
    nunca vistos): GANA dinero, gana más que la campeona, respeta la caída
    máxima y lo hace con al menos 3 operaciones. Perder menos no es ganar; una
    sola operación es suerte, no evidencia."""
    if not (cand["max_drawdown"] <= MAX_DD and cand["trades"] >= MIN_HOLDOUT_TRADES and cand["return"] > 0):
        return False
    champ_valid = champ["max_drawdown"] <= MAX_DD and champ["trades"] >= MIN_HOLDOUT_TRADES
    # una campeona que rompe el límite del 10 % o cuyo resultado es de 1-2 operaciones (suerte)
    # no protege su puesto: cualquier aspirante válida que gane dinero la sustituye
    return cand["return"] > champ["return"] if champ_valid else True


_WORKER: Optional["Optimizer"] = None


def _eval_in_worker(cfg: Config) -> dict:
    assert _WORKER is not None
    return _WORKER.evaluate(cfg)


class Optimizer:
    def __init__(self, data: Dict[str, List[Candle]], periods_per_year: int = 8_760, cash: float = 10_000.0,
                 seed: int = 0, min_trades: int = 10, log: Callable[[str], None] = print,
                 workers: int = 0, sentiment: Optional[Dict[str, int]] = None,
                 funding: Optional[Dict[str, list]] = None) -> None:
        self.data = data
        self.ppy = periods_per_year
        self.cash = cash
        self.rng = random.Random(seed)
        self.min_trades = min_trades
        self.log = log
        self.cache: Dict[tuple, dict] = {}
        self.teams = list(group_swarm())
        n = min(len(v) for v in data.values())
        self.n = n
        self.start = min(WINDOW, max(a.warmup for ags in group_swarm().values() for a in ags) + 1)
        usable = n - self.start
        # [aprender 40 %][validación 40 %, en 3 tramos][examen final 20 %]
        self.val_from = self.start + int(usable * 0.40)
        self.test_from = self.start + int(usable * 0.80)
        if n - self.test_from < 100:
            raise ValueError(f"pocas velas ({n}); hacen falta al menos ~{self.start + 500}")
        self.evals = 0
        self.sentiment = sentiment
        self.funding = funding
        self.workers = max(1, workers if workers else min(MAX_AUTO_WORKERS, _usable_cpus()))

    def evaluate(self, cfg: Config, holdout: bool = False) -> dict:
        eng = Engine(cfg, cash=self.cash, cache=self.cache, sentiment=self.sentiment, funding=self.funding)
        eng.track_stats = False
        stop = self.n if holdout else self.test_from
        trade_from = self.test_from if holdout else self.val_from
        out = run_backtest(eng, self.data, self.start, stop, trade_from)
        m = metrics(out["equity"], self.ppy)
        ts = trade_stats(eng.pf.closed)
        folds = None if holdout else fold_returns(out["equity"])
        st = stress_test([t.equity_return for t in eng.pf.closed], 1.0, n_paths=400, seed=1)
        dd95 = st.get("dd_p95", 0.0)
        self.evals += 1
        return {"fitness": fitness(m, ts["n"], self.min_trades, folds, dd95), **m, "trades": ts["n"], "folds": folds,
                "dd_p95": dd95,
                "win_rate": ts["win_rate"], "profit_factor": ts["profit_factor"] if ts["profit_factor"] != math.inf
                else 99.0, "buy_hold": out["buy_hold"], "halted": eng.risk.halted}

    def warm(self) -> None:
        """Calcula una vez las señales de todos los agentes en todas las velas
        (la parte cara). Después, cada simulación solo repite las decisiones."""
        s0 = next(iter(self.data))
        if (s0, self.data[s0][self.n - 1].time) not in self.cache:
            eng = Engine(Config(), cash=self.cash, cache=self.cache, sentiment=self.sentiment, funding=self.funding)
            eng.track_stats = False
            run_backtest(eng, self.data, self.start, self.n, self.n - 1)

    def evaluate_many(self, cfgs: List[Config]) -> List[dict]:
        """Evalúa en paralelo (fork: los procesos hijos heredan la caché). ``gc.freeze``
        evita que el recolector toque las páginas heredadas y las copie. Si un
        proceso hijo muere (p. ej. por falta de memoria), en vez de colgarse se
        repite la tanda en serie."""
        if self.workers <= 1 or len(cfgs) <= 1 or "fork" not in mp.get_all_start_methods():
            return [self.evaluate(c) for c in cfgs]
        global _WORKER
        self.warm()
        _WORKER = self
        gc.collect()
        gc.freeze()
        try:
            with ProcessPoolExecutor(min(self.workers, len(cfgs)), mp_context=mp.get_context("fork")) as ex:
                out = list(ex.map(_eval_in_worker, cfgs))
            self.evals += len(cfgs)
            return out
        except BrokenProcessPool:
            self.log("  [aviso] un proceso paralelo murió (¿memoria?); repitiendo esta tanda en serie")
            return [self.evaluate(c) for c in cfgs]
        finally:
            _WORKER = None
            gc.unfreeze()

    def run(self, champion: Optional[Config] = None, population: int = 12, generations: int = 6,
            elite: int = 3) -> dict:
        t0 = time.time()
        base = _fix(champion or Config())
        pop = [base, _fix(Config())] + [mutate(base, self.rng, self.teams, rate=0.8) for _ in range(population - 2)]
        scored: List[Tuple[float, Config, dict]] = []
        for gen in range(generations):
            seen = {json.dumps(c.to_dict(), sort_keys=True) for _, c, _ in scored}
            fresh: List[Config] = []
            for c in pop:
                key = json.dumps(c.to_dict(), sort_keys=True)
                if key not in seen:
                    seen.add(key)
                    fresh.append(c)
            for c, r in zip(fresh, self.evaluate_many(fresh)):
                scored.append((r["fitness"], c, r))
            scored.sort(key=lambda x: -x[0])
            best = scored[0][2]
            self.log(f"  generación {gen + 1}/{generations}: mejor validación {best['return']:+.2%} "
                     f"(caída {best['max_drawdown']:.1%}, {best['trades']} ops)  [{self.evals} simulaciones, "
                     f"{time.time() - t0:.0f}s]")
            parents = [c for _, c, _ in scored[: max(elite, population // 3)]]
            pop = [c for _, c, _ in scored[:elite]]
            while len(pop) < population:
                a, b = self.rng.sample(parents, 2) if len(parents) > 1 else (parents[0], parents[0])
                pop.append(mutate(crossover(a, b, self.rng), self.rng, self.teams))

        # examen final: el mejor de validación contra la campeona actual, en datos nunca vistos
        cand_cfg, cand_val = scored[0][1], scored[0][2]
        cand_test, champ_test = self.evaluate(cand_cfg, holdout=True), self.evaluate(base, holdout=True)
        accepted = cand_cfg != base and should_accept(cand_test, champ_test)
        return {"accepted": accepted, "candidate": cand_cfg, "candidate_val": cand_val,
                "candidate_test": cand_test, "champion": base, "champion_test": champ_test,
                "evals": self.evals, "seconds": time.time() - t0,
                "split": {"start": self.start, "val_from": self.val_from, "test_from": self.test_from, "n": self.n}}


def load_champion(path: str) -> Optional[Config]:
    if os.path.exists(path):
        with open(path) as fh:
            return Config.from_dict(json.load(fh).get("config"))
    return None


def save_result(champion_path: str, history_path: str, res: dict, meta: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(champion_path)), exist_ok=True)
    row = {"date": time.strftime("%Y-%m-%d %H:%M:%S"), **meta, "accepted": res["accepted"],
           "evals": res["evals"], "seconds": round(res["seconds"], 1),
           "candidate_val": res["candidate_val"], "candidate_test": res["candidate_test"],
           "champion_test": res["champion_test"], "candidate": res["candidate"].to_dict()}
    with open(history_path, "a") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    if res["accepted"] or not os.path.exists(champion_path):
        cfg = res["candidate"] if res["accepted"] else res["champion"]
        test = res["candidate_test"] if res["accepted"] else res["champion_test"]
        tmp = champion_path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump({"date": row["date"], "config": cfg.to_dict(), "holdout": test, **meta}, fh, indent=2,
                      ensure_ascii=False)
        os.replace(tmp, champion_path)
