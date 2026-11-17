"""Unit tests for examples/trading_agents (offline: synthetic candles, fake LLM)."""
import math
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "examples", "trading_agents"))

import agents  # noqa: E402
import bot  # noqa: E402
import indicators as ta  # noqa: E402
from features import Features  # noqa: E402
from learning import Calibrator, Coordinator, detect_regime  # noqa: E402
from market import Candle, align, synthetic  # noqa: E402
from risk import Portfolio, Position, RiskManager  # noqa: E402


def test_indicators_basic():
    xs = [float(i) for i in range(1, 41)]
    assert ta.sma(xs, 5)[4] == 3.0
    assert ta.ema(xs, 5)[3] is None and ta.ema(xs, 5)[-1] == pytest.approx(38.0)
    assert ta.rsi(xs)[-1] == 100.0
    assert ta.rsi(list(reversed(xs)))[-1] == pytest.approx(0.0)
    lo, mid, up = ta.bollinger([5.0] * 30)
    assert lo[-1] == mid[-1] == up[-1] == 5.0
    lo, mid, up = ta.bollinger(xs, 20, 2.0)  # rolling formula == naive formula
    w = xs[-20:]
    sd = math.sqrt(sum((x - mid[-1]) ** 2 for x in w) / 20)
    assert up[-1] == pytest.approx(mid[-1] + 2 * sd)
    assert ta.obv([1, 2, 1, 1], [10, 10, 5, 7]) == [0, 10, 5, 5]


def test_swarm_is_large_and_bounded():
    swarm = agents.agent_swarm()
    assert len(swarm) >= 80 and len({a.name for a in swarm}) == len(swarm)
    f = Features(synthetic(330, seed=1), "BTC")
    for a in swarm:
        s = a.analyze(f)
        assert -1 <= s.score <= 1 and 0 <= s.confidence <= 1 and s.reason, a.name


def test_coordinator_learns_to_trust_the_right_agent():
    good = lambda r: agents.Signal("good", 1 if r > 0 else -1, 1, "")  # noqa: E731
    bad = lambda r: agents.Signal("bad", -1 if r > 0 else 1, 1, "")  # noqa: E731
    c = Coordinator(["good", "bad"], eta=0.3, alpha=0.01)
    for i in range(50):
        r = 0.01 if i % 3 else -0.01
        c.learn([good(r), bad(r)], "lateral", r, 0.01)
    assert c.weights["lateral"]["good"] > 0.9
    assert c.weights["lateral"]["bad"] >= 0.01 / 2  # fixed share keeps it recoverable
    assert c.stats["good"].hit_rate == 1.0 and c.stats["bad"].hit_rate == 0.0
    assert c.weights["tendencia"]["good"] == pytest.approx(0.5)
    score, agree = c.combine([good(1), bad(1)], "lateral")
    assert score > 0.8 and agree > 0.9
    c2 = Coordinator.from_dict(c.to_dict(), ["good", "bad", "new"])
    assert c2.updates == 50 and "new" in c2.weights["lateral"]


def test_calibrator_requires_proven_edge():
    cal = Calibrator(min_samples=10, min_edge=0.1, horizon=5, fee=0.0)
    ok, why = cal.approved("k")
    assert not ok and "historial" in why
    for _ in range(12):  # every shadow hits its 2R target
        cal.record("X", "k", 100, 99, 102)
        cal.update("X", 103, 99.5, 102)
    assert cal.approved("k")[0]
    for _ in range(12):  # a losing pattern is never approved
        cal.record("X", "bad", 100, 99, 102)
        cal.update("X", 100.5, 98, 98)
    assert not cal.approved("bad")[0]


def test_regime_detection():
    up = Features([Candle(i, 100 + i, 101 + i, 99 + i, 100 + i, 1) for i in range(100)])
    assert detect_regime(up) == "tendencia"
    flat = Features([Candle(i, 100, 101, 99, 100 + (1 if i % 2 else -1), 1) for i in range(100)])
    assert detect_regime(flat) == "lateral"


