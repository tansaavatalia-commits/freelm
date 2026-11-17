"""Bot multiagente de señales cripto que aprende solo — SOLO PAPER TRADING.

    python examples/trading_agents/bot.py backtest                 # sin red: datos sintéticos
    python examples/trading_agents/bot.py backtest --source binance --symbol ETHUSDT
    python examples/trading_agents/bot.py backtest --llm --llm-every 24   # con analista IA (freelm)
    python examples/trading_agents/bot.py live --symbol BTCUSDT --interval 1h --llm
    python examples/trading_agents/bot.py status --symbol BTCUSDT

Lo aprendido (pesos de cada agente por régimen) se guarda en
``~/.cache/freelm-trading/<SYMBOL>.json`` y se reutiliza en la próxima
ejecución: cuanto más corre, más experiencia acumula.

Esto es material educativo. No es asesoramiento financiero; el rendimiento
pasado (y más aún el de un backtest) no garantiza nada. El bot no envía
órdenes reales a ningún exchange.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import indicators as ta
from agents import Agent, LLMAnalystAgent, Signal, default_agents
from learning import REGIMES, Coordinator, detect_regime
from market import Candle, fetch_binance, load_csv, synthetic
from risk import PaperBroker, RiskManager

WINDOW = 250
STATE_DIR = os.environ.get("FREELM_TRADING_DIR", os.path.join(os.path.expanduser("~"), ".cache", "freelm-trading"))
PERIODS_PER_YEAR = {"1m": 525_600, "5m": 105_120, "15m": 35_040, "1h": 8_760, "4h": 2_190, "1d": 365}


@dataclass
class StepResult:
    time: int
    price: float
    regime: str
    decision: float
    action: Optional[str]
    signals: List[Signal] = field(default_factory=list)


class TradingBot:
    def __init__(self, agents: Sequence[Agent], coordinator: Coordinator, broker: PaperBroker,
                 risk: RiskManager, llm_every: int = 1) -> None:
        self.agents = list(agents)
        self.coord, self.broker, self.risk = coordinator, broker, risk
        self.llm_every = max(1, llm_every)
        self._pending: Optional[tuple] = None  # (signals, regime, close) esperando su resultado
        self._last_llm: Dict[str, Signal] = {}
        self._steps = 0
        self.warmup = max(a.warmup for a in self.agents) + 1

    def step(self, window: Sequence[Candle]) -> StepResult:
        c = window[-1]
        closes = [x.close for x in window]
        rets = [math.log(closes[i] / closes[i - 1]) for i in range(max(1, len(closes) - 30), len(closes))]
        vol = math.sqrt(sum(r * r for r in rets) / len(rets)) if rets else 0.01

        # 1) aprender de lo que pasó desde la decisión anterior
        if self._pending:
            sigs, regime, prev_close = self._pending
            self.coord.learn(sigs, regime, math.log(c.close / prev_close), vol)

        # 2) cada equipo opina; el analista IA escucha a los demás
        tech = [a for a in self.agents if not isinstance(a, LLMAnalystAgent)]
        signals = [a.analyze(window) for a in tech]
        for a in self.agents:
            if isinstance(a, LLMAnalystAgent):
                if self._steps % self.llm_every == 0 or a.name not in self._last_llm:
                    a.peer_signals = signals[:]
                    self._last_llm[a.name] = a.analyze(window)
                signals.append(self._last_llm[a.name])

        # 3) el coordinador decide con los pesos aprendidos para este régimen
        regime = detect_regime(window)
        decision = self.coord.combine(signals, regime)

        # 4) el gestor de riesgo ejecuta (en papel)
        atr = ta.atr([x.high for x in window], [x.low for x in window], closes)[-1]
        action = self.risk.act(self.broker, c.time, c.close, c.low, atr, decision)

        self._pending = (signals, regime, c.close)
        self._steps += 1
        return StepResult(c.time, c.close, regime, decision, action, signals)


# --------------------------------------------------------------------------- utilidades

def build_llm(enabled: bool) -> Any:
    if not enabled:
        return None
    try:
        from freelm import FreeLLM
        return FreeLLM.from_env(timeout=30)
    except Exception as e:  # noqa: BLE001 - sin claves el bot sigue, solo sin IA
        print(f"[aviso] analista IA desactivado: {type(e).__name__}: {e}", file=sys.stderr)
        return None


def make_bot(symbol: str, llm: Any, llm_model: str, llm_every: int, state: Optional[str],
             cash: float = 10_000.0, eta: float = 0.5) -> TradingBot:
    agents: List[Agent] = default_agents()
    if llm is not None:
        agents.append(LLMAnalystAgent(llm, model=llm_model, symbol=symbol))
    coord = Coordinator.load(state, [a.name for a in agents], eta=eta)
    broker = PaperBroker(cash=cash)
    return TradingBot(agents, coord, broker, RiskManager(peak_equity=cash), llm_every=llm_every)


def load_candles(args: argparse.Namespace) -> List[Candle]:
    if args.source == "binance":
        return fetch_binance(args.symbol, args.interval, args.limit)
    if args.source == "csv":
        if not args.csv:
            raise SystemExit("--source csv necesita --csv RUTA")
        return load_csv(args.csv)
    return synthetic(args.limit, seed=args.seed)


def metrics(equity: Sequence[float], periods_per_year: int) -> Dict[str, float]:
    rets = [equity[i] / equity[i - 1] - 1 for i in range(1, len(equity)) if equity[i - 1] > 0]
    mean = sum(rets) / len(rets) if rets else 0.0
    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / len(rets)) if rets else 0.0
    peak, mdd = equity[0], 0.0
    for e in equity:
        peak = max(peak, e)
        mdd = max(mdd, 1 - e / peak)
    return {"return": equity[-1] / equity[0] - 1, "max_drawdown": mdd,
            "sharpe": mean / sd * math.sqrt(periods_per_year) if sd else 0.0}


def backtest(bot: TradingBot, candles: Sequence[Candle], verbose: bool = False) -> Dict[str, Any]:
    if len(candles) <= bot.warmup + 1:
        raise SystemExit(f"hacen falta más de {bot.warmup + 1} velas (hay {len(candles)})")
    start_eq = bot.broker.equity(candles[bot.warmup].close)
    equity, start_px = [start_eq], candles[bot.warmup].close
    for i in range(bot.warmup, len(candles)):
        res = bot.step(candles[max(0, i - WINDOW + 1): i + 1])
        equity.append(bot.broker.equity(res.price))
        if verbose and res.action:
            print(f"  {res.action:<5} {res.price:>12.2f}  decisión {res.decision:+.2f}  [{res.regime}]")
    return {"equity": equity, "buy_hold": candles[-1].close / start_px - 1, "candles": len(candles) - bot.warmup}


def print_learning(coord: Coordinator) -> None:
    print("\nLo que ha aprendido el coordinador (peso por régimen):")
    for reg in REGIMES:
        top = ", ".join(f"{a} {w:.0%}" for a, w in coord.ranking(reg))
        print(f"  {reg:<10} {top}")
    print("\nAcierto direccional por agente:")
    for a, s in sorted(coord.stats.items(), key=lambda kv: -kv[1].hit_rate):
        print(f"  {a:<12} {s.hit_rate:6.1%}  ({s.n} señales, recompensa acumulada {s.reward:+.1f})")
    print(f"  actualizaciones totales: {coord.updates}")


def state_path(args: argparse.Namespace) -> Optional[str]:
    if getattr(args, "no_memory", False):
        return None
    return args.state or os.path.join(STATE_DIR, f"{args.symbol.upper()}.json")


# --------------------------------------------------------------------------- comandos

def cmd_backtest(args: argparse.Namespace) -> int:
    candles = load_candles(args)
    path = state_path(args)
    bot = make_bot(args.symbol, build_llm(args.llm), args.llm_model, args.llm_every, path, args.cash)
    print(f"Backtest {args.symbol} ({args.source}, {len(candles)} velas, agentes: "
          f"{', '.join(a.name for a in bot.agents)})")
    out = backtest(bot, candles, verbose=args.verbose)
    m = metrics(out["equity"], PERIODS_PER_YEAR.get(args.interval, 8_760))
    sells = [t for t in bot.broker.trades if t.side == "SELL"]
    buys = [t for t in bot.broker.trades if t.side == "BUY"]
    wins = sum(1 for b, s in zip(buys, sells) if s.price > b.price)
    print(f"\nResultado (papel): {m['return']:+.2%}   comprar y mantener: {out['buy_hold']:+.2%}")
    print(f"Drawdown máximo: {m['max_drawdown']:.2%}   Sharpe: {m['sharpe']:.2f}   "
          f"operaciones: {len(sells)}   ganadoras: {wins}/{len(sells)}"
          f"{'   [INTERRUPTOR ACTIVADO]' if bot.risk.halted else ''}")
    print_learning(bot.coord)
    if path:
        bot.coord.save(path)
        print(f"\nMemoria guardada en {path}")
    return 0


def cmd_live(args: argparse.Namespace) -> int:
    path = state_path(args) or os.path.join(STATE_DIR, f"{args.symbol.upper()}.json")
    book = path.replace(".json", ".paper.json")
    bot = make_bot(args.symbol, build_llm(args.llm), args.llm_model, 1, path, args.cash)
    if os.path.exists(book):  # recuperar la cartera de papel
        with open(book) as fh:
            d = json.load(fh)
        bot.broker.cash, bot.broker.qty = d["cash"], d["qty"]
        for k, v in d.get("risk", {}).items():
            setattr(bot.risk, k, v)
    last_seen = 0
    print(f"Modo vivo (papel) {args.symbol} {args.interval}. Ctrl+C para salir.")
    while True:
        try:
            candles = fetch_binance(args.symbol, args.interval, WINDOW + 1)[:-1]  # la última vela está abierta
            if candles and candles[-1].time > last_seen:
                last_seen = candles[-1].time
                res = bot.step(candles)
                ts = time.strftime("%Y-%m-%d %H:%M", time.gmtime(res.time / 1000))
                print(f"{ts}  {res.price:>12.2f}  [{res.regime}]  decisión {res.decision:+.2f}  "
                      f"{res.action or '-':<5} capital {bot.broker.equity(res.price):,.2f}")
                for s in res.signals:
                    print(f"    {s.agent:<12} {s.score:+.2f} x{s.confidence:.2f}  {s.reason}")
                bot.coord.save(path)
                with open(book, "w") as fh:
                    json.dump({"cash": bot.broker.cash, "qty": bot.broker.qty,
                               "risk": {k: v for k, v in asdict(bot.risk).items()},
                               "trades": [asdict(t) for t in bot.broker.trades[-200:]]}, fh, indent=2)
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
    if not path or not os.path.exists(path):
        print(f"Sin memoria todavía para {args.symbol} ({path}). Ejecuta un backtest o el modo vivo.")
        return 1
    with open(path) as fh:
        names = list(json.load(fh).get("stats", {}))
    print_learning(Coordinator.load(path, names))
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Bot multiagente de señales cripto que aprende (solo papel).")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--symbol", default="BTCUSDT")
        sp.add_argument("--interval", default="1h", choices=sorted(PERIODS_PER_YEAR))
        sp.add_argument("--state", help="archivo de memoria (por defecto ~/.cache/freelm-trading/SYMBOL.json)")
        sp.add_argument("--no-memory", action="store_true", help="no leer ni guardar lo aprendido")
        sp.add_argument("--cash", type=float, default=10_000.0)
        sp.add_argument("--llm", action="store_true", help="añadir el analista IA (freelm, claves gratis del env)")
        sp.add_argument("--llm-model", default="chat:fast")

    b = sub.add_parser("backtest", help="simular sobre datos históricos y aprender")
    common(b)
    b.add_argument("--source", default="synthetic", choices=["synthetic", "binance", "csv"])
    b.add_argument("--csv")
    b.add_argument("--limit", type=int, default=1000)
    b.add_argument("--seed", type=int, default=7)
    b.add_argument("--llm-every", type=int, default=24, help="consultar la IA cada N velas (ahorra cuota)")
    b.add_argument("-v", "--verbose", action="store_true")
    b.set_defaults(func=cmd_backtest)

    lv = sub.add_parser("live", help="seguir el mercado en tiempo real (paper trading)")
    common(lv)
    lv.add_argument("--poll", type=float, default=60.0, help="segundos entre consultas")
    lv.add_argument("--once", action="store_true", help="procesar una vela y salir (útil en cron)")
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
