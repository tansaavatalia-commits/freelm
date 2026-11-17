"""Bot multiagente de señales cripto que aprende solo. SOLO PAPER TRADING.

~100 agentes por símbolo en 6 equipos, varios símbolos a la vez (8 por
defecto, unas 800 señales por vela). Las señales se confrontan en dos
niveles (equipo y consejo). Después pasan por un equipo escéptico con veto y
por un calibrador que solo deja operar los tipos de señal con ventaja neta
demostrada. Ver README.md.

    python examples/trading_agents/bot.py backtest                    # sin red: datos sintéticos
    python examples/trading_agents/bot.py backtest --source binance --limit 4000
    python examples/trading_agents/bot.py bench                       # señales por segundo
    python examples/trading_agents/bot.py live --llm                  # tiempo real (papel)
    python examples/trading_agents/bot.py status

Esto es material educativo, no asesoramiento financiero. Ningún sistema puede
garantizar beneficios ni evitar todas las pérdidas. El bot no envía órdenes
reales a ningún exchange.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence

from agents import Agent, LLMAnalystAgent, agent_swarm
from features import Features
from learning import REGIMES, Calibrator, detect_regime
from market import DEFAULT_SYMBOLS, Candle, align, fetch_binance, load_csv, synthetic
from risk import ClosedTrade, Portfolio, Position, RiskManager
from teams import Council, Decision, Team

WINDOW = 320
SHADOW_GAP = 6  # como mucho una operación en la sombra por símbolo cada N velas (muestras menos correlacionadas)
STATE_DIR = os.environ.get("FREELM_TRADING_DIR", os.path.join(os.path.expanduser("~"), ".cache", "freelm-trading"))
PERIODS_PER_YEAR = {"15m": 35_040, "1h": 8_760, "4h": 2_190, "1d": 365}


def build_teams(state: Optional[dict] = None, swarm: Optional[Sequence[Agent]] = None) -> Dict[str, Team]:
    groups: Dict[str, List[Agent]] = {}
    for a in (swarm if swarm is not None else agent_swarm()):
        if a.warmup <= WINDOW:
            groups.setdefault(a.team, []).append(a)
    st = (state or {}).get("teams", {})
    return {name: Team(name, ags, st.get(name)) for name, ags in groups.items()}


@dataclass
class StepReport:
    decisions: Dict[str, Decision] = field(default_factory=dict)
    opened: List[Position] = field(default_factory=list)
    closed: List[ClosedTrade] = field(default_factory=list)
    signals: int = 0
    seconds: float = 0.0
    event: Optional[str] = None


class Engine:
    def __init__(self, teams: Dict[str, Team], council: Council, calibrator: Calibrator, portfolio: Portfolio,
                 risk: RiskManager, llm_agent: Optional[LLMAnalystAgent] = None) -> None:
        self.teams, self.council, self.cal = teams, council, calibrator
        self.pf, self.risk, self.llm = portfolio, risk, llm_agent
        self.warmup = min(WINDOW, max(a.warmup for t in teams.values() for a in t.agents) + 1)
        self._pending: Dict[str, tuple] = {}
        self._last_shadow: Dict[str, int] = {}
        self._step = 0
        self.total_signals = 0
        self.total_seconds = 0.0
        self.llm_vetoes = 0

    def step(self, windows: Dict[str, Sequence[Candle]], trading: bool = True) -> StepReport:
        rep = StepReport()
        t0 = time.perf_counter()
        prices: Dict[str, float] = {}
        candidates: List[tuple] = []
        now = 0
        for sym, window in windows.items():
            c = window[-1]
            now, prices[sym] = c.time, c.close
            f = Features(window, sym)
            vol = f.vol()

            # 1) aprender de lo que pasó desde la vela anterior (equipos y consejo)
            pend = self._pending.get(sym)
            if pend:
                team_sigs, agent_sigs, regime_prev, prev_close = pend
                ret = math.log(c.close / prev_close)
                for name, sigs in agent_sigs.items():
                    self.teams[name].coord.learn(sigs, regime_prev, ret, vol)
                self.council.coord.learn(team_sigs, regime_prev, ret, vol)
            self.cal.update(sym, c.high, c.low, c.close)

            # 2) cada equipo delibera; 3) el consejo confronta a los equipos
            regime = detect_regime(f)
            team_sigs, agent_sigs = [], {}
            for name, team in self.teams.items():
                v, sigs = team.verdict(f, regime)
                team_sigs.append(v)
                agent_sigs[name] = sigs
                rep.signals += len(sigs) + 1
            d = self.council.decide(sym, f, regime, team_sigs)
            rep.decisions[sym] = d
            self._pending[sym] = (team_sigs, agent_sigs, regime, c.close)

            # 4) operación en la sombra para medir si este tipo de señal tiene ventaja
            atr = f.atr(14)[-1]
            if atr and d.score >= self.council.enter and self._step - self._last_shadow.get(sym, -SHADOW_GAP) >= SHADOW_GAP:
                stop, target = self.risk.levels(c.close, atr)
                self.cal.record(sym, d.key, c.close, stop, target)
                self._last_shadow[sym] = self._step

            # 5) gestionar la posición abierta
            t = self.risk.manage(self.pf, sym, c.time, c.high, c.low, c.close, atr, d.score)
            if t:
                rep.closed.append(t)
            if trading and d.approved and atr and sym not in self.pf.positions:
                e, _ = self.cal.edge(d.key)
                candidates.append((e * d.score, sym, d, f, atr))

        rep.seconds = time.perf_counter() - t0
        self.total_signals += rep.signals
        self.total_seconds += rep.seconds

        equity = self.pf.equity(prices)
        rep.event = self.risk.tick(self.pf, equity, prices, now)

        # 6) abrir las mejores candidatas (con revisión final de la IA si está activa)
        for _, sym, d, f, atr in sorted(candidates, key=lambda x: -x[0]):
            if self.risk.can_open(self.pf):
                break
            if self.llm is not None:
                self.llm.peer_signals = d.teams
                s = self.llm.analyze(f)
                if s.value < 0:
                    self.llm_vetoes += 1
                    d.vetoes.append(f"IA en contra: {s.reason}")
                    continue
            price = prices[sym]
            qty = self.risk.size(self.pf, equity, price, atr)
            if qty * price < 10:
                continue
            stop, target = self.risk.levels(price, atr)
            pos = Position(sym, qty, price, stop, target, price - stop, now, price,
                           f"consejo {d.score:+.2f}, acuerdo {d.agreement:.0%}, {d.edge_note}")
            self.pf.open(pos)
            rep.opened.append(pos)
        self._step += 1
        return rep

    @property
    def signals_per_second(self) -> float:
        return self.total_signals / self.total_seconds if self.total_seconds else 0.0

    def state(self) -> dict:
        return {"teams": {n: t.coord.to_dict() for n, t in self.teams.items()},
                "council": self.council.coord.to_dict(), "calibrator": self.cal.to_dict()}


# --------------------------------------------------------------------------- construcción

def load_state(path: Optional[str]) -> dict:
    if path and os.path.exists(path):
        with open(path) as fh:
            return json.load(fh)
    return {}


def save_state(path: str, engine: Engine) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(engine.state(), fh, ensure_ascii=False)
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


def make_engine(args: argparse.Namespace, state: dict) -> Engine:
    teams = build_teams(state)
    cal = Calibrator.from_dict(state.get("calibrator"), min_samples=args.min_samples, min_edge=args.min_edge)
    council = Council(list(teams), cal, state.get("council"), min_agreement=args.min_agreement,
                      block_volatile=not args.allow_volatile)
    return Engine(teams, council, cal, Portfolio(cash=args.cash),
                  RiskManager(risk_per_trade=args.risk, peak_equity=args.cash, max_positions=args.max_positions),
                  build_llm(args.llm, args.llm_model))


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
            raise SystemExit("--source csv necesita --csv RUTA (un archivo por símbolo: RUTA con {symbol})")
        return align({s: load_csv(args.csv.format(symbol=s)) for s in syms})
    return {s: synthetic(args.limit, seed=args.seed + i, start=100.0 * (i + 1), structure=args.structure)
            for i, s in enumerate(syms)}


def state_path(args: argparse.Namespace) -> Optional[str]:
    if getattr(args, "no_memory", False):
        return None
    return args.state or os.path.join(STATE_DIR, f"{args.source if hasattr(args, 'source') else 'binance'}"
                                                 f"-{args.interval}.json")


# --------------------------------------------------------------------------- métricas e informes

def metrics(equity: Sequence[float], periods_per_year: int) -> Dict[str, float]:
    rets = [equity[i] / equity[i - 1] - 1 for i in range(1, len(equity)) if equity[i - 1] > 0]
    mean = sum(rets) / len(rets) if rets else 0.0
    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / len(rets)) if rets else 0.0
    peak, mdd = equity[0], 0.0
    for e in equity:
        peak = max(peak, e)
        mdd = max(mdd, 1 - e / peak)
    total = equity[-1] / equity[0] - 1
    years = max(len(equity) - 1, 1) / periods_per_year
    return {"return": total, "annual": (1 + total) ** (1 / years) - 1 if total > -1 else -1.0,
            "max_drawdown": mdd, "sharpe": mean / sd * math.sqrt(periods_per_year) if sd else 0.0}


def trade_stats(trades: Sequence[ClosedTrade]) -> Dict[str, float]:
    wins = [t.pnl for t in trades if t.pnl > 0]
    losses = [-t.pnl for t in trades if t.pnl <= 0]
    return {"n": len(trades), "win_rate": len(wins) / len(trades) if trades else 0.0,
            "profit_factor": sum(wins) / sum(losses) if losses else (math.inf if wins else 0.0),
            "avg_r": sum(t.r for t in trades) / len(trades) if trades else 0.0}


def print_learning(state: dict, top: int = 3) -> None:
    council = state.get("council", {}).get("weights", {})
    print("\nConsejo: peso de cada equipo por régimen")
    for reg in REGIMES:
        if reg in council:
            print(f"  {reg:<10} " + ", ".join(f"{a} {w:.0%}" for a, w in sorted(council[reg].items(),
                                                                              key=lambda kv: -kv[1])))
    print(f"\nMejores agentes de cada equipo (top {top}, régimen tendencia | lateral)")
    for name, t in state.get("teams", {}).items():
        w = t.get("weights", {})
        best = [", ".join(a for a, _ in sorted(w.get(reg, {}).items(), key=lambda kv: -kv[1])[:top])
                for reg in ("tendencia", "lateral")]
        print(f"  {name:<12} {best[0]}  |  {best[1]}")
    cal = Calibrator.from_dict(state.get("calibrator"))
    rows = cal.table()
    if rows:
        print("\nCalibrador: esperanza medida en la sombra por tipo de señal (R = riesgo arriesgado)")
        print(f"  {'tipo':<28}{'casos':>7}{'media':>8}{'acierto':>9}{'conservadora':>14}")
        for k, n, mean, wr, e in rows[:12]:
            print(f"  {k:<28}{n:>7}{mean:>+8.2f}{wr:>9.0%}{e:>+13.2f}R")


def run_backtest(engine: Engine, data: Dict[str, List[Candle]], train: float, verbose: bool = False) -> dict:
    n = min(len(v) for v in data.values())
    start = engine.warmup
    split = start + int((n - start) * train)
    if n - split < 50:
        raise SystemExit(f"pocas velas ({n}); usa --limit mayor")
    equity: List[float] = []
    first_px = {s: data[s][split].close for s in data}
    for i in range(start, n):
        trading = i >= split
        windows = {s: cs[max(0, i - WINDOW + 1): i + 1] for s, cs in data.items()}
        rep = engine.step(windows, trading=trading)
        if trading:
            equity.append(engine.pf.equity({s: data[s][i].close for s in data}))
        if verbose and trading:
            for p in rep.opened:
                print(f"  ABRE  {p.symbol:<9} {p.entry:>11.4f}  stop {p.stop:.4f}  obj {p.target:.4f}  ({p.reason})")
            for t in rep.closed:
                print(f"  CIERRA {t.symbol:<8} {t.exit:>11.4f}  {t.r:+.2f}R  {t.pnl:+.2f}  ({t.why})")
        if rep.event:
            print(f"  [{rep.event}] interruptor de emergencia activado")
    bh = sum(data[s][n - 1].close / first_px[s] - 1 for s in data) / len(data)
    return {"equity": [engine.pf.cash if not equity else equity[0]] + equity, "buy_hold": bh,
            "train_candles": split - start, "test_candles": n - split}


# --------------------------------------------------------------------------- comandos

def cmd_backtest(args: argparse.Namespace) -> int:
    data = load_universe(args)
    if not data:
        raise SystemExit("sin datos")
    path = state_path(args)
    engine = make_engine(args, load_state(path))
    n_agents = sum(len(t.agents) for t in engine.teams.values())
    print(f"Universo: {', '.join(data)} ({args.source}, {args.interval})")
    print(f"{len(engine.teams)} equipos, {n_agents} agentes por símbolo -> "
          f"{(n_agents + len(engine.teams)) * len(data)} señales por vela")
    out = run_backtest(engine, data, args.train, args.verbose)
    ppy = PERIODS_PER_YEAR.get(args.interval, 8_760)
    m = metrics(out["equity"], ppy)
    ts = trade_stats(engine.pf.closed)
    print(f"\nFase 1, aprendizaje (sin operar): {out['train_candles']} velas")
    print(f"Fase 2, validación fuera de muestra (operando en papel): {out['test_candles']} velas")
    print(f"  Resultado: {m['return']:+.2%}  (anualizado {m['annual']:+.2%})   "
          f"comprar y mantener la cesta: {out['buy_hold']:+.2%}")
    print(f"  Drawdown máximo: {m['max_drawdown']:.2%}   Sharpe: {m['sharpe']:.2f}")
    pf = "∞" if ts["profit_factor"] == math.inf else f"{ts['profit_factor']:.2f}"
    print(f"  Operaciones: {ts['n']}   acierto {ts['win_rate']:.0%}   factor de beneficio {pf}   "
          f"media {ts['avg_r']:+.2f}R")
    print(f"  Señales procesadas: {engine.total_signals:,} a {engine.signals_per_second:,.0f} señales/segundo")
    vetoes = sorted(engine.council.veto_counts.items(), key=lambda kv: -kv[1])
    print("  Vetos del equipo escéptico: " + ", ".join(f"{k} {v:,}" for k, v in vetoes[:5]))
    if engine.llm is not None:
        print(f"  Vetos de la IA: {engine.llm_vetoes}")
    if engine.risk.halted:
        print("  [INTERRUPTOR DE EMERGENCIA ACTIVADO]")
    goal = m["annual"] if args.target_basis == "anual" else m["return"]
    verdict = "ALCANZADO" if goal >= args.target else "NO alcanzado"
    print(f"\nObjetivo {args.target:.0%} ({args.target_basis}): {verdict} ({goal:+.2%})."
          + ("" if args.source != "synthetic" else " Ojo: datos sintéticos, no reales."))
    print_learning(engine.state())
    if path:
        save_state(path, engine)
        print(f"\nMemoria guardada en {path} (la próxima ejecución parte de aquí)")
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    args.limit = max(args.limit, WINDOW + args.steps + 10)
    data = load_universe(args)
    engine = make_engine(args, {})
    n = min(len(v) for v in data.values())
    for i in range(n - args.steps, n):
        engine.step({s: cs[i - WINDOW + 1: i + 1] for s, cs in data.items()}, trading=True)
    sps = engine.signals_per_second
    print(f"{engine.total_signals:,} señales en {engine.total_seconds:.2f}s -> {sps:,.0f} señales/segundo "
          f"({'OK' if sps >= 500 else 'por debajo de'} el mínimo de 500)")
    return 0 if sps >= 500 else 1


def cmd_live(args: argparse.Namespace) -> int:
    path = state_path(args) or os.path.join(STATE_DIR, f"binance-{args.interval}.json")
    book = path.replace(".json", ".paper.json")
    engine = make_engine(args, load_state(path))
    if os.path.exists(book):  # recuperar la cartera de papel
        with open(book) as fh:
            d = json.load(fh)
        engine.pf.cash = d["cash"]
        engine.pf.positions = {s: Position(**p) for s, p in d.get("positions", {}).items()}
        for k, v in d.get("risk", {}).items():
            setattr(engine.risk, k, v)
    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    last_seen = 0
    print(f"Modo vivo (papel): {', '.join(syms)} {args.interval}. Ctrl+C para salir.")
    while True:
        try:
            data = align({s: fetch_binance(s, args.interval, WINDOW + 1)[:-1] for s in syms})  # última vela abierta
            t = min(cs[-1].time for cs in data.values())
            if t > last_seen:
                last_seen = t
                rep = engine.step(data, trading=True)
                ts = time.strftime("%Y-%m-%d %H:%M", time.gmtime(t / 1000))
                prices = {s: cs[-1].close for s, cs in data.items()}
                print(f"\n{ts}  capital {engine.pf.equity(prices):,.2f}  ({rep.signals} señales en "
                      f"{rep.seconds * 1000:.0f} ms)")
                for s, d in rep.decisions.items():
                    st = "APROBADA" if d.approved else "; ".join(d.vetoes[:2])
                    print(f"  {s:<9} [{d.regime}] consejo {d.score:+.2f} acuerdo {d.agreement:.0%}  {st}")
                for p in rep.opened:
                    print(f"  >>> ABRE {p.symbol} a {p.entry:.4f}, stop {p.stop:.4f}, objetivo {p.target:.4f}")
                for c in rep.closed:
                    print(f"  <<< CIERRA {c.symbol} a {c.exit:.4f}: {c.pnl:+.2f} ({c.r:+.2f}R, {c.why})")
                save_state(path, engine)
                with open(book, "w") as fh:
                    json.dump({"cash": engine.pf.cash,
                               "positions": {s: asdict(p) for s, p in engine.pf.positions.items()},
                               "risk": {k: v for k, v in asdict(engine.risk).items()},
                               "closed": [asdict(c) for c in engine.pf.closed[-500:]]}, fh, indent=2)
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


def cmd_status(args: argparse.Namespace) -> int:
    path = state_path(args)
    state = load_state(path)
    if not state:
        print(f"Sin memoria todavía ({path}). Ejecuta un backtest o el modo vivo.")
        return 1
    print_learning(state, top=5)
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Bot multiagente de señales cripto que aprende (solo papel).")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp: argparse.ArgumentParser, source_default: str = "synthetic") -> None:
        sp.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
        sp.add_argument("--interval", default="1h", choices=sorted(PERIODS_PER_YEAR))
        sp.add_argument("--source", default=source_default, choices=["synthetic", "binance", "csv"])
        sp.add_argument("--csv", help="plantilla de ruta, p. ej. datos/{symbol}.csv")
        sp.add_argument("--limit", type=int, default=3000)
        sp.add_argument("--seed", type=int, default=7)
        sp.add_argument("--structure", type=float, default=1.0, help="inercia en datos sintéticos (0 = azar puro)")
        sp.add_argument("--state", help="archivo de memoria (por defecto ~/.cache/freelm-trading/...)")
        sp.add_argument("--no-memory", action="store_true", help="no leer ni guardar lo aprendido")
        sp.add_argument("--cash", type=float, default=10_000.0)
        sp.add_argument("--risk", type=float, default=0.01, help="riesgo por operación (0.01 = 1%%)")
        sp.add_argument("--max-positions", type=int, default=4)
        sp.add_argument("--min-agreement", type=float, default=0.6)
        sp.add_argument("--min-samples", type=int, default=40)
        sp.add_argument("--min-edge", type=float, default=0.15, help="ventaja mínima conservadora en R")
        sp.add_argument("--allow-volatile", action="store_true")
        sp.add_argument("--llm", action="store_true", help="la IA (freelm) revisa cada operación antes de abrirla")
        sp.add_argument("--llm-model", default="chat:fast")

    b = sub.add_parser("backtest", help="aprender y validar fuera de muestra")
    common(b)
    b.add_argument("--train", type=float, default=0.6, help="fracción de velas para aprender sin operar")
    b.add_argument("--target", type=float, default=0.18)
    b.add_argument("--target-basis", choices=["anual", "periodo"], default="anual")
    b.add_argument("-v", "--verbose", action="store_true")
    b.set_defaults(func=cmd_backtest)

    be = sub.add_parser("bench", help="medir señales por segundo")
    common(be)
    be.add_argument("--steps", type=int, default=30)
    be.set_defaults(func=cmd_bench)

    lv = sub.add_parser("live", help="tiempo real en papel (Binance público)")
    common(lv, "binance")
    lv.add_argument("--poll", type=float, default=60.0)
    lv.add_argument("--once", action="store_true", help="procesar una vela y salir (para cron)")
    lv.set_defaults(func=cmd_live)

    st = sub.add_parser("status", help="ver lo aprendido")
    common(st)
    st.set_defaults(func=cmd_status)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