def test_risk_sizing_breakeven_and_kill_switch():
    pf, r = Portfolio(cash=10_000, fee=0.0), RiskManager()
    qty = r.size(pf, 10_000, 100, 5.0)
    assert qty * 7.5 == pytest.approx(100)  # loses 1% of capital at the stop (1.5 ATR)
    assert r.size(pf, 10_000, 100, 0.5) * 100 == pytest.approx(3_000)  # capped at 30% exposure
    stop, target = r.levels(100, 5.0)
    assert (target - 100) / (100 - stop) == pytest.approx(2.0)  # 2:1 reward/risk
    pf.open(Position("X", qty, 100, stop, target, 100 - stop, 0, 100, ""))
    assert r.manage(pf, "X", 1, 108, 99, 107, 5.0, 0.5) is None
    assert pf.positions["X"].stop >= 100  # after +1R the stop is at break-even or better
    t = r.manage(pf, "X", 2, 101, 90, 91, 5.0, 0.5)
    assert t is not None and t.pnl >= 0  # a winner that came back does not turn into a loss
    pf2, r2 = Portfolio(cash=1000), RiskManager(peak_equity=1000, max_drawdown=0.1)
    assert r2.tick(950) is None
    assert r2.tick(890) == "HALT" and r2.halted
    assert r2.can_open(pf2) == "interruptor activado"


def test_losing_streak_pauses_trading():
    pf, r = Portfolio(cash=10_000), RiskManager(max_losing_streak=2, cooldown=5)
    for i in range(2):
        pf.open(Position(f"S{i}", 1, 100, 98, 104, 2, 0, 100, ""))
        r.manage(pf, f"S{i}", 1, 100, 97, 97, 1.0, 0.0)
    assert r.pause_left == 5 and "pausa" in r.can_open(pf)


def test_backtest_runs_offline_and_saves_memory(tmp_path, capsys):
    state = str(tmp_path / "m.json")
    argv = ["--symbols", "BTCUSDT,ETHUSDT", "--limit", "520", "--state", state, "--dir", str(tmp_path)]
    assert bot.main(["backtest", *argv, "--train", "0.5"]) == 0
    out = capsys.readouterr().out
    assert "Validación fuera de muestra" in out and "señales procesadas" in out and os.path.exists(state)
    assert bot.main(["status", "--state", state]) == 0


def test_bench_exceeds_500_signals_per_second(capsys):
    assert bot.main(["bench", "--symbols", "BTCUSDT,ETHUSDT", "--steps", "5", "--no-memory"]) == 0


def test_llm_agent_parses_json_and_survives_failures():
    f = Features(synthetic(120), "BTC")
    ok = SimpleNamespace(chat=lambda *a, **k: SimpleNamespace(
        text='Claro: {"score": 0.6, "confidence": 0.7, "reason": "tendencia sana"}', provider="groq"))
    s = agents.LLMAnalystAgent(ok).analyze(f)
    assert s.score == 0.6 and "groq" in s.reason

    def boom(*a, **k):
        raise RuntimeError("no keys")

    assert agents.LLMAnalystAgent(SimpleNamespace(chat=boom)).analyze(f).value == 0.0


def test_metrics_and_align():
    m = bot.metrics([100, 110, 99, 120], 365)
    assert m["return"] == pytest.approx(0.2) and m["max_drawdown"] == pytest.approx(0.1)
    a = [Candle(t, 1, 1, 1, 1, 1) for t in (1, 2, 3)]
    b = [Candle(t, 1, 1, 1, 1, 1) for t in (2, 3, 4)]
    assert [c.time for c in align({"a": a, "b": b})["a"]] == [2, 3]


# ---------------------------------------------------------------- grafo, optimizador, exchange

from engine import Config, Engine, Graph, Node, run_backtest  # noqa: E402
from exchange import CcxtExecutor, check_gate, to_market  # noqa: E402
from optimize import MAX_DD, Optimizer, fitness, mutate  # noqa: E402


