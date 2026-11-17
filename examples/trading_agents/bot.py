"""Bot multiagente de señales cripto: grafo de nodos, aprendizaje y mejora automática.

    python bot.py graph                         # dibuja el grafo de nodos (Mermaid)
    python bot.py bench                         # señales por segundo
    python bot.py backtest                      # aprender + validar fuera de muestra
    python bot.py optimize                      # una ronda de mejora automática
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
from dataclasses import asdict
from typing import Dict, List, Optional

from agents import LLMAnalystAgent
from engine import WINDOW, Config, Engine, metrics, run_backtest, trade_stats
from exchange import CcxtExecutor, check_gate, load_track, record_equity
from learning import REGIMES, Calibrator
from market import DEFAULT_SYMBOLS, Candle, align, fetch_binance, load_csv, synthetic
from optimize import Optimizer, load_champion, save_result
from risk import ClosedTrade, Position

STATE_DIR = os.environ.get("FREELM_TRADING_DIR", os.path.join(os.path.expanduser("~"), ".cache", "freelm-trading"))
PERIODS_PER_YEAR = {"15m": 35_040, "1h": 8_760, "4h": 2_190, "1d": 365}


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
        return Config.from_dict(load_json(args.config).get("config"))
    if not args.default_config:
        champ = load_champion(p(args, "champion.json"))
        if champ:
            return champ
    return Config()


def state_file(args: argparse.Namespace) -> Optional[str]:
    if getattr(args, "no_memory", False):
        return None
    return args.state or p(args, f"memoria-{args.source}-{args.interval}.json")


def load_universe(args: argparse.Namespace) -> Dict[str, List[Candle]]:
    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if args.source == "binance":
        data = {}
        for s in syms:
            try:
                data[s] = fetch_binance(s, args.interval, args.limit)
            except Exception as e:  # noqa: BLE001 - un símbolo caído no tumba el resto
                print(f"[aviso] {s}: {type(e).__name__}: {e}", file=sys.stderr)
        return align(data)
    if args.source == "csv":
        if not args.csv:
            raise SystemExit("--source csv necesita --csv PLANTILLA (p. ej. datos/{symbol}.csv)")
        return align({s: load_csv(args.csv.format(symbol=s)) for s in syms})
    return {s: synthetic(args.limit, seed=args.seed + i, start=100.0 * (i + 1), structure=args.structure)
            for i, s in enumerate(syms)}


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
    rows = Calibrator.from_dict(state.get("calibrator")).table()
    if rows:
        print("\nCalibrador: esperanza medida en la sombra por tipo de señal (R = riesgo arriesgado)")
        print(f"  {'tipo':<28}{'casos':>7}{'media':>8}{'acierto':>9}{'conservadora':>14}")
        for k, n, mean, wr, e in rows[:10]:
            print(f"  {k:<28}{n:>7}{mean:>+8.2f}{wr:>9.0%}{e:>+13.2f}R")


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
    eng = Engine(config_for(args), load_json(path), cash=args.cash, llm=build_llm(args.llm, args.llm_model))
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
    print(f"  señales procesadas: {eng.total_signals:,} a {eng.signals_per_second:,.0f}/s")
    vetoes = sorted(eng.veto_counts.items(), key=lambda kv: -kv[1])
    print("  vetos: " + ", ".join(f"{k} {v:,}" for k, v in vetoes[:5]))
    ok_dd = m["max_drawdown"] <= 0.10
    print(f"\nObjetivo acordado (máximo rendimiento con caída ≤ 10 %): caída {m['max_drawdown']:.1%} "
          f"{'✔' if ok_dd else '✘'}  ·  tu meta del +18 % semanal: {m['weekly']:+.2%} por semana"
          + ("  [datos sintéticos]" if args.source == "synthetic" else ""))
    print()
    print_learning(eng.state())
    if path:
        save_json(path, eng.state())
        print(f"\nMemoria guardada en {path}")
    return 0


def cmd_optimize(args: argparse.Namespace) -> int:
    data = load_universe(args)
    if not data:
        raise SystemExit("sin datos")
    champ_path, hist_path = p(args, "champion.json"), p(args, "optimize_history.jsonl")
    champ = None if args.default_config else load_champion(champ_path)
    opt = Optimizer(data, PERIODS_PER_YEAR.get(args.interval, 8_760), cash=args.cash, seed=args.seed,
                    min_trades=args.min_trades)
    sp = {"aprender": opt.val_from - opt.start, "validación": opt.test_from - opt.val_from,
          "examen": opt.n - opt.test_from}
    print(f"Optimizando sobre {', '.join(data)} ({args.source}, {args.interval}): "
          + ", ".join(f"{k} {v} velas" for k, v in sp.items()))
    print(f"Campeona de partida: {'la guardada' if champ else 'configuración por defecto'}")
    res = opt.run(champ, population=args.population, generations=args.generations)
    ct, ht = res["candidate_test"], res["champion_test"]
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
    eng = Engine(config_for(args), load_json(path), cash=cash, executor=executor,
                 llm=build_llm(args.llm, args.llm_model))
    book = load_json(book_path)
    if book:  # recuperar la cartera
        eng.pf.cash = book["cash"]
        eng.pf.positions = {s: Position(**q) for s, q in book.get("positions", {}).items()}
        eng.pf.closed = [ClosedTrade(**c) for c in book.get("closed", [])]
        for k, v in book.get("risk", {}).items():
            setattr(eng.risk, k, v)
    last_seen = int(book.get("last_time", 0)) if book else 0  # no procesar dos veces la misma vela
    last_opt = book.get("last_optimize", "") if book else ""
    mode = {"paper": "papel"}.get(args.exchange, args.exchange)
    print(f"Modo vivo ({eng.executor.name}): {', '.join(syms)} {args.interval}. Ctrl+C para salir.")
    while True:
        try:
            data = align({s: fetch_binance(s, args.interval, WINDOW + 1)[:-1] for s in syms})  # última vela abierta
            t = min(cs[-1].time for cs in data.values())
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
                for c in rep.closed:
                    print(f"  <<< CIERRA {c.symbol} a {c.exit:.4f}: {c.pnl:+.2f} ({c.r:+.2f}R, {c.why})")
                save_json(path, eng.state())
                save_json(book_path, {"cash": eng.pf.cash,
                                      "positions": {s: asdict(q) for s, q in eng.pf.positions.items()},
                                      "risk": {k: v for k, v in asdict(eng.risk).items()},
                                      "closed": [asdict(c) for c in eng.pf.closed[-1000:]],
                                      "last_time": t, "last_optimize": last_opt})
                record_equity(track_path, eq, mode)
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
            print(f"[error] {type(e).__name__}: {e}", file=sys.stderr)
            if args.once:
                return 1
        try:
            time.sleep(args.poll)
        except KeyboardInterrupt:
            return 0


def _reoptimize(args: argparse.Namespace, eng: Engine, path: str) -> Engine:
    """Ronda diaria de mejora dentro del propio bucle en vivo. Si sale una nueva
    campeona, el motor se reconstruye con ella conservando cartera y memoria."""
    print("\n[autopiloto] ronda diaria de optimización...")
    oargs = argparse.Namespace(**{**vars(args), "source": "binance", "limit": args.optimize_limit,
                                  "population": 10, "generations": 5, "min_trades": 10, "seed": int(time.time())})
    try:
        cmd_optimize(oargs)
    except (Exception, SystemExit) as e:  # noqa: BLE001 - optimizar es opcional, operar no se detiene
        print(f"[autopiloto] optimización omitida: {type(e).__name__}: {e}", file=sys.stderr)
        return eng
    cfg = config_for(args)
    if cfg == eng.cfg:
        return eng
    new = Engine(cfg, eng.state(), cash=eng.pf.cash, executor=eng.executor, llm=eng.llm)
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
    o.set_defaults(func=cmd_optimize)

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
    lv.add_argument("--poll", type=float, default=60.0)
    lv.add_argument("--once", action="store_true", help="procesar una vela y salir (para cron)")
    lv.add_argument("--auto-optimize", action="store_true", help="una ronda de mejora al día dentro del bucle")
    lv.add_argument("--optimize-hour", type=int, default=3, help="hora UTC de la ronda diaria")
    lv.add_argument("--optimize-limit", type=int, default=5000, help="velas por símbolo para optimizar")
    lv.set_defaults(func=cmd_live, cash=100.0)  # simular con el mismo capital que se usará de verdad

    gt = sub.add_parser("gate", help="¿ha superado la prueba de 20 días?")
    common(gt, "binance")
    gt.set_defaults(func=cmd_gate)

    st = sub.add_parser("status", help="ver lo aprendido y la campeona")
    common(st)
    st.set_defaults(func=cmd_status)
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    args = parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
