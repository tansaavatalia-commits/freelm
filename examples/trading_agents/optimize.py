"""Mejora automática: un optimizador evolutivo que no se deja engañar por el pasado.

Los datos se dividen en tres tramos consecutivos:

    [ aprender 50% ][ validación 25% ][ examen final 25% ]

1. Una población de configuraciones (``Config``) evoluciona: se cruzan, mutan y
   se seleccionan por su resultado en **validación**.
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

import json
import math
import os
import random
import time
from dataclasses import replace
from typing import Callable, Dict, List, Optional, Tuple

from engine import WINDOW, Config, Engine, group_swarm, metrics, run_backtest, trade_stats
from market import Candle

MAX_DD = 0.10
BOUNDS: Dict[str, Tuple[float, float]] = {
    "enter": (0.05, 0.40), "min_agreement": (0.50, 0.90), "min_edge": (0.0, 0.50),
    "min_samples": (15, 120), "risk_per_trade": (0.003, 0.02), "stop_atr": (1.0, 3.0),
    "target_atr": (1.5, 8.0), "max_positions": (1, 6), "max_exposure": (0.15, 0.50),
    "exit_score": (-0.6, 0.0), "team_eta": (0.05, 1.0), "council_eta": (0.05, 1.0),
    "shadow_horizon": (12, 96),
}
INTS = {"min_samples", "max_positions", "shadow_horizon"}
BOOLS = ("block_volatile", "trend_filter")


def _fix(cfg: Config) -> Config:
    kw = {}
    for k, (lo, hi) in BOUNDS.items():
        v = min(hi, max(lo, getattr(cfg, k)))
        kw[k] = int(round(v)) if k in INTS else round(v, 4)
    kw["target_atr"] = max(kw["target_atr"], 1.5 * kw["stop_atr"])  # beneficio/riesgo >= 1.5
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


def fitness(m: Dict[str, float], n_trades: int, min_trades: int) -> float:
    """Rendimiento del tramo, con la caída máxima como límite duro."""
    if m["max_drawdown"] > MAX_DD:
        return -1.0 - m["max_drawdown"]
    if n_trades < min_trades:
        return -0.5 + 0.01 * n_trades
    return m["return"]


class Optimizer:
    def __init__(self, data: Dict[str, List[Candle]], periods_per_year: int = 8_760, cash: float = 10_000.0,
                 seed: int = 0, min_trades: int = 10, log: Callable[[str], None] = print) -> None:
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
        self.val_from = self.start + int(usable * 0.50)
        self.test_from = self.start + int(usable * 0.75)
        if n - self.test_from < 100:
            raise ValueError(f"pocas velas ({n}); hacen falta al menos ~{self.start + 400}")
        self.evals = 0

    def evaluate(self, cfg: Config, holdout: bool = False) -> dict:
        eng = Engine(cfg, cash=self.cash, cache=self.cache)
        stop = self.n if holdout else self.test_from
        trade_from = self.test_from if holdout else self.val_from
        out = run_backtest(eng, self.data, self.start, stop, trade_from)
        m = metrics(out["equity"], self.ppy)
        ts = trade_stats(eng.pf.closed)
        self.evals += 1
        return {"fitness": fitness(m, ts["n"], self.min_trades), **m, "trades": ts["n"],
                "win_rate": ts["win_rate"], "profit_factor": ts["profit_factor"] if ts["profit_factor"] != math.inf
                else 99.0, "buy_hold": out["buy_hold"], "halted": eng.risk.halted}

    def run(self, champion: Optional[Config] = None, population: int = 12, generations: int = 6,
            elite: int = 3) -> dict:
        t0 = time.time()
        base = _fix(champion or Config())
        pop = [base, _fix(Config())] + [mutate(base, self.rng, self.teams, rate=0.8) for _ in range(population - 2)]
        scored: List[Tuple[float, Config, dict]] = []
        for gen in range(generations):
            seen = {json.dumps(c.to_dict(), sort_keys=True) for _, c, _ in scored}
            for c in pop:
                if json.dumps(c.to_dict(), sort_keys=True) in seen:
                    continue
                r = self.evaluate(c)
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
        cand_test = self.evaluate(cand_cfg, holdout=True)
        champ_test = self.evaluate(base, holdout=True)
        accepted = (cand_test["max_drawdown"] <= MAX_DD and cand_test["fitness"] > champ_test["fitness"]
                    and cand_cfg != base)
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