def test_graph_orders_nodes_by_data_and_detects_cycles():
    seen = []
    g = Graph("t")
    g.add(Node("c", ("b",), ("out",), lambda ctx: seen.append("c")))
    g.add(Node("a", ("in",), ("a",), lambda ctx: seen.append("a")))
    g.add(Node("b", ("a",), ("b",), lambda ctx: seen.append("b")))
    g.run({})
    assert seen == ["a", "b", "c"] and ("a", "b", "a") in g.edges() and "flowchart" in g.mermaid()
    g.add(Node("x", ("out",), ("in",), lambda ctx: None))
    with pytest.raises(ValueError):
        g.order()


def test_engine_graph_contains_teams_council_and_veto():
    eng = Engine(Config(teams=("tendencia", "flujo")))
    names = [n.name for n in eng.symbol_graph.order()]
    assert names.index("equipo:tendencia") < names.index("consejo") < names.index("escéptico")
    assert names.index("filtro_ventaja") < names.index("candidata")
    assert set(eng.teams) == {"tendencia", "flujo"}


def test_config_roundtrip_and_mutation_respects_limits():
    c = Config(teams=("tendencia", "reversión"), min_edge=0.3)
    assert Config.from_dict(c.to_dict()) == c
    import random
    rng = random.Random(1)
    for _ in range(50):
        m = mutate(c, rng, ["tendencia", "reversión", "flujo"], rate=1.0)
        assert m.max_drawdown == MAX_DD and m.target_atr >= 1.5 * m.stop_atr and 1 <= m.max_positions <= 6
        assert not m.teams or len(m.teams) >= 2


def test_fitness_disqualifies_drawdown_over_10pct():
    assert fitness({"return": 5.0, "max_drawdown": 0.11}, 100, 10) < 0
    assert fitness({"return": 0.05, "max_drawdown": 0.05}, 100, 10) == 0.05
    assert fitness({"return": 0.5, "max_drawdown": 0.05}, 3, 10) < 0  # too few trades proves nothing


def test_signal_cache_gives_identical_results():
    data = {s: synthetic(420, seed=i, structure=1.0) for i, s in enumerate(["A", "B"])}
    cache = {}
    runs = []
    for c in (None, cache, cache):
        eng = Engine(Config(min_samples=5, min_edge=0.0), cache=c)
        out = run_backtest(eng, data, eng.warmup, 420, 330)
        runs.append((round(out["equity"][-1], 6), len(eng.pf.closed)))
    assert runs[0] == runs[1] == runs[2] and cache


def test_optimizer_round_offline(tmp_path):
    data = {s: synthetic(760, seed=i, structure=1.0) for i, s in enumerate(["A", "B"])}
    opt = Optimizer(data, seed=1, min_trades=1, log=lambda m: None)
    res = opt.run(population=3, generations=1)
    assert res["evals"] >= 3 and "return" in res["candidate_test"] and isinstance(res["accepted"], bool)
    from optimize import load_champion, save_result
    cp, hp = str(tmp_path / "c.json"), str(tmp_path / "h.jsonl")
    save_result(cp, hp, res, {"source": "synthetic"})
    assert load_champion(cp) is not None and open(hp).read().count("\n") == 1


def test_gate_requires_20_days_profit_and_low_drawdown():
    day = 86_400
    good = [{"t": i * day, "equity": 100 + i * 0.5, "mode": "papel"} for i in range(21)]
    assert check_gate(good, 6)[0]
    assert not check_gate(good[:10], 6)[0]                       # too short
    assert not check_gate(good, 2)[0]                            # too few trades
    crash = good[:10] + [{"t": 11 * day, "equity": 80, "mode": "papel"}] + good[11:]
    assert not check_gate(crash, 6)[0]                           # drawdown > 10%
    losing = [{"t": i * day, "equity": 100 - i * 0.1, "mode": "papel"} for i in range(21)]
    assert not check_gate(losing, 6)[0]
    assert not check_gate([dict(r, mode="testnet") for r in good], 6)[0]  # only paper counts


