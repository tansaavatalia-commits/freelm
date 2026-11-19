"""Bot multiagente de señales cripto: grafo de nodos, aprendizaje y mejora automática.

    python bot.py graph                         # dibuja el grafo de nodos (Mermaid)
    python bot.py bench                         # señales por segundo
    python bot.py backtest                      # aprender + validar fuera de muestra
    python bot.py optimize                      # una ronda de mejora automática
    python bot.py validate                      # walk-forward, Deflated Sharpe, PBO, sensibilidad
    python bot.py classic                       # lo mismo con momentum clásico (velas diarias)
    python bot.py momentum                      # momentum combinado en papel, 20 días (1 vez al día)
    python bot.py live                          # tiempo real, en papel (por defecto)
    python bot.py live --exchange testnet       # órdenes en el testnet del exchange
    python bot.py gate                          # ¿listo para dinero real? (20 días)
    python bot.py live --exchange real --confirm-real-money --max-capital 100
    python bot.py status

Plan de 20 días (ver README): ``live`` corriendo en papel y ``optimize --source
binance`` una vez al día. ``gate`` dice cuándo (y si) se puede pasar a dinero real.

Material educativo, no asesoramiento financiero. Ningún sistema puede garantizar
beneficios ni evitar todas las pérdidas.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from dataclasses import asdict, replace
from types import SimpleNamespace
from typing import Dict, List, Optional, Sequence

from agents import LLMAnalystAgent
from engine import SHADOW_GAP, WINDOW, Config, Engine, metrics, run_backtest, stress_test, trade_stats
from exchange import CcxtExecutor, check_gate, load_track, record_equity, to_market
from learning import REGIMES, AgentStats, Calibrator
from market import DEFAULT_SYMBOLS, Candle, align, fetch_candles, fetch_fear_greed, fetch_funding, load_csv, synthetic
from notify import Notifier
from optimize import Optimizer, load_champion, save_result
from report import format_performance, performance
from risk import ClosedTrade, Position
from safety import DecisionJournal, check_fresh

STATE_DIR = os.environ.get("FREELM_TRADING_DIR", os.path.join(os.path.expanduser("~"), ".cache", "freelm-trading"))
PERIODS_PER_YEAR = {"1m": 525_600, "5m": 105_120, "15m": 35_040, "1h": 8_760, "4h": 2_190, "1d": 365}
INTERVAL_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14_400, "1d": 86_400}


def p(args: argparse.Namespace, name: str) -> str:
    return os.path.join(args.dir or STATE_DIR, name)


# --------------------------------------------------------------------------- construcción

def load_json(path: Optional[str]) -> dict:
    if path and os.path.exists(path):
        with open(path) as fh:
            return json.load(fh)
    return {}


def save_json(path: str, obj: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def build_llm(enabled: bool, model: str) -> Optional[LLMAnalystAgent]:
    if not enabled:
        return None
    try:
        from freelm import FreeLLM
        return LLMAnalystAgent(FreeLLM.from_env(timeout=30), model=model)
    except Exception as e:  # noqa: BLE001 - sin claves el bot sigue, solo sin IA
        print(f"[aviso] analista IA desactivado: {type(e).__name__}: {e}", file=sys.stderr)
        return None


def config_for(args: argparse.Namespace) -> Config:
    if args.config:
        cfg = Config.from_dict(load_json(args.config).get("config"))
    else:
        champ = None if args.default_config else load_champion(p(args, "champion.json"))
        cfg = champ or Config()
    return apply_cost_flags(cfg, args)


def apply_cost_flags(cfg: Config, args: argparse.Namespace) -> Config:
    """--entry-mode limit|market y --bnb (comisión 0,075 % pagando con BNB) desde la línea de órdenes."""
    kw: Dict[str, object] = {}
    if getattr(args, "entry_mode", None):
        kw["entry_mode"] = args.entry_mode
    if getattr(args, "bnb", False):
        kw["maker_fee"] = kw["taker_fee"] = 0.00075
    cfg = replace(cfg, **kw) if kw else cfg
    if getattr(args, "exchange", "papel") in ("testnet", "real") and cfg.entry_mode == "limit" and cfg.target_maker:
        # en el exchange el stop ya está puesto como orden: el objetivo se vigila y se vende a mercado.
        # La estadística de ese modo (claves LT|) cuenta el objetivo como taker.
        cfg = replace(cfg, target_maker=False)
    return cfg


def state_file(args: argparse.Namespace) -> Optional[str]:
    if getattr(args, "no_memory", False):
        return None
    return args.state or p(args, f"memoria-{args.source}-{args.interval}.json")


def load_raw(args: argparse.Namespace) -> Dict[str, List[Candle]]:
    """Velas de cada símbolo SIN recortar a las fechas comunes (cada moneda con su historia)."""
    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if args.source == "binance":
        data = {}
        for s in syms:
            try:
                data[s] = fetch_candles(s, args.interval, args.limit)
            except Exception as e:  # noqa: BLE001 - un símbolo caído no tumba el resto
                print(f"[aviso] {s}: {type(e).__name__}: {e}", file=sys.stderr)
        return data
    if args.source == "csv":
        if not args.csv:
            raise SystemExit("--source csv necesita --csv PLANTILLA (p. ej. datos/{symbol}.csv)")
        return {s: load_csv(args.csv.format(symbol=s)) for s in syms}
    return {s: synthetic(args.limit, seed=args.seed + i, start=100.0 * (i + 1), structure=args.structure)
            for i, s in enumerate(syms)}


def load_universe(args: argparse.Namespace) -> Dict[str, List[Candle]]:
    return align(load_raw(args))


def load_sentiment(args: argparse.Namespace) -> Optional[Dict[str, int]]:
    """Fear & Greed diario para el equipo «mercado» (solo con datos reales)."""
    if args.source == "synthetic" or args.no_sentiment:
        return None
    try:
        # días que cubren las velas pedidas en su intervalo real (1 h, 4 h, 1 d...), con margen
        days = args.limit * 365 // PERIODS_PER_YEAR.get(args.interval, 8_760) + 10
        return fetch_fear_greed(limit=max(30, days))
    except Exception as e:  # noqa: BLE001 - el sentimiento es opcional
        print(f"[aviso] sin Fear & Greed: {type(e).__name__}", file=sys.stderr)
        return None


def load_funding(args: argparse.Namespace, symbols: List[str], start_ms: int) -> Optional[Dict[str, list]]:
    """Funding rate de futuros para el equipo «posicionamiento» (solo con datos reales).
    Se pide desde 40 días antes de la primera vela, para poder calcular su z-score."""
    if args.source == "synthetic" or args.no_funding:
        return None
    out = {}
    for s in symbols:
        try:
            out[s] = fetch_funding(s, start_ms - 40 * 86_400_000)
        except Exception as e:  # noqa: BLE001 - el funding es opcional
            print(f"[aviso] {s}: sin funding ({type(e).__name__})", file=sys.stderr)
    got = sum(1 for v in out.values() if v)
    if got < len(symbols):
        print(f"[aviso] funding disponible para {got}/{len(symbols)} monedas", file=sys.stderr)
    return out


def _first_ms(data: Dict[str, List[Candle]]) -> int:
    return min(cs[0].time for cs in data.values())


def print_verification(trades: List[ClosedTrade]) -> None:
    """¿Se cumplió lo prometido? Probabilidad verificada al abrir frente al acierto real."""
    ts = [t for t in trades if t.p_win > 0]
    if not ts:
        print("  verificación del 77 %: ninguna operación cumplió el filtro de probabilidad")
        return
    promised = sum(t.p_win for t in ts) / len(ts)
    hit = sum(1 for t in ts if t.pnl > 0) / len(ts)
    verdict = "se cumple" if hit >= promised else ("dentro de lo esperable" if len(ts) < 20 else "NO se cumple")
    print(f"  verificación del 77 %: {len(ts)} operaciones con probabilidad verificada media {promised:.0%} "
          f"-> acertaron {hit:.0%} ({verdict})")


def fetch_universe(syms: List[str], interval: str, limit: int) -> Dict[str, List[Candle]]:
    """Las 8 monedas en paralelo: en 1-5 min, todas llegan en ~1 s tras el cierre de la vela."""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=len(syms)) as ex:
        res = dict(zip(syms, ex.map(lambda s: fetch_candles(s, interval, limit), syms)))
    return align(res)


def sleep_to_next_close(interval: str, poll: float) -> None:
    """Duerme hasta 1,5 s después del cierre de la próxima vela: la decisión y la orden
    salen en el mismo segundo en que la vela con señal se confirma. ``--poll`` > 0 lo anula."""
    if poll > 0:
        time.sleep(poll)
        return
    iv = INTERVAL_SECONDS.get(interval, 3600)
    now = time.time()
    time.sleep(max(1.0, (int(now // iv) + 1) * iv + 1.5 - now))


def print_stress(trades: List[ClosedTrade]) -> None:
    st = stress_test([t.equity_return for t in trades], 1.0)
    if not st.get("paths"):
        print("  prueba de estrés: hacen falta al menos 5 operaciones")
        return
    print(f"  prueba de estrés ({st['paths']:,} órdenes al azar de las mismas {st['trades']} operaciones): "
          f"caída típica {st['dd_p50']:.1%}, mala racha (peor 5 %) {st['dd_p95']:.1%}, "
          f"prob. de acabar en pérdidas {st['p_loss']:.0%}")


def agent_ic_table(state: dict) -> List[tuple]:
    """(agente, equipo, observaciones, IC, t) de cada agente, del más al menos predictivo.

    Con ``learn_horizon`` = h > 1 los retornos de h velas se solapan: las observaciones no son
    independientes y la t ingenua sale inflada ~sqrt(h). Se corrige dividiendo por sqrt(h)."""
    h = max(1, int((state.get("config") or {}).get("learn_horizon", 1) or 1))
    rows = []
    for team, t in state.get("teams", {}).items():
        for name, st in t.get("stats", {}).items():
            a = AgentStats(**st)
            if a.ic_n > 2:
                rows.append((name, team, a.ic_n, a.ic, a.ic_t / math.sqrt(h)))
    return sorted(rows, key=lambda r: -r[4])


def print_ic(state: dict, k: int = 6, full: bool = False) -> None:
    rows = agent_ic_table(state)
    if not rows:
        return
    useful = sum(1 for r in rows if r[4] > 2)
    harmful = sum(1 for r in rows if r[4] < -2)
    print("\nCapacidad predictiva por agente (IC = correlación con el retorno siguiente; |t| > 2 = no es azar)")
    print(f"  {useful} agentes con IC positivo significativo, {harmful} con IC negativo significativo, "
          f"{len(rows) - useful - harmful} indistinguibles del ruido (de {len(rows)})")
    show = rows if full else rows[:k] + ([("…", "", 0, 0.0, 0.0)] if len(rows) > 2 * k else []) + rows[-k:]
    for name, team, n, ic, t in show:
        if name == "…":
            print("  …")
            continue
        print(f"  {name:<18}{team:<16}IC {ic:+.3f}  t {t:+6.1f}  ({n:,} obs.)")


def print_learning(state: dict, top: int = 3) -> None:
    cfg = state.get("config")
    if cfg:
        keys = ("enter", "min_agreement", "min_edge", "risk_per_trade", "stop_atr", "target_atr", "max_positions")
        print("Configuración: " + ", ".join(f"{k}={cfg[k]}" for k in keys if k in cfg)
              + (f", equipos={cfg['teams']}" if cfg.get("teams") else ""))
    council = state.get("council", {}).get("weights", {})
    print("\nConsejo: peso de cada equipo por régimen")
    for reg in REGIMES:
        if reg in council:
            print(f"  {reg:<10} " + ", ".join(f"{a} {w:.0%}" for a, w in sorted(council[reg].items(),
                                                                              key=lambda kv: -kv[1])))
    print(f"\nMejores agentes de cada equipo (top {top}; régimen tendencia | lateral)")
    for name, t in state.get("teams", {}).items():
        w = t.get("weights", {})
        best = [", ".join(a for a, _ in sorted(w.get(reg, {}).items(), key=lambda kv: -kv[1])[:top])
                for reg in ("tendencia", "lateral")]
        print(f"  {name:<12} {best[0]}  |  {best[1]}")
    cfg = Config.from_dict(state.get("config"))
    rows = Calibrator.from_dict(state.get("calibrator"), sample_gap=SHADOW_GAP).table(z=cfg.prob_z)
    if rows:
        print("\nCalibrador: tipo de señal x perfil de salida (#t = objetivo en ATR), medido en la sombra")
        print(f"  {'tipo':<34}{'casos':>7}{'acierto':>9}{'verificable':>13}{'esperanza':>11}")
        for k, n, mean, wr, e, plb in rows[:12]:
            mark = "  << opera" if plb >= cfg.min_win_prob and e > 0 else ""
            print(f"  {k:<34}{n:>7}{wr:>9.0%}{plb:>13.0%}{e:>+10.2f}R{mark}")
        print(f"  (solo se opera si «verificable» >= {cfg.min_win_prob:.0%}: cota inferior de Wilson con "
              f"z={cfg.prob_z:g}, muestras efectivas)")


def print_result(label: str, m: Dict[str, float], ts: Dict[str, float], bh: float) -> None:
    pf = "∞" if ts["profit_factor"] == math.inf else f"{ts['profit_factor']:.2f}"
    print(f"{label}: {m['return']:+.2%}  (semanal {m['weekly']:+.2%}, anual {m['annual']:+.2%})   "
          f"cesta comprar y mantener: {bh:+.2%}")
    print(f"  caída máxima {m['max_drawdown']:.2%}   Sharpe {m['sharpe']:.2f}   operaciones {ts['n']}   "
          f"acierto {ts['win_rate']:.0%}   factor de beneficio {pf}   media {ts['avg_r']:+.2f}R")


# --------------------------------------------------------------------------- comandos

def cmd_backtest(args: argparse.Namespace) -> int:
    data = load_universe(args)
    if not data:
        raise SystemExit("sin datos")
    path = state_file(args)
    eng = Engine(config_for(args), load_json(path), cash=args.cash, llm=build_llm(args.llm, args.llm_model),
                 sentiment=load_sentiment(args), funding=load_funding(args, list(data), _first_ms(data)))
    n = min(len(v) for v in data.values())
    split = eng.warmup + int((n - eng.warmup) * args.train)
    if n - split < 50:
        raise SystemExit(f"pocas velas ({n}); usa --limit mayor")
    n_agents = sum(len(t.agents) for t in eng.teams.values())
    print(f"Universo: {', '.join(data)} ({args.source}, {args.interval})")
    print(f"{len(eng.teams)} equipos, {n_agents} agentes por símbolo, "
          f"{(n_agents + len(eng.teams)) * len(data)} señales por vela; ejecución: {eng.executor.name}")

    def show(i: int, rep) -> None:
        if args.verbose and i >= split:
            for q in rep.opened:
                print(f"  ABRE   {q.symbol:<9} {q.entry:>11.4f}  stop {q.stop:.4f}  obj {q.target:.4f}  ({q.reason})")
            for t in rep.closed:
                print(f"  CIERRA {t.symbol:<9} {t.exit:>11.4f}  {t.r:+.2f}R  {t.pnl:+.2f}  ({t.why})")
        if rep.event:
            print("  [interruptor de emergencia activado]")

    out = run_backtest(eng, data, eng.warmup, n, split, on_step=show)
    m = metrics(out["equity"], PERIODS_PER_YEAR.get(args.interval, 8_760))
    ts = trade_stats(eng.pf.closed)
    print(f"\nAprendizaje sin operar: {split - eng.warmup} velas · validación operando en papel: {n - split} velas")
    print_result("Validación fuera de muestra", m, ts, out["buy_hold"])
    s0 = next(iter(data))
    times = [data[s0][split].time] + [data[s0][i].time for i in range(split, n)]
    for line in format_performance(performance(out["equity"], times, PERIODS_PER_YEAR.get(args.interval, 8_760),
                                               eng.pf.closed)):
        print(line)
    print(f"  señales procesadas: {eng.total_signals:,} a {eng.signals_per_second:,.0f}/s")
    print_stress(eng.pf.closed)
    print_verification(eng.pf.closed)
    vetoes = sorted(eng.veto_counts.items(), key=lambda kv: -kv[1])
    print("  vetos: " + ", ".join(f"{k} {v:,}" for k, v in vetoes[:5]))
    ok_dd = m["max_drawdown"] <= 0.10
    print(f"\nObjetivo acordado (máximo rendimiento con caída ≤ 10 %): caída {m['max_drawdown']:.1%} "
          f"{'✔' if ok_dd else '✘'}  ·  tu meta del +18 % semanal: {m['weekly']:+.2%} por semana"
          + ("  [datos sintéticos]" if args.source == "synthetic" else ""))
    print()
    print_learning(eng.state())
    print_ic(eng.state())
    if path:
        save_json(path, eng.state())
        print(f"\nMemoria guardada en {path}")
    return 0


def cmd_optimize(args: argparse.Namespace) -> int:
    data = load_universe(args)
    if not data:
        raise SystemExit("sin datos")
    champ_path, hist_path = p(args, "champion.json"), p(args, "optimize_history.jsonl")
    saved = None if args.default_config else load_champion(champ_path)
    champ = apply_cost_flags(saved or Config(), args)
    opt = Optimizer(data, PERIODS_PER_YEAR.get(args.interval, 8_760), cash=args.cash, seed=args.seed,
                    min_trades=args.min_trades, workers=args.workers, sentiment=load_sentiment(args),
                    funding=load_funding(args, list(data), _first_ms(data)))
    sp = {"aprender": opt.val_from - opt.start, "validación": opt.test_from - opt.val_from,
          "examen": opt.n - opt.test_from}
    print(f"Optimizando sobre {', '.join(data)} ({args.source}, {args.interval}): "
          + ", ".join(f"{k} {v} velas" for k, v in sp.items()))
    print(f"Campeona de partida: {'la guardada' if saved else 'configuración por defecto'} "
          f"(entrada {champ.entry_mode}, comisión {champ.taker_fee:.3%})")
    res = opt.run(champ, population=args.population, generations=args.generations)
    ct, ht = res["candidate_test"], res["champion_test"]
    cv = res["candidate_val"]
    if cv.get("folds"):
        print("  aspirante en los 3 tramos de validación: " + " · ".join(f"{x:+.2%}" for x in cv["folds"]))
    print("\nExamen final (datos nunca vistos):")
    print(f"  aspirante: {ct['return']:+.2%}  caída {ct['max_drawdown']:.1%}  {ct['trades']} ops  "
          f"(semanal {ct['weekly']:+.2%})")
    print(f"  campeona : {ht['return']:+.2%}  caída {ht['max_drawdown']:.1%}  {ht['trades']} ops  "
          f"(semanal {ht['weekly']:+.2%})")
    print("  => " + ("NUEVA CAMPEONA: la mejora se confirma en datos nuevos." if res["accepted"] else
                     "se mantiene la campeona: la mejora no se confirmó fuera de muestra."))
    save_result(champ_path, hist_path, res, {"source": args.source, "interval": args.interval,
                                             "symbols": list(data)})
    print(f"  ({res['evals']} simulaciones en {res['seconds']:.0f}s; historial en {hist_path})")
    return 0


def print_judgement(rep: dict, rules: Sequence[str] = ()) -> List[str]:
    """Tabla y veredicto de ``validation.judge``. Devuelve las estrategias validadas."""
    from validation import MAX_PBO
    print(f"  {'estrategia':<11}{'resultado':>10}{'caída':>7}{'ops':>5}{'acierto':>8}{'media R':>9}"
          f"{'IC95 % media R':>18}{'DSR':>6}   tramos")
    for k, v in rep["strategies"].items():
        lo, hi = v["ci_r"]
        ci = f"[{lo:+.2f}, {hi:+.2f}]" if lo == lo else "—"
        print(f"  {k:<11}{v['return']:>+10.2%}{v['max_drawdown']:>7.1%}{v['trades']:>5}{v['win_rate']:>8.0%}"
              f"{v['mean_r']:>+9.2f}{ci:>18}{v['dsr']:>6.2f}   " + " ".join(f"{x:+.1%}" for x in v["segments"]))
    pbo = rep["pbo"]
    print("\n  Probabilidad de sobreajuste de la familia (PBO, CSCV): "
          + ("no medible (todas las estrategias dieron lo mismo)" if pbo is None else
             f"{pbo:.0%} ({'aceptable' if pbo <= MAX_PBO else 'ALTA: elegir la mejor de esta familia no generaliza'})"))
    if rules:
        print("  Reglas: " + "; ".join(f"{r} = {RULE_LABEL[r]}" for r in rules))
    ok = [k for k, v in rep["strategies"].items() if v["validated"]]
    print()
    for k, v in rep["strategies"].items():
        print(f"  {k:<11}" + ("VALIDADA" if v["validated"] else "NO VALIDADA: " + "; ".join(v["why"])))
    print("\n=> " + (f"Estrategias validadas: {', '.join(ok)}." if ok else
                      "Ninguna estrategia supera la validación. No hay ventaja demostrada: no se recomienda "
                      "operar con dinero real con ninguna de ellas."))
    return ok


RULES = {"77": {}, "ev50": {"min_win_prob": 0.5}}
RULE_LABEL = {"77": "acierto verificado >= 77 %", "ev50": "esperanza > 0 y acierto verificado >= 50 %"}


def cmd_validate(args: argparse.Namespace) -> int:
    """Valida una familia de estrategias con walk-forward, Deflated Sharpe, PBO,
    sensibilidad de parámetros y bootstrap. Solo declara VALIDADA la que pasa todo."""
    from validation import judge
    data = load_universe(args)
    if not data:
        raise SystemExit("sin datos")
    saved = None if args.default_config else load_champion(p(args, "champion.json"))
    base = apply_cost_flags(saved or Config(), args)
    horizons = [int(x) for x in args.horizons.split(",") if x.strip()]
    rules = [r for r in args.rules.split(",") if r.strip()]
    for r in rules:
        if r not in RULES:
            raise SystemExit(f"regla desconocida: {r} (usa {', '.join(RULES)})")
    family = {f"{r}·h{h}": replace(base, learn_horizon=h, **RULES[r]) for r in rules for h in horizons}
    neighbours = {}
    for r in rules:
        for i, h in enumerate(horizons):
            neighbours[f"{r}·h{h}"] = [f"{r}·h{horizons[j]}" for j in (i - 1, i + 1) if 0 <= j < len(horizons)]
    opt = Optimizer(data, PERIODS_PER_YEAR.get(args.interval, 8_760), cash=args.cash, workers=args.workers,
                    sentiment=load_sentiment(args), funding=load_funding(args, list(data), _first_ms(data)))
    trade_from = opt.start + int((opt.n - opt.start) * args.learn)
    weeks = (opt.n - trade_from) * INTERVAL_SECONDS.get(args.interval, 3600) / 604_800
    n_trials = len(family) + args.prior_trials
    print(f"Validación de {len(family)} estrategias sobre {', '.join(data)} ({args.source}, {args.interval})")
    print(f"  walk-forward: aprende {trade_from - opt.start} velas y luego opera {opt.n - trade_from} velas "
          f"(~{weeks:.0f} semanas) sin dejar de aprender, siempre solo con el pasado")
    print(f"  pruebas que se descuentan (Deflated Sharpe): {n_trials} "
          f"({len(family)} de esta familia + {args.prior_trials} anteriores)")
    t0 = time.time()
    res = opt.walk_forward_many(list(family.values()), trade_from)
    results = dict(zip(family, res))
    rep = judge(results, neighbours, n_trials)
    bh = res[0]["buy_hold"] if res else 0.0
    print(f"  ({time.time() - t0:.0f}s) cesta comprar y mantener en el mismo tramo: {bh:+.2%}\n")
    ok = print_judgement(rep, rules)
    rows = {k: {**v, "config": family[k].to_dict()} for k, v in rep["strategies"].items()}
    save_json(p(args, "validation.json"), {"date": time.strftime("%Y-%m-%d %H:%M:%S"), "interval": args.interval,
                                          "symbols": list(data), "source": args.source, "pbo": rep["pbo"],
                                          "n_trials": n_trials, "buy_hold": bh, "strategies": rows})
    return 0 if ok else 3


def cmd_classic(args: argparse.Namespace) -> int:
    """Valida las estrategias clásicas con respaldo académico (strategies.py): momentum de
    tendencia y momentum relativo, más el conjunto de todas, con las mismas pruebas que
    ``validate``. Por defecto: velas diarias, historia completa de cada moneda (cada una
    entra cuando empieza a cotizar) y covarianza real con shrinkage."""
    import strategies as stg
    from validation import judge, probabilistic_sharpe, returns_from_equity, segment_returns
    raw = load_raw(args)
    if not raw:
        raise SystemExit("sin datos")
    data = raw if args.full_history else align(raw)
    ppy = PERIODS_PER_YEAR.get(args.interval, 365)
    fee = 0.00075 if args.bnb else Config().taker_fee
    family = {k: replace(c, target_vol=args.target_vol, fee=fee, risk_model=args.risk_model,
                         dd_budget=args.dd_budget, dd_window=args.dd_window)
              for k, c in stg.default_family().items()}
    trade_from = max(c.warmup for c in family.values())
    panel = stg.Panel(data)
    if panel.n - trade_from < 200:
        raise SystemExit(f"pocas velas ({panel.n}); usa --limit mayor")
    results = {k: stg.simulate_fast(panel, c, trade_from, ppy) for k, c in family.items()}
    results["conjunto"] = stg.ensemble({k: results[k] for k in family})
    n_trials = len(results) + args.prior_trials
    days = (panel.n - trade_from) * INTERVAL_SECONDS.get(args.interval, 86_400) / 86_400
    years = max(days / 365, 1e-9)
    first = time.strftime("%Y-%m-%d", time.gmtime(panel.times[trade_from] / 1000))
    print(f"Estrategias clásicas sobre {', '.join(data)} ({args.source}, {args.interval}): "
          f"{panel.n - trade_from} velas operadas desde {first} (~{years:.1f} años)")
    print(f"  {'historia completa de cada moneda' if args.full_history else 'solo fechas comunes'}; "
          f"riesgo {'covarianza con shrinkage' if args.risk_model == 'cov' else 'correlación 1 supuesta'}; "
          f"volatilidad objetivo {args.target_vol:.0%}"
          + (f"; control de caída {args.dd_budget:.0%}" if args.dd_budget > 0 else ""))
    print(f"  pruebas que se descuentan (Deflated Sharpe): {n_trials} "
          f"({len(results)} de esta familia + {args.prior_trials} anteriores)")
    print(f"  cesta comprar y mantener en el mismo tramo: {results['conjunto']['buy_hold']:+.2%}\n")
    rep = judge(results, stg.neighbours(family), n_trials)
    for v in rep["strategies"].values():
        v["annual"] = (1 + v["return"]) ** (1 / years) - 1 if v["return"] > -1 else -1.0
    ok = print_judgement(rep)
    best = rep["strategies"]["conjunto"]
    print(f"\n  conjunto (sin elegir ninguna variante): {best['annual']:+.1%} al año, caída {best['max_drawdown']:.1%}, "
          f"acierto por operación {best['win_rate']:.0%}")
    if best["win_rate"] < 0.77:
        print("  ojo: el seguimiento de tendencia gana con pocas operaciones grandes; su acierto NUNCA llega "
              "al 77 % exigido por la regla de entrada del bot")
    # sensibilidad al universo (sesgo de supervivencia): el conjunto sin cada moneda
    loo = {}
    if len(data) > 2:
        print("\n  Sensibilidad al universo (conjunto sin cada moneda):")
        for s in data:
            pn = stg.Panel({k: v for k, v in data.items() if k != s})
            e = stg.ensemble({k: stg.simulate_fast(pn, c, trade_from, ppy) for k, c in family.items()})
            ann = e["equity"][-1] ** (1 / years) - 1
            psr = probabilistic_sharpe(returns_from_equity(e["equity"]))
            loo[s] = {"annual": ann, "max_drawdown": e["max_drawdown"], "psr": psr,
                      "segments": segment_returns(e["equity"])}
            print(f"    sin {s:<9} {ann:+6.1%} al año · caída {e['max_drawdown']:5.1%} · PSR {psr:.2f}")
        worst = min(loo.values(), key=lambda x: x["annual"])
        print(f"  peor caso: {worst['annual']:+.1%} al año, caída {worst['max_drawdown']:.1%}"
              + ("  -> no depende de una sola moneda" if worst["annual"] > 0 and worst["max_drawdown"] <= 0.10
                 else "  -> DEPENDE de alguna moneda concreta"))
    print("  aviso: el universo son las monedas grandes de HOY; las que desaparecieron (LUNA, FTT...) no están, "
          "así que el resultado puede estar inflado por sesgo de supervivencia")
    save_json(p(args, "classic.json"), {"date": time.strftime("%Y-%m-%d %H:%M:%S"), "interval": args.interval,
                                       "symbols": list(data), "pbo": rep["pbo"], "n_trials": n_trials,
                                       "config": family["tsmom·50"].__dict__ | {"lookback": "familia"},
                                       "strategies": rep["strategies"], "leave_one_out": loo})
    return 0 if ok else 3


def cmd_momentum(args: argparse.Namespace) -> int:
    """Momentum combinado en PAPEL (20 días): un día por ejecución, tras el cierre diario."""
    import momentum_paper as mp_
    from safety import check_window
    fam = mp_.family_for(args.target_vol, 0.00075 if args.bnb else None, args.risk_model)
    sp, tp = p(args, "momentum_state.json"), p(args, "momentum_track.jsonl")
    state = mp_.load(sp, args.cash, fam)
    notifier = Notifier()
    if state.get("restarted"):
        print(f"[aviso] prueba en papel reiniciada: {state['restarted']}")
        notifier.send(f"freelm momentum: prueba en papel reiniciada ({state['restarted']})")
        if os.path.exists(tp):
            os.replace(tp, tp + ".anterior")
        state.pop("restarted")
        mp_.save(sp, state)
    track = load_track(tp)

    def show(final: bool = False) -> str:
        sm = mp_.summary(state, track)
        lines = [f"Momentum combinado en PAPEL: día {sm['days']}/{mp_.PAPER_DAYS}"
                 + (f" (desde {mp_.utc(state['start_day'])})" if state.get("start_day") else ""),
                 f"  capital {state['equity']:.2f} (inicio {state['cash0']:.2f}): {sm['return']:+.2%} · "
                 f"caída máx. {sm['max_drawdown']:.1%} · cesta comprar y mantener {sm['basket']:+.2%}",
                 "  posiciones: " + (", ".join(f"{s} {w:.0%}" for s, w in sorted(sm["weights"].items(),
                                                                             key=lambda kv: -kv[1]))
                                     or "ninguna (liquidez)")]
        if sm["halted"]:
            lines.append("  DETENIDO: la caída superó el 10 %; todo en liquidez.")
        if sm["done"]:
            lines.append("  Prueba de 20 días COMPLETA: " + (
                "ganó sin superar el 10 % de caída. Ojo: 20 días son pocos para demostrar nada; la "
                "validación estadística sigue sin aprobarla. Dinero real solo con tu autorización expresa."
                if sm["passed"] else "NO superada (no ganó o superó el límite de caída). No pasar a dinero real."))
        return "\n".join(lines)

    if args.report:
        print(show())
        return 0
    if state["days"] >= mp_.PAPER_DAYS and not args.continue_after:
        print(show())
        print("  (la prueba ya terminó; --continue-after para seguir en papel)")
        return 0
    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    now_ms = int(time.time() * 1000)
    journal = DecisionJournal(p(args, "diario"))
    raw: Dict[str, List[Candle]] = {}
    for s in syms:
        try:
            raw[s] = mp_.closed_daily(fetch_candles(s, "1d", args.limit), now_ms)
        except Exception as e:  # noqa: BLE001 - sin datos de una moneda no se decide ese día
            journal.write(now_ms, {"tipo": "aviso", "estrategia": "momentum", "motivo": f"{s}: sin datos ({e})"})
            notifier.send(f"freelm momentum: sin datos de {s}; hoy no se opera")
            print(f"[aviso] {s}: sin datos ({type(e).__name__}); hoy no se opera", file=sys.stderr)
            return 0
    data = raw  # cada moneda con su historia (el motor maneja universos desiguales)
    problems = {s: pr for s, cs in data.items() for pr in [check_window(cs)] if pr}
    stale = {s: m for s, cs in data.items() for m in [check_fresh(cs, 86_400)] if m}
    if problems or stale:
        why = "; ".join(f"{s}: {v[0] if isinstance(v, list) else v}" for s, v in {**problems, **stale}.items())
        journal.write(now_ms, {"tipo": "aviso", "estrategia": "momentum", "motivo": "datos dudosos: " + why})
        notifier.send(f"freelm momentum: datos dudosos, hoy no se opera ({why[:300]})")
        print(f"[aviso] datos dudosos, hoy no se opera: {why}", file=sys.stderr)
        return 0
    state, rep = mp_.step(state, data, fam)
    if rep["skipped"] and not rep["skipped"].startswith("detenido"):
        print(f"{mp_.utc(rep['day'])}: {rep['skipped']}")
        print(show())
        return 0
    for s, side, w in rep["trades"]:
        journal.write(rep["day"], {"tipo": "orden_papel", "estrategia": "momentum", "simbolo": s, "lado": side,
                                   "peso": round(w, 4)})
    track.append({"t": rep["day"] / 1000, "equity": state["equity"], "basket": rep.get("basket", 0.0),
                  "mode": "momentum"})
    record = track[-1]
    with open(tp, "a") as fh:
        fh.write(json.dumps(record) + "\n")
    mp_.save(sp, state)
    journal.write(rep["day"], {"tipo": "cartera", "estrategia": "momentum", "capital": round(state["equity"], 6),
                               "pesos": {s: round(w, 4) for s, w in state["weights"].items()},
                               "evento": rep["skipped"]})
    text = show()
    print(f"{mp_.utc(rep['day'])}: " + (f"{len(rep['trades'])} cambios de cartera" if rep["trades"] else
                                       "sin cambios") + (f" · {rep['skipped']}" if rep["skipped"] else ""))
    print(text)
    notifier.send("freelm " + text)
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    args.limit = max(args.limit, WINDOW + args.steps + 10)
    data = load_universe(args)
    eng = Engine(Config(), cash=args.cash)
    n = min(len(v) for v in data.values())
    for i in range(n - args.steps, n):
        eng.step({s: cs[i - WINDOW + 1: i + 1] for s, cs in data.items()})
    sps = eng.signals_per_second
    print(f"{eng.total_signals:,} señales en {eng.total_seconds:.2f}s -> {sps:,.0f} señales/segundo "
          f"({'supera' if sps >= 500 else 'NO llega a'} el mínimo de 500)")
    return 0 if sps >= 500 else 1


def cmd_graph(args: argparse.Namespace) -> int:
    eng = Engine(config_for(args))
    for g in (eng.symbol_graph, eng.portfolio_graph):
        print(f"%% grafo '{g.name}': orden de ejecución: " + " -> ".join(n.name for n in g.order()))
        print(g.mermaid())
        print()
    return 0


def _book_path(args: argparse.Namespace) -> str:
    return p(args, f"cartera-{args.exchange}.json")


def _track_path(args: argparse.Namespace) -> str:
    return p(args, f"historial-{args.exchange}.jsonl")


def cmd_conexion(args: argparse.Namespace, client: object = None) -> int:
    """Comprueba la conexión con el exchange: claves, saldo, mínimos de orden de cada moneda y,
    con --orden-prueba (solo testnet), una compra límite muy por debajo del precio que nunca
    se ejecuta y se cancela al momento. No compra ni vende nada."""
    if args.exchange == "papel":
        print("El modo papel no se conecta a ningún exchange: usa --exchange testnet (o real).")
        return 2
    if args.orden_prueba and args.exchange != "testnet":
        print("La orden de prueba solo se permite en testnet.")
        return 2
    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    try:
        ex = CcxtExecutor(args.exchange_id, testnet=args.exchange == "testnet", max_capital=args.max_capital,
                          client=client)
        print(f"Conectado a {ex.name}.")
        free = ex.free_quote()
        print(f"  Saldo libre: {free:,.2f} {ex.quote} · capital que usaría el bot: {ex.starting_cash():,.2f} "
              f"(tope {args.max_capital:,.2f})")
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 - mensaje claro en vez de traza
        print(f"  [X] No se pudo conectar: {type(e).__name__}: {e}")
        print("      Revisa que las claves sean de la testnet (testnet.binance.vision) o de la cuenta real, según el modo.")
        return 1
    ok = True
    for s in syms:
        m = to_market(s, ex.quote)
        mk = ex.ex.markets.get(m)
        if not mk:
            print(f"  [!] {m}: no existe en este exchange")
            ok = False
            continue
        lim = mk.get("limits", {})
        print(f"  [OK] {m}: mínimo {((lim.get('cost') or {}).get('min') or 0):g} {ex.quote} por orden")
    if args.orden_prueba:
        s = syms[0]
        m = to_market(s, ex.quote)
        price = float(ex.ex.fetch_ticker(m)["last"]) * 0.5  # a mitad de precio: no se ejecuta nunca
        min_cost = ((ex.ex.markets[m].get("limits", {}).get("cost") or {}).get("min") or 5)
        qty = (min_cost * 1.2) / price
        oid = ex.place_limit_buy(s, qty, price)
        if oid in (False, None):
            print("  [X] El exchange rechazó la orden de prueba (¿permiso de trading activado en la clave?).")
            return 1
        filled, _, status = ex.limit_status(s, oid)
        ex.cancel_limit(s, oid)
        print(f"  [OK] Orden de prueba colocada y cancelada ({m} a {price:,.2f}, estado '{status}', ejecutado {filled:g}).")
    print("Conexión correcta." if ok else "Conexión correcta, con avisos.")
    return 0 if ok else 1


def cmd_gate(args: argparse.Namespace) -> int:
    args.exchange = "papel"
    book = load_json(_book_path(args))
    ok, notes = check_gate(load_track(_track_path(args)), len(book.get("closed", [])))
    print("Puerta del dinero real (necesita superar la prueba de 20 días en papel):")
    for n in notes:
        print("  " + n)
    print("=> " + ("APTO: puedes pasar a dinero real con --exchange real --confirm-real-money." if ok
                   else "NO APTO todavía. Deja el bot en papel."))
    return 0 if ok else 1


def cmd_live(args: argparse.Namespace) -> int:
    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    executor = None
    cash = args.cash
    if args.exchange == "real":
        args_p = argparse.Namespace(**{**vars(args), "exchange": "papel"})
        ok, notes = check_gate(load_track(_track_path(args_p)), len(load_json(_book_path(args_p)).get("closed", [])))
        if not ok:
            print("Dinero real BLOQUEADO: el bot no ha superado la prueba de 20 días en papel.")
            for n in notes:
                print("  " + n)
            return 2
        if not args.confirm_real_money:
            print("Añade --confirm-real-money para operar con dinero real.")
            return 2
    if args.exchange in ("testnet", "real"):
        executor = CcxtExecutor(args.exchange_id, testnet=args.exchange == "testnet", max_capital=args.max_capital)
        cash = executor.starting_cash()
        print(f"Conectado a {executor.name}. Capital de trabajo: {cash:.2f} (tope {args.max_capital:.2f})")
    path = state_file(args) or p(args, f"memoria-binance-{args.interval}.json")
    book_path, track_path = _book_path(args), _track_path(args)
    fund_from = int(time.time() * 1000) - WINDOW * 3_600_000
    eng = Engine(config_for(args), load_json(path), cash=cash, executor=executor,
                 llm=build_llm(args.llm, args.llm_model), sentiment=load_sentiment(args),
                 funding=load_funding(args, syms, fund_from))
    fund_try = time.time()
    book = load_json(book_path)
    if book:  # recuperar la cartera
        eng.pf.cash = book["cash"]
        eng.pf.positions = {s: Position(**q) for s, q in book.get("positions", {}).items()}
        eng.pf.closed = [ClosedTrade(**c) for c in book.get("closed", [])]
        for k, v in book.get("risk", {}).items():
            setattr(eng.risk, k, v)
    last_seen = int(book.get("last_time", 0)) if book else 0  # no procesar dos veces la misma vela
    last_opt = book.get("last_optimize", "") if book else ""
    last_summary = book.get("last_summary", "") if book else ""
    tg = Notifier()
    sent_try = time.time()  # se acaba de descargar al crear el motor
    tag = "" if mode_is_paper(args) else "💶 REAL " if args.exchange == "real" else "🧪 TESTNET "
    mode = {"paper": "papel"}.get(args.exchange, args.exchange)
    journal = DecisionJournal(p(args, "diario"))
    reconciled = executor is None  # en papel no hay nada que conciliar
    errors = 0
    stale_warned = False
    print(f"Modo vivo ({eng.executor.name}): {', '.join(syms)} {args.interval}. Ctrl+C para salir.")
    print(f"  Diario de decisiones: {journal.dir}")
    while True:
        try:
            data = fetch_universe(syms, args.interval, WINDOW + 1)
            data = {s: cs[:-1] for s, cs in data.items()}  # la última vela aún está abierta
            t = min(cs[-1].time for cs in data.values())
            if errors >= 3:
                tg.send(f"{tag}✅ Conexión recuperada tras {errors} intentos fallidos.")
            errors = 0
            stale = [f"{s}: {m}" for s, cs in data.items()
                     if (m := check_fresh(cs, INTERVAL_SECONDS.get(args.interval, 3600)))]
            if stale:  # el exchange devuelve datos viejos: no se decide con ellos
                print(f"[aviso] {stale[0]} - no se opera en esta vuelta", file=sys.stderr)
                journal.write(int(time.time() * 1000), {"tipo": "aviso", "datos_atrasados": stale})
                if not stale_warned:
                    tg.send(f"{tag}⚠️ Datos atrasados del exchange ({stale[0]}). El bot no opera hasta que se normalicen.")
                    stale_warned = True
                if args.once:
                    return 1
                sleep_to_next_close(args.interval, args.poll)
                continue
            stale_warned = False
            if not reconciled:  # al arrancar: ¿la cartera guardada coincide con el exchange?
                prices0 = {s: cs[-1].close for s, cs in data.items()}
                for s in executor.reconcile(eng.pf.positions):
                    tr = eng.pf.close(s, prices0[s], t, "conciliación: ya no estaba en el exchange (stop ejecutado)")
                    eng.risk.on_closed(tr)
                    journal.write(t, {"tipo": "conciliacion", "simbolo": s, "resultado": round(tr.pnl, 6)})
                    tg.send(f"{tag}🔄 {s}: la posición ya no estaba en el exchange al arrancar; cerrada en el libro.")
                reconciled = True
            if t > last_seen:
                last_seen = t
                rep = eng.step(data)
                prices = {s: cs[-1].close for s, cs in data.items()}
                eq = eng.pf.equity(prices)
                ts = time.strftime("%Y-%m-%d %H:%M", time.gmtime(t / 1000))
                print(f"\n{ts}  capital {eq:,.2f}  ({rep.signals} señales en {rep.seconds * 1000:.0f} ms)")
                for s, d in rep.decisions.items():
                    st = "APROBADA" if d.approved else "; ".join(d.vetoes[:2])
                    print(f"  {s:<9} [{d.regime}] consejo {d.score:+.2f} acuerdo {d.agreement:.0%}  {st}")
                for q in rep.opened:
                    print(f"  >>> ABRE {q.symbol} a {q.entry:.4f}, stop {q.stop:.4f}, objetivo {q.target:.4f}")
                    tg.send(f"{tag}🟢 COMPRA {q.symbol} a {q.entry:.4f}\nstop {q.stop:.4f} · objetivo {q.target:.4f}\n"
                            f"{q.reason}")
                for c in rep.closed:
                    print(f"  <<< CIERRA {c.symbol} a {c.exit:.4f}: {c.pnl:+.2f} ({c.r:+.2f}R, {c.why})")
                    tg.send(f"{tag}{'✅' if c.pnl >= 0 else '🔻'} VENTA {c.symbol} a {c.exit:.4f}: {c.pnl:+.2f} "
                            f"({c.r:+.2f}R) · {c.why}\ncapital {eq:,.2f}")
                if rep.event == "HALT":
                    tg.send(f"{tag}🛑 INTERRUPTOR DE EMERGENCIA: caída del 10 %. El bot deja de operar.")
                save_json(path, eng.state())
                save_json(book_path, {"cash": eng.pf.cash,
                                      "positions": {s: asdict(q) for s, q in eng.pf.positions.items()},
                                      "risk": {k: v for k, v in asdict(eng.risk).items()},
                                      "closed": [asdict(c) for c in eng.pf.closed[-1000:]],
                                      "last_time": t, "last_optimize": last_opt, "last_summary": last_summary})
                record_equity(track_path, eq, mode)
                journal.step(t, rep, prices, eq)
                if rep.event == "DAILY":
                    tg.send(f"{tag}⛔ Límite de pérdida diaria alcanzado: sin nuevas entradas hasta mañana (UTC).")
                for s, probs in rep.data_issues.items():
                    print(f"  [datos dudosos] {s}: {probs[0]}", file=sys.stderr)
                day = time.strftime("%Y-%m-%d", time.gmtime())
                # el índice es diario y se publica a lo largo del día: reintentar (como mucho
                # una vez por hora) mientras falte el dato de hoy
                if (not args.no_sentiment and day not in (eng.sentiment or {})
                        and time.time() - sent_try > 3600):
                    sent_try = time.time()
                    eng.sentiment = load_sentiment(args) or eng.sentiment
                if time.time() - fund_try > 4 * 3600:  # el funding se liquida cada 8 h
                    fund_try = time.time()
                    eng.funding = load_funding(args, syms, fund_from) or eng.funding
                if tg.enabled and day != last_summary and time.gmtime().tm_hour >= args.summary_hour:
                    last_summary = day
                    tg.send(build_report(args, markdown=False))
                    book_now = load_json(book_path)
                    book_now["last_summary"] = last_summary
                    save_json(book_path, book_now)
                today = time.strftime("%Y-%m-%d", time.gmtime())
                if args.auto_optimize and today != last_opt and time.gmtime().tm_hour >= args.optimize_hour:
                    last_opt = today
                    eng = _reoptimize(args, eng, path)
                    book_now = load_json(book_path)
                    book_now["last_optimize"] = last_opt
                    save_json(book_path, book_now)
            if args.once:
                return 0
        except KeyboardInterrupt:
            return 0
        except Exception as e:  # noqa: BLE001 - un fallo de red no debe matar el bucle
            errors += 1
            print(f"[error] {type(e).__name__}: {e}", file=sys.stderr)
            journal.write(int(time.time() * 1000), {"tipo": "error", "error": f"{type(e).__name__}: {e}"})
            if errors == 3:
                tg.send(f"{tag}⚠️ Sin conexión o error repetido (3 veces): {type(e).__name__}. El bot no opera "
                        "mientras dure; las posiciones siguen protegidas por su stop en el exchange.")
            if args.once:
                return 1
        try:
            sleep_to_next_close(args.interval, args.poll)
        except KeyboardInterrupt:
            return 0


def mode_is_paper(args: argparse.Namespace) -> bool:
    return args.exchange == "papel"


def build_report(args: argparse.Namespace, markdown: bool = True) -> str:
    """Resumen del modo en vivo: capital, rendimiento, operaciones, puerta del dinero real."""
    book = load_json(_book_path(args))
    track = load_track(_track_path(args))
    paper = argparse.Namespace(**{**vars(args), "exchange": "papel"})
    ok, notes = check_gate(load_track(_track_path(paper)), len(load_json(_book_path(paper)).get("closed", [])))
    lines: List[str] = []
    h = "### " if markdown else ""
    lines.append(f"{h}Bot de trading ({args.exchange}) · {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}")
    if len(track) >= 2:
        eq = [r["equity"] for r in track]
        days = (track[-1]["t"] - track[0]["t"]) / 86_400
        ret = eq[-1] / eq[0] - 1
        peak, mdd = eq[0], 0.0
        for e in eq:
            peak = max(peak, e)
            mdd = max(mdd, 1 - e / peak)
        day_ago = [r["equity"] for r in track if r["t"] >= track[-1]["t"] - 86_400]
        weekly = (1 + ret) ** (7 / days) - 1 if days >= 1 and ret > -1 else 0.0
        lines += [f"- Capital: **{eq[-1]:,.2f}** (inicio {eq[0]:,.2f}, {days:.1f} días)",
                  f"- Rendimiento: **{ret:+.2%}** · últimas 24 h {eq[-1] / day_ago[0] - 1:+.2%} · "
                  f"semanal equivalente {weekly:+.2%} (meta +18 %)",
                  f"- Caída máxima: {mdd:.2%} (límite 10 %)"]
        if days >= 2:  # informe profesional (estilo quantstats) a partir de 2 días de historial
            trades = [SimpleNamespace(pnl=c["pnl"]) for c in book.get("closed", [])]
            perf = performance(eq, [r["t"] * 1000 for r in track], PERIODS_PER_YEAR.get(args.interval, 8_760), trades)
            lines += ["-" + x[1:] for x in format_performance(perf)]
    else:
        lines.append("- Aún sin historial en vivo.")
    closed = book.get("closed", [])
    if len(closed) >= 5:
        risk = config_for(args).risk_per_trade  # historiales antiguos sin risk_frac
        st = stress_test([c["r"] * (c.get("risk_frac") or risk) for c in closed], 1.0)
        lines.append(f"- Prueba de estrés: caída típica {st['dd_p50']:.1%}, mala racha (peor 5 %) {st['dd_p95']:.1%}")
    if closed:
        wins = sum(1 for c in closed if c["pnl"] > 0)
        lines.append(f"- Operaciones cerradas: {len(closed)} · ganadoras {wins} ({wins / len(closed):.0%}) · "
                     f"resultado {sum(c['pnl'] for c in closed):+.2f}")
        for c in closed[-3:]:
            lines.append(f"  - {c['symbol']} {c['pnl']:+.2f} ({c['r']:+.2f}R, {c['why']})")
    pos = book.get("positions", {})
    open_txt = ", ".join(f"{s} desde {q['entry']:.4f}" for s, q in pos.items()) or "ninguna"
    lines.append(f"- Posiciones abiertas: {open_txt}")
    champ = load_json(p(args, "champion.json"))
    if champ:
        hh = champ.get("holdout", {})
        lines.append(f"- Configuración campeona del {champ.get('date', '?')}: examen final {hh.get('return', 0):+.2%}, "
                     f"caída {hh.get('max_drawdown', 0):.1%}")
    lines.append(f"{h}Puerta del dinero real: {'✅ APTO' if ok else '⏳ todavía no'}")
    lines += [f"- {n}" for n in notes]
    return "\n".join(lines)


def cmd_report(args: argparse.Namespace) -> int:
    print(build_report(args, markdown=not args.plain))
    return 0


def _reoptimize(args: argparse.Namespace, eng: Engine, path: str) -> Engine:
    """Ronda diaria de mejora dentro del propio bucle en vivo. Si sale una nueva
    campeona, el motor se reconstruye con ella conservando cartera y memoria."""
    print("\n[autopiloto] ronda diaria de optimización...")
    # todas las opciones que lee cmd_optimize (live no define --workers: antes fallaba aquí cada día)
    oargs = argparse.Namespace(**{**vars(args), "source": "binance", "limit": args.optimize_limit,
                                  "population": 16, "generations": 8, "min_trades": 10, "seed": int(time.time()),
                                  "workers": getattr(args, "workers", 0)})
    try:
        cmd_optimize(oargs)
    except (Exception, SystemExit) as e:  # noqa: BLE001 - optimizar es opcional, operar no se detiene
        print(f"[autopiloto] optimización omitida: {type(e).__name__}: {e}", file=sys.stderr)
        return eng
    cfg = config_for(args)
    if cfg == eng.cfg:
        return eng
    new = Engine(cfg, eng.state(), cash=eng.pf.cash, executor=eng.executor, llm=eng.llm, sentiment=eng.sentiment,
                 funding=eng.funding)
    new.pf, new.risk.peak_equity, new.risk.halted = eng.pf, eng.risk.peak_equity, eng.risk.halted
    new.risk.losing_streak, new.risk.pause_left = eng.risk.losing_streak, eng.risk.pause_left
    save_json(path, new.state())
    print("[autopiloto] nueva campeona activada")
    return new


def cmd_status(args: argparse.Namespace) -> int:
    champ = load_json(p(args, "champion.json"))
    if champ:
        h = champ.get("holdout", {})
        print(f"Campeona ({champ.get('date')}): examen final {h.get('return', 0):+.2%}, "
              f"caída {h.get('max_drawdown', 0):.1%}, {h.get('trades', 0)} operaciones")
    hist = p(args, "optimize_history.jsonl")
    if os.path.exists(hist):
        with open(hist) as fh:
            rows = [json.loads(x) for x in fh if x.strip()]
        print(f"Rondas de mejora: {len(rows)} ({sum(r['accepted'] for r in rows)} aceptadas)")
    state = load_json(state_file(args))
    if not state and not champ:
        print("Sin memoria todavía. Ejecuta backtest, optimize o live.")
        return 1
    if state:
        print()
        print_learning(state, top=5)
        print_ic(state, full=args.all_agents)
    return 0


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Bot multiagente de señales cripto que aprende y se mejora solo.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(sp: argparse.ArgumentParser, source_default: str = "synthetic", limit: int = 3000) -> None:
        sp.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
        sp.add_argument("--interval", default="1h", choices=sorted(PERIODS_PER_YEAR))
        sp.add_argument("--source", default=source_default, choices=["synthetic", "binance", "csv"])
        sp.add_argument("--csv", help="plantilla de ruta, p. ej. datos/{symbol}.csv")
        sp.add_argument("--limit", type=int, default=limit, help="velas por símbolo")
        sp.add_argument("--seed", type=int, default=7)
        sp.add_argument("--structure", type=float, default=1.0, help="inercia de los datos sintéticos (0 = azar)")
        sp.add_argument("--dir", help=f"carpeta de memoria (por defecto {STATE_DIR})")
        sp.add_argument("--state", help="archivo de memoria del aprendizaje")
        sp.add_argument("--no-memory", action="store_true", help="no leer ni guardar lo aprendido")
        sp.add_argument("--config", help="usar la configuración de este JSON")
        sp.add_argument("--default-config", action="store_true", help="ignorar la campeona guardada")
        sp.add_argument("--cash", type=float, default=10_000.0)
        sp.add_argument("--llm", action="store_true", help="la IA (freelm) revisa cada operación antes de abrirla")
        sp.add_argument("--llm-model", default="chat:fast")
        sp.add_argument("--no-sentiment", action="store_true", help="no descargar el índice Fear & Greed")
        sp.add_argument("--no-funding", action="store_true", help="no descargar el funding rate de futuros")
        sp.add_argument("--entry-mode", choices=["market", "limit"],
                        help="tipo de orden de entrada (por defecto, el de la configuración: market)")
        sp.add_argument("--bnb", action="store_true", help="comisiones con descuento BNB (0,075 %% por lado)")

    b = sub.add_parser("backtest", help="aprender y validar fuera de muestra")
    common(b)
    b.add_argument("--train", type=float, default=0.6, help="fracción de velas para aprender sin operar")
    b.add_argument("-v", "--verbose", action="store_true")
    b.set_defaults(func=cmd_backtest)

    o = sub.add_parser("optimize", help="una ronda de mejora automática (para cron diario)")
    common(o)
    o.add_argument("--population", type=int, default=12)
    o.add_argument("--generations", type=int, default=6)
    o.add_argument("--min-trades", type=int, default=10)
    o.add_argument("--workers", type=int, default=0, help="procesos en paralelo (0 = todos los núcleos)")
    o.set_defaults(func=cmd_optimize)

    va = sub.add_parser("validate", help="validación estadística: walk-forward, Deflated Sharpe, PBO, sensibilidad")
    common(va)
    va.add_argument("--horizons", default="1,6,12,24,36", help="valores de learn_horizon a validar")
    va.add_argument("--rules", default="77,ev50", help="reglas de entrada: 77 (la del usuario) y/o ev50")
    va.add_argument("--learn", type=float, default=0.4, help="fracción inicial solo para aprender")
    va.add_argument("--prior-trials", type=int, default=20,
                    help="pruebas hechas antes con estos datos (se descuentan en el Deflated Sharpe)")
    va.add_argument("--workers", type=int, default=0, help="procesos en paralelo (0 = todos los núcleos)")
    va.set_defaults(func=cmd_validate)

    cl = sub.add_parser("classic", help="validar estrategias clásicas (momentum) con las mismas pruebas")
    common(cl, limit=3000)
    cl.set_defaults(interval="1d")
    cl.add_argument("--target-vol", type=float, default=0.05,
                    help="volatilidad anual objetivo (regla fijada: caída máxima / 2 = 5 %%)")
    cl.add_argument("--risk-model", choices=["cov", "corr1"], default="cov")
    cl.add_argument("--dd-budget", type=float, default=0.0, help="control de caída tipo CPPI (0 = apagado)")
    cl.add_argument("--dd-window", type=int, default=0, help="días del máximo de referencia (0 = histórico)")
    cl.add_argument("--aligned", dest="full_history", action="store_false",
                    help="solo fechas comunes a todas las monedas (antes: por defecto)")
    cl.add_argument("--prior-trials", type=int, default=95,
                    help="pruebas hechas antes con estos datos (se descuentan en el Deflated Sharpe)")
    cl.set_defaults(func=cmd_classic)

    mo = sub.add_parser("momentum", help="momentum combinado en PAPEL: prueba de 20 días (1 día por ejecución)")
    mo.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    mo.add_argument("--limit", type=int, default=260, help="velas diarias que se descargan")
    mo.add_argument("--dir", help=f"carpeta de memoria (por defecto {STATE_DIR})")
    mo.add_argument("--cash", type=float, default=100.0)
    mo.add_argument("--target-vol", type=float, default=0.05, help="la configuración validada usa 5 %%")
    mo.add_argument("--risk-model", choices=["cov", "corr1"], default="cov")
    mo.add_argument("--bnb", action="store_true", help="comisiones con descuento BNB")
    mo.add_argument("--report", action="store_true", help="solo mostrar cómo va")
    mo.add_argument("--continue-after", action="store_true", help="seguir en papel después de los 20 días")
    mo.set_defaults(func=cmd_momentum)

    be = sub.add_parser("bench", help="medir señales por segundo")
    common(be)
    be.add_argument("--steps", type=int, default=30)
    be.set_defaults(func=cmd_bench)

    g = sub.add_parser("graph", help="dibujar el grafo de nodos (Mermaid)")
    common(g)
    g.set_defaults(func=cmd_graph)

    lv = sub.add_parser("live", help="tiempo real (papel / testnet / real)")
    common(lv, "binance")
    lv.add_argument("--exchange", default="papel", choices=["papel", "testnet", "real"])
    lv.add_argument("--exchange-id", default="binance", help="cualquier exchange de ccxt: binance, kraken, bitvavo...")
    lv.add_argument("--max-capital", type=float, default=100.0, help="tope duro de capital en modo testnet/real")
    lv.add_argument("--confirm-real-money", action="store_true")
    lv.add_argument("--poll", type=float, default=0.0,
                    help="segundos entre consultas (0 = justo al cierre de cada vela, recomendado)")
    lv.add_argument("--once", action="store_true", help="procesar una vela y salir (para cron)")
    lv.add_argument("--auto-optimize", action="store_true", help="una ronda de mejora al día dentro del bucle")
    lv.add_argument("--optimize-hour", type=int, default=3, help="hora UTC de la ronda diaria")
    lv.add_argument("--summary-hour", type=int, default=7, help="hora UTC del resumen diario por Telegram")
    lv.add_argument("--optimize-limit", type=int, default=5000, help="velas por símbolo para optimizar")
    # tiempo real: velas de 5 min por defecto (decisión al segundo del cierre de cada vela)
    lv.set_defaults(func=cmd_live, cash=100.0, interval="5m")  # simular con el mismo capital que se usará de verdad

    rp = sub.add_parser("report", help="resumen del modo en vivo (Markdown)")
    common(rp, "binance")
    rp.add_argument("--exchange", default="papel", choices=["papel", "testnet", "real"])
    rp.add_argument("--plain", action="store_true", help="texto sin formato (para Telegram)")
    rp.set_defaults(func=cmd_report)

    cx = sub.add_parser("conexion", help="comprobar claves, saldo y órdenes con el exchange (testnet o real)")
    common(cx, "binance")
    cx.add_argument("--exchange", default="testnet", choices=["papel", "testnet", "real"])
    cx.add_argument("--exchange-id", default="binance")
    cx.add_argument("--max-capital", type=float, default=100.0)
    cx.add_argument("--orden-prueba", action="store_true",
                    help="(solo testnet) coloca y cancela una compra límite a mitad de precio")
    cx.set_defaults(func=cmd_conexion)

    gt = sub.add_parser("gate", help="¿ha superado la prueba de 20 días?")
    common(gt, "binance")
    gt.set_defaults(func=cmd_gate)

    st = sub.add_parser("status", help="ver lo aprendido y la campeona")
    common(st)
    st.add_argument("--all-agents", action="store_true", help="tabla de IC de todos los agentes")
    st.set_defaults(func=cmd_status)
    return ap


def _utf8_console() -> None:
    """En Windows, la consola o un fichero redirigido pueden usar cp1252: los acentos y
    símbolos (≥, ✔, …) romperían el bot con UnicodeEncodeError. Se fuerza UTF-8."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001 - flujos sin reconfigure (tests, pipes antiguos)
            pass


def main(argv: Optional[List[str]] = None) -> int:
    _utf8_console()
    args = parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