class FakeExchange:
    def __init__(self):
        self.orders, self.cancelled = [], []
        self.markets = {"BTC/USDT": {"limits": {"amount": {"min": 0.0001}, "cost": {"min": 5}}}}
        self.balance = {"USDT": {"free": 500.0}, "BTC": {"free": 0.0}}

    def load_markets(self):
        return self.markets

    def amount_to_precision(self, m, q):
        return f"{math.floor(q * 1e5) / 1e5:.5f}"

    def price_to_precision(self, m, p):
        return f"{p:.2f}"

    def fetch_balance(self):
        return self.balance

    def create_order(self, m, typ, side, qty, price=None, params=None):
        self.orders.append((m, typ, side, float(qty), price, params))
        if typ == "market" and side == "buy":
            self.balance["BTC"]["free"] += float(qty)
        if typ == "market" and side == "sell":
            self.balance["BTC"]["free"] -= float(qty)
        return {"id": str(len(self.orders)), "filled": float(qty), "average": 50_000.0, "fees": []}

    def cancel_order(self, oid, m):
        self.cancelled.append(oid)


def test_ccxt_executor_caps_capital_and_places_exchange_stops():
    fx = FakeExchange()
    ex = CcxtExecutor(testnet=False, max_capital=100.0, client=fx, log=lambda m: None)
    assert ex.real_money and ex.starting_cash() == 100.0   # hard cap even with 500 available
    assert to_market("BTCUSDT") == "BTC/USDT"
    qty, px = ex.buy("BTCUSDT", 0.0015, 50_000)
    assert qty == pytest.approx(0.0015) and px == 50_000.0
    ex.protect("BTCUSDT", qty, 49_000)
    assert fx.orders[-1][5] == {"stopLossPrice": 49_000.0}
    ex.protect("BTCUSDT", qty, 49_500)                     # trailing: old stop is cancelled first
    assert fx.cancelled == ["2"]
    ex.sell("BTCUSDT", qty, 51_000)
    assert fx.orders[-1][1:3] == ("market", "sell") and fx.balance["BTC"]["free"] == pytest.approx(0)
    assert ex.buy("BTCUSDT", 0.00005, 50_000)[0] == 0.0   # below exchange minimum: skipped


def test_live_real_money_is_blocked_without_track_record(tmp_path, capsys):
    rc = bot.main(["live", "--exchange", "real", "--confirm-real-money", "--dir", str(tmp_path), "--once"])
    assert rc == 2 and "BLOQUEADO" in capsys.readouterr().out
    assert bot.main(["gate", "--dir", str(tmp_path)]) == 1


def test_live_once_paper_is_idempotent_per_candle(tmp_path, monkeypatch, capsys):
    """GitHub Actions runs `live --once` every hour: the same candle must not be processed twice,
    and the paper book + equity track must persist between runs."""
    series = {s: synthetic(400, seed=i) for i, s in enumerate(["BTCUSDT", "ETHUSDT"])}
    monkeypatch.setattr(bot, "fetch_binance", lambda s, interval, limit: series[s][-limit:])
    argv = ["live", "--once", "--symbols", "BTCUSDT,ETHUSDT", "--dir", str(tmp_path)]
    assert bot.main(argv) == 0
    assert bot.main(argv) == 0  # same candle again: skipped
    book = bot.load_json(str(tmp_path / "cartera-papel.json"))
    assert book["cash"] == pytest.approx(100.0) or book["positions"]  # 100 simulated, like the real plan
    assert book["last_time"] == series["BTCUSDT"][-2].time
    assert (tmp_path / "historial-papel.jsonl").read_text().count("\n") == 1
    for s in series:  # a new candle arrives
        series[s] = synthetic(401, seed=list(series).index(s))
    assert bot.main(argv) == 0
    assert (tmp_path / "historial-papel.jsonl").read_text().count("\n") == 2
