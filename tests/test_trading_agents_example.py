"""Unit tests for examples/trading_agents (offline: synthetic candles, fake LLM)."""
import math
import os
import sys
from dataclasses import replace
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


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """AGENTS.md: nada de red en los tests unitarios. El índice Fear & Greed se
    descarga en modo vivo/binance; aquí se sustituye por un fallo inmediato."""
    def offline(*a, **k):
        raise ConnectionError("red desactivada en los tests")
    import market as _m
    monkeypatch.setattr(_m, "fetch_fear_greed", offline)
    monkeypatch.setattr(bot, "fetch_fear_greed", offline)
    monkeypatch.setattr(bot, "fetch_funding", offline)
    # las velas sintéticas de los tests son «antiguas»: en estos tests se dan por frescas
    # (la comprobación de frescura tiene su propio test)
    monkeypatch.setattr(bot, "check_fresh", lambda *a, **k: None)


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
        assert m.max_drawdown == MAX_DD and m.target_atr >= m.stop_atr and 1 <= m.max_positions <= 6
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
    assert fx.orders[-1][5]["stopLossPrice"] == 49_000.0 and fx.orders[-1][5]["clientOrderId"].startswith("fls")
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
    monkeypatch.setattr(bot, "fetch_candles", lambda s, interval, limit: series[s][-limit:])
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


# ---------------------------------------------------------------- datos, avisos, informe

import market  # noqa: E402
from notify import Notifier  # noqa: E402


def test_fetch_candles_retries_then_falls_back(monkeypatch):
    calls, waits = [], []

    def flaky(sym, interval, limit):
        calls.append(sym)
        if len(calls) < 2:
            raise ConnectionError("cortado")
        return synthetic(5)

    assert len(market.fetch_candles("BTCUSDT", primary=flaky, sleep=waits.append)) == 5
    assert waits == [2]

    def dead(*a):
        raise ConnectionError("caído")

    monkeypatch.setattr(market, "fetch_ccxt", lambda s, i, n, ex: synthetic(3) if ex == "bybit" else [])
    assert len(market.fetch_candles("BTCUSDT", primary=dead, sleep=lambda s: None)) == 3
    monkeypatch.setattr(market, "fetch_ccxt", lambda *a: (_ for _ in ()).throw(RuntimeError("x")))
    with pytest.raises(RuntimeError, match="sin datos"):
        market.fetch_candles("BTCUSDT", primary=dead, sleep=lambda s: None)


def test_fetch_ccxt_maps_symbols_and_rows():
    client = SimpleNamespace(fetch_ohlcv=lambda m, i, limit: [[1, 1, 2, 0.5, 1.5, None]] if m == "ETH/USDT" else [])
    c = market.fetch_ccxt("ETHUSDT", client=client)[0]
    assert (c.time, c.high, c.close, c.volume) == (1, 2.0, 1.5, 0.0)


def test_notifier_is_silent_without_config_and_never_raises():
    assert not Notifier(token="", chat_id="").send("hola")
    sent = []
    ok = Notifier("T", "42", http=SimpleNamespace(post=lambda url, json, timeout: sent.append((url, json)) or
                                                    SimpleNamespace(status_code=200))).send("hola")
    assert ok and sent[0][0].endswith("/botT/sendMessage") and sent[0][1]["chat_id"] == "42"

    def boom(*a, **k):
        raise OSError("sin red")

    assert not Notifier("T", "42", http=SimpleNamespace(post=boom)).send("hola")


def test_report_summarises_live_track(tmp_path, monkeypatch, capsys):
    series = {s: synthetic(400, seed=i) for i, s in enumerate(["BTCUSDT", "ETHUSDT"])}
    monkeypatch.setattr(bot, "fetch_candles", lambda s, interval, limit: series[s][-limit:])
    bot.main(["live", "--once", "--symbols", "BTCUSDT,ETHUSDT", "--dir", str(tmp_path)])
    capsys.readouterr()
    assert bot.main(["report", "--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "### Bot de trading (papel)" in out and "Puerta del dinero real" in out and "todavía no" in out


# ---------------------------------------------------------------- equipo mercado, riesgo, optimizador, estrés

import engine as engine_mod  # noqa: E402
from engine import stress_test  # noqa: E402
from optimize import fold_returns  # noqa: E402


def test_fast_learning_matches_reference_hedge():
    names = ["a", "b", "c"]
    ref, fast = Coordinator(names, eta=0.4, alpha=0.05), Coordinator(names, eta=0.4, alpha=0.05)
    scores, confs = (0.9, -0.5, 0.2), (1.0, 0.6, 0.3)
    for ret in (0.01, -0.02, 0.005, 0.03):
        ref.learn([agents.Signal(n, s, c, "") for n, s, c in zip(names, scores, confs)], "lateral", ret, 0.01)
        fast.learn_arrays(scores, confs, "lateral", ret, 0.01)
    for n in names:
        assert fast.weights["lateral"][n] == pytest.approx(ref.weights["lateral"][n])
        assert fast.stats[n].n == ref.stats[n].n and fast.stats[n].hits == ref.stats[n].hits
    sig = [agents.Signal(n, s, c, "") for n, s, c in zip(names, scores, confs)]
    assert fast.combine_arrays(scores, confs, "lateral") == pytest.approx(ref.combine(sig, "lateral"))


def test_market_context_ranks_breadth_and_leader():
    up = [Candle(i, 100 + i, 101 + i, 99 + i, 100 + i, 1) for i in range(220)]
    down = [Candle(i, 300 - i, 301 - i, 299 - i, 300 - i, 1) for i in range(220)]
    flat = [Candle(i, 100, 101, 99, 100, 1) for i in range(220)]
    ctx = market.market_context({"BTCUSDT": up, "ETHUSDT": down, "SOLUSDT": flat}, {"1970-01-01": 12})
    assert ctx["BTCUSDT"]["rank"][24] == 1.0 and ctx["ETHUSDT"]["rank"][24] == 0.0
    assert ctx["SOLUSDT"]["breadth"] == pytest.approx(1 / 3) and ctx["BTCUSDT"]["btc_gap"] > 0
    assert ctx["ETHUSDT"]["fng"] == 12
    f = Features(down, "ETHUSDT")
    f.ctx = ctx["ETHUSDT"]
    assert agents.RelStrengthAgent(72).analyze(f).score == -1.0
    assert agents.SentimentAgent().analyze(f).score > 0.9  # miedo extremo -> sesgo comprador
    assert agents.BtcLeaderAgent().analyze(f).score > 0
    assert agents.SentimentAgent().analyze(Features(down)).value == 0  # sin dato: neutral


def test_riskoff_veto_and_heat_cap():
    d = engine_mod.Decision("X", 0.8, 0.9, "tendencia", "k")
    eng = Engine(Config(min_samples=1, min_edge=-9, trend_filter=False))
    ctx = {"decision": d, "market": {"long_ema": None}, "candle": synthetic(1)[0],
           "mctx": {"btc_gap": -0.1, "breadth": 0.1}}
    next(n for n in eng.symbol_graph.nodes if n.name == "escéptico").fn(ctx)
    assert any("fase bajista" in v for v in d.vetoes)
    # límite de riesgo total: con 3 % y 1,5 ATR, no se abre más allá del presupuesto
    eng2 = Engine(Config(max_heat=0.01, max_positions=6, risk_per_trade=0.02, max_exposure=1.0), cash=1000)
    rep = engine_mod.StepReport()
    cands = [(1.0, s, engine_mod.Decision(s, .8, .9, "tendencia", "k"), 1.0, {"features": None, "window": []})
             for s in ("A", "B", "C")]
    eng2.portfolio_graph.run({"prices": {"A": 100, "B": 100, "C": 100}, "time": 0, "candidates": cands, "report": rep})
    heat = sum(p.qty * (p.entry - p.stop) for p in eng2.pf.positions.values())
    assert heat <= 0.01 * 1000 + 1e-6 and "límite de riesgo total alcanzado" in rep.notes


def test_fold_fitness_rewards_consistency():
    assert fold_returns([100, 110, 121, 133.1]) == pytest.approx([0.1, 0.1, 0.1])
    m = {"return": 0.3, "max_drawdown": 0.05}
    steady = fitness(m, 50, 10, [0.1, 0.1, 0.1])
    lucky = fitness(m, 50, 10, [0.5, -0.1, 0.0])
    assert steady > lucky


def test_parallel_evaluation_matches_serial():
    data = {s: synthetic(760, seed=i, structure=1.0) for i, s in enumerate(["A", "B", "C"])}
    opt = Optimizer(data, seed=1, min_trades=1, log=lambda m: None, workers=2)
    cfgs = [Config(), Config(enter=0.25, min_agreement=0.7)]
    par = opt.evaluate_many(cfgs)
    ser = [opt.evaluate(c) for c in cfgs]
    assert [round(r["return"], 9) for r in par] == [round(r["return"], 9) for r in ser]


def test_stress_test_bounds():
    st = stress_test([2, -1, -1, 2, -1, 2, -1, 2], risk=0.01, n_paths=500)
    assert 0 < st["dd_p50"] <= st["dd_p95"] < 0.2 and 0 <= st["p_loss"] <= 1
    assert stress_test([1, 2], 0.01) == {"paths": 0}
    assert stress_test([-1] * 10, 0.01, n_paths=50)["p_loss"] == 1.0


def test_fitness_penalises_bad_streak_risk():
    m = {"return": 0.2, "max_drawdown": 0.05}
    assert fitness(m, 50, 10, None, dd_p95=0.08) == pytest.approx(0.2)
    assert fitness(m, 50, 10, None, dd_p95=0.15) == pytest.approx(0.2 - 2 * 0.05)


def test_champion_needs_real_profit_on_holdout():
    from optimize import should_accept
    base = {"return": 0.0, "max_drawdown": 0.0, "trades": 0}
    # caso real de la investigación: -0,75 % con 1 operación NO debe ser «nueva campeona»
    assert not should_accept({"return": -0.0075, "max_drawdown": 0.012, "trades": 1}, base)
    assert not should_accept({"return": 0.05, "max_drawdown": 0.02, "trades": 1}, base)      # 1 op = suerte
    assert not should_accept({"return": 0.05, "max_drawdown": 0.12, "trades": 9}, base)      # caída > 10 %
    assert not should_accept({"return": 0.02, "max_drawdown": 0.02, "trades": 9},
                             {"return": 0.03, "max_drawdown": 0.02, "trades": 9})
    assert should_accept({"return": 0.02, "max_drawdown": 0.02, "trades": 9}, base)


# ---------------------------------------------------------------- correcciones de la revisión exhaustiva

def test_reoptimize_from_live_args_does_not_crash(tmp_path, monkeypatch, capsys):
    """live --auto-optimize: cmd_optimize leía args.workers, que live no define."""
    series = {s: synthetic(900, seed=i, structure=1.0) for i, s in enumerate(["BTCUSDT", "ETHUSDT"])}
    monkeypatch.setattr(bot, "fetch_candles", lambda s, interval, limit: series[s][-limit:])
    args = bot.parser().parse_args(["live", "--symbols", "BTCUSDT,ETHUSDT", "--dir", str(tmp_path),
                                    "--optimize-limit", "900"])
    eng = Engine(Config(), cash=100.0, sentiment={"2026-01-01": 40})
    monkeypatch.setattr(bot, "cmd_optimize", lambda a: (a.workers, a.population) and 0)
    assert bot._reoptimize(args, eng, str(tmp_path / "m.json")) is eng  # misma config: no rehace el motor
    assert "omitida" not in capsys.readouterr().err
    # si sale una campeona nueva, el motor nuevo conserva el sentimiento y la cartera
    monkeypatch.setattr(bot, "config_for", lambda a: Config(enter=0.3))
    new = bot._reoptimize(args, eng, str(tmp_path / "m.json"))
    assert new is not eng and new.sentiment == eng.sentiment and new.pf is eng.pf


def test_should_accept_replaces_invalid_champion():
    from optimize import should_accept
    good = {"return": 0.05, "max_drawdown": 0.04, "trades": 9}
    assert should_accept(good, {"return": 0.08, "max_drawdown": 0.14, "trades": 12})  # campeona rompió el 10 %
    assert should_accept(good, {"return": 0.06, "max_drawdown": 0.01, "trades": 1})   # campeona = 1 op (suerte)
    assert not should_accept(good, {"return": 0.06, "max_drawdown": 0.02, "trades": 9})


def test_stress_penalty_is_capped_above_hard_tiers():
    m = {"return": -0.02, "max_drawdown": 0.05}
    assert fitness(m, 50, 10, None, dd_p95=0.9) > fitness(m, 9, 10)  # válida > «pocas operaciones»


def test_stress_uses_risk_actually_taken():
    pf = Portfolio(cash=1000, fee=0.0)
    pf.open(Position("X", 1, 100, 95, 110, 5, 0, 100, "", risk_frac=0.005))
    t = pf.close("X", 110, 1, "objetivo")
    assert t.r == pytest.approx(2.0) and t.equity_return == pytest.approx(0.01)


def test_market_context_without_btc_has_no_fake_leader():
    up = [Candle(i, 100 + i, 101 + i, 99 + i, 100 + i, 1) for i in range(220)]
    ctx = market.market_context({"ETHUSDT": up, "SOLUSDT": up})
    assert ctx["ETHUSDT"]["btc_gap"] is None
    f = Features(up, "ETHUSDT")
    f.ctx = ctx["ETHUSDT"]
    assert agents.BtcLeaderAgent().analyze(f).value == 0
    d = engine_mod.Decision("ETHUSDT", 0.8, 0.9, "tendencia", "k")
    eng = Engine(Config(trend_filter=False))
    sk = next(n for n in eng.symbol_graph.nodes if n.name == "escéptico")
    sk.fn({"decision": d, "market": {"long_ema": None}, "candle": up[-1], "mctx": {**ctx["ETHUSDT"], "breadth": 0}})
    assert not any("bajista" in v for v in d.vetoes)


def test_allocation_stops_at_heat_budget_before_asking_llm():
    calls = []
    llm = SimpleNamespace(peer_signals=[], analyze=lambda f: calls.append(1) or agents.Signal("llm", 1, 1, ""))
    eng = Engine(Config(max_heat=0.01, max_positions=6, risk_per_trade=0.02, max_exposure=1.0), cash=1000, llm=llm)
    rep = engine_mod.StepReport()
    cands = [(1.0, s, engine_mod.Decision(s, .8, .9, "tendencia", "k"), 0.7, {"features": None, "window": synthetic(30)})
             for s in ("A", "B", "C")]
    eng.portfolio_graph.run({"prices": {"A": 100, "B": 100, "C": 100}, "time": 0, "candidates": cands, "report": rep})
    assert len(eng.pf.positions) == 1 and len(calls) == 1  # ATR 0,7 deja residuos de coma flotante: debe cortar igual
    assert "límite de riesgo total alcanzado" in rep.notes


def test_paper_slippage_never_overspends_cash():
    eng = Engine(Config(max_positions=6, max_exposure=1.0, risk_per_trade=0.5, max_heat=1.0), cash=100.0)
    rep = engine_mod.StepReport()
    cands = [(1.0, "A", engine_mod.Decision("A", .8, .9, "tendencia", "k"), 1.0, {"features": None, "window": []})]
    eng.portfolio_graph.run({"prices": {"A": 100}, "time": 0, "candidates": cands, "report": rep})
    assert eng.pf.positions and eng.pf.cash >= -1e-9


def test_sentiment_history_covers_the_interval(monkeypatch):
    asked = []
    monkeypatch.setattr(bot, "fetch_fear_greed", lambda limit: asked.append(limit) or {})
    args = bot.parser().parse_args(["backtest", "--source", "binance", "--interval", "4h", "--limit", "3000"])
    bot.load_sentiment(args)
    assert asked[0] >= 500  # 3000 velas de 4 h = 500 días (antes pedía 135)


# ---------------------------------------------------------------- equipo «posicionamiento»

def test_funding_at_is_point_in_time_with_zscore():
    series = [(i * 8 * 3_600_000, 0.0001 + (0.0001 if i % 2 else 0)) for i in range(60)] + [(60 * 28_800_000, 0.002)]
    rate, z = market.funding_at(series, 60 * 28_800_000 + 5)
    assert rate == 0.002 and z > 5
    assert market.funding_at(series, 10 * 28_800_000 + 1)[1] is None  # < 20 previos: sin z
    assert market.funding_at(series, -1) == (None, None)               # nada antes: sin mirar al futuro
    assert market.funding_at(None, 5) == (None, None)


def test_positioning_agents():
    cs = [Candle(i, 100, 101, 99, 100, 10, 8) for i in range(30)]  # 80 % compra agresiva
    f = Features(cs, "X")
    assert agents.TakerFlowAgent(24).analyze(f).score > 0.9
    assert agents.TakerFlowAgent(24).analyze(Features(synthetic(40)[:0] or [Candle(i, 1, 1, 1, 1, 1) for i in range(30)])).value == 0
    f.ctx = {"funding": 0.0012, "funding_z": 3.0}
    assert agents.FundingAgent("z").analyze(f).score < -0.9      # largos muy apalancados -> a la contra
    assert agents.FundingAgent("nivel").analyze(f).score < -0.9
    f.ctx = {"funding": -0.0005, "funding_z": -2.5}
    assert agents.FundingAgent("z").analyze(f).score > 0.9
    assert agents.FundingAgent("z").analyze(Features(cs)).value == 0  # sin dato: neutral
    ctx = market.market_context({"BTCUSDT": cs, "ETHUSDT": cs}, funding={"BTCUSDT": [(0, 0.0003)]})
    assert ctx["BTCUSDT"]["funding"] == 0.0003 and ctx["ETHUSDT"]["funding"] is None


def test_fetch_funding_reads_binance_archive(monkeypatch):
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("BTCUSDT-fundingRate-2025-10.csv", "calc_time,funding_interval_hours,last_funding_rate\n"
                   "1759276800000,8,0.00010000\n1759305600000,8,0.00025000\n")

    class Http:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, params=None):
            if "data.binance.vision" in url and "2025-10" in url:
                return SimpleNamespace(status_code=200, content=buf.getvalue())
            if "data.binance.vision" in url:
                return SimpleNamespace(status_code=404, content=b"")
            raise ConnectionError("API bloqueada")

    monkeypatch.setattr(market.httpx, "Client", Http)
    monkeypatch.setitem(sys.modules, "ccxt", None)  # sin ccxt: el respaldo falla en silencio
    rows = market.fetch_funding("BTCUSDT", 1759276800000, 1759400000000)
    assert rows == [(1759276800000, 0.0001), (1759305600000, 0.00025)]


# ---------------------------------------------------------------- IC por agente e informe de rendimiento

def test_agent_ic_detects_predictive_and_contrarian_agents():
    import random

    from learning import AgentStats
    rng = random.Random(0)
    good, bad, noise = AgentStats(), AgentStats(), AgentStats()
    for _ in range(2000):
        y = rng.gauss(0, 1)
        good.add_ic(y + rng.gauss(0, 2), y)
        bad.add_ic(-y + rng.gauss(0, 2), y)
        noise.add_ic(rng.gauss(0, 1), y)
    assert good.ic > 0.3 and good.ic_t > 10
    assert bad.ic_t < -10 and abs(noise.ic_t) < 3
    c = Coordinator(["a"], eta=0.3)
    for i in range(50):
        r = 0.01 if i % 2 else -0.01
        c.learn_arrays((1.0 if r > 0 else -1.0,), (1.0,), "lateral", r, 0.01)
    assert c.stats["a"].ic == pytest.approx(1.0) and c.to_dict()["stats"]["a"]["ic_n"] == 50
    rows = bot.agent_ic_table({"teams": {"t": c.to_dict()}})
    assert rows[0][0] == "a" and rows[0][4] > 10


def test_performance_report_metrics():
    from report import format_performance, performance
    hour = 3_600_000
    eq = [100, 101, 102, 99, 98, 100, 103, 104]
    times = [1_700_000_000_000 + i * 12 * hour for i in range(len(eq))]
    trades = [SimpleNamespace(pnl=x) for x in (2, -1, -1, 3, 1)]
    p = performance(eq, times, 8_760, trades)
    assert p["total"] == pytest.approx(0.04) and p["max_drawdown"] == pytest.approx(1 - 98 / 102)
    assert p["sortino"] > 0 and p["win_streak"] == 2 and p["loss_streak"] == 2
    assert p["expectancy"] == pytest.approx(0.8) and p["payoff"] == pytest.approx(2.0)
    assert any("Sortino" in line for line in format_performance(p))
    assert performance([100], [0], 8_760) == {}


# ---------------------------------------------------------------- filtro de probabilidad verificada (>= 77 %)

def test_wilson_lower_bound():
    from learning import wilson_lower
    assert wilson_lower(0, 0, 3) == 0.0
    assert wilson_lower(8, 10, 3) < 0.5                    # 80 % en 10 casos no demuestra nada
    assert 0.77 < wilson_lower(900, 1000, 3) < 0.9         # 90 % en 1000 casos sí
    assert wilson_lower(90, 100, 1.96) > wilson_lower(90, 100, 3.0)  # más exigencia, cota más baja


def test_calibrator_chooses_only_verified_high_probability_profile():
    cal = Calibrator(min_samples=20, horizon=10, fee=0.0, sample_gap=10)
    # objetivo cercano (0,5 ATR) casi siempre se toca; el lejano (3 ATR) casi nunca
    for i in range(400):
        cal.record("X", "k", 100.0, 98.0, atr=1.0, profiles=(0.5, 3.0))
        low = 97.0 if i % 25 == 0 else 99.6        # 4 % de las veces salta el stop
        cal.update("X", 100.6, low, 100.2)
    ok, note, target, p = cal.choose("k", (0.5, 3.0), 0.77, 3.0)
    assert ok and target == 0.5 and p >= 0.77, note
    assert not cal.choose("k", (3.0,), 0.77, 3.0)[0]       # el perfil lejano no llega al 77 %
    assert not cal.choose("otro", (0.5,), 0.77, 3.0)[0]    # sin historial: nunca opera


def test_overlapping_shadows_count_as_fewer_effective_samples():
    cal = Calibrator(min_samples=1, horizon=48, fee=0.0, sample_gap=6)
    for _ in range(100):
        cal.record("X", "k", 100.0, 90.0, 120.0)
    for _ in range(48):
        cal.update("X", 101, 99, 100)                       # todas duran 48 velas (horizonte)
    assert cal.results["k"][0] == 100 and cal.effective_n("k") == pytest.approx(100 * 6 / 48)


def test_strict_position_exits_exactly_like_the_shadow():
    pf, r = Portfolio(cash=1000, fee=0.0), RiskManager(exit_score=-0.2)
    pf.open(Position("X", 1, 100, 98, 101, 2, 0, 100, "", p_win=0.8, expires=3, strict=True))
    assert r.check_exit(pf, "X", 100.5, 99.5, 100.2, 1.0, -0.9) is None   # el consejo bajista NO cierra
    assert pf.positions["X"].stop == 98                                    # ni sube el stop
    assert r.check_exit(pf, "X", 100.5, 99.5, 100.2, 1.0, 0.0) is None
    assert r.check_exit(pf, "X", 100.5, 99.5, 100.3, 1.0, 0.0) == (100.3, "fin del horizonte")
    t = pf.close("X", 100.3, 1, "fin")
    assert t.p_win == 0.8


def test_optimizer_never_lowers_the_77_percent_rule():
    import random

    from optimize import _fix
    rng = random.Random(3)
    c = _fix(Config(min_win_prob=0.5))
    assert c.min_win_prob >= 0.77
    for _ in range(30):
        assert mutate(c, rng, ["tendencia", "flujo"], rate=1.0).min_win_prob >= 0.77


def test_verification_report(capsys):
    from risk import ClosedTrade
    trades = [ClosedTrade("X", 0, 1, 100, 101, 1, 1.0, 0.5, "obj", 0.01, 0.8) for _ in range(9)]
    trades.append(ClosedTrade("X", 0, 1, 100, 98, 1, -2.0, -1.0, "stop", 0.01, 0.8))
    bot.print_verification(trades)
    assert "acertaron 90%" in capsys.readouterr().out
    bot.print_verification([])
    assert "ninguna operación" in capsys.readouterr().out


def test_sleep_to_next_close_aligns_to_candle(monkeypatch):
    slept = []
    monkeypatch.setattr(bot.time, "time", lambda: 1_000_000_010.0)
    monkeypatch.setattr(bot.time, "sleep", slept.append)
    bot.sleep_to_next_close("5m", 0)
    assert (1_000_000_010.0 + slept[0]) % 300 == pytest.approx(1.5)
    bot.sleep_to_next_close("5m", 7)
    assert slept[-1] == 7


# ---------------------------------------------------------------- órdenes límite (maker)

def test_limit_shadow_fills_only_when_price_trades_through():
    cal = Calibrator(min_samples=1, horizon=10, sample_gap=1, entry_cost=0.0, target_cost=0.0, stop_cost=0.0,
                     limit_offset=0.5, limit_wait=2)
    cal.record("X", "k", 100.0, 98.5, atr=2.0, profiles=(1.0,))       # límite a 99, stop 97.5, objetivo 101
    cal.update("X", 101.0, 99.0, 100.0)    # toca 99 pero no lo atraviesa: no ejecuta
    assert cal.open["X"][0].wait == 1 and not cal.results
    cal.update("X", 99.5, 98.9, 99.2)      # atraviesa: ejecutada a 99 (sin objetivo en la vela de entrada)
    assert cal.open["X"][0].wait == 0 and cal.open["X"][0].entry == 99.0
    cal.update("X", 101.5, 99.0, 101.0)    # objetivo 101
    k = "k#t1"
    assert cal.results[k][0] == 1 and cal.results[k][3] == 1
    cal.record("X", "k", 100.0, 98.5, atr=2.0, profiles=(1.0,))
    cal.update("X", 102, 100, 101)
    cal.update("X", 103, 101, 102)          # nunca bajó a 99: se cancela y cuenta como perdida
    assert cal.missed["k"] == 1 and not cal.open["X"]


def test_maker_costs_are_cheaper_than_taker_in_the_shadow():
    def r_for(entry_cost, target_cost):
        cal = Calibrator(min_samples=1, horizon=10, sample_gap=1, entry_cost=entry_cost, target_cost=target_cost,
                         stop_cost=0.0015)
        cal.record("X", "k", 100.0, 98.5, atr=1.0, profiles=(1.0,))
        cal.update("X", 101.5, 99.5, 101.0)
        return cal.results["k#t1"][1]
    assert r_for(0.00075, 0.00075) > r_for(0.0015, 0.0015)


def test_engine_limit_order_lifecycle():
    eng = Engine(Config(entry_mode="limit", limit_offset_atr=0.5, limit_wait=2, max_positions=4,
                        max_exposure=1.0, risk_per_trade=0.02, max_heat=1.0), cash=1000)
    rep = engine_mod.StepReport()
    d = engine_mod.Decision("A", .8, .9, "tendencia", "L|k", exit_target=1.0, p_win=0.8)
    eng.portfolio_graph.run({"prices": {"A": 100}, "time": 0, "report": rep,
                             "candidates": [(0.8, "A", d, 2.0, {"features": None, "window": []})]})
    assert not eng.pf.positions and eng.pf.pending["A"]["limit"] == pytest.approx(99.0)
    assert eng.risk.can_open(eng.pf) is None and eng.pf.cash == 1000  # pendiente: aún no gasta caja
    node = next(n for n in eng.symbol_graph.nodes if n.name == "órdenes_límite")
    node.fn({"symbol": "A", "candle": Candle(1, 100, 100.5, 98.9, 99.5, 1), "report": rep})
    p = eng.pf.positions["A"]
    assert p.entry == 99.0 and p.entry_fee == eng.cfg.maker_fee and p.strict and not eng.pf.pending
    assert p.target == pytest.approx(101.0) and p.stop == pytest.approx(96.0)


def test_real_exchange_limit_mode_uses_taker_target_and_own_stats():
    args = bot.parser().parse_args(["live", "--exchange", "testnet", "--entry-mode", "limit", "--default-config"])
    cfg = bot.config_for(args)
    assert cfg.entry_mode == "limit" and not cfg.target_maker
    eng = Engine(cfg)
    assert eng.cal.target_cost == pytest.approx(cfg.taker_fee + engine_mod.SLIPPAGE)


def test_ccxt_limit_order_cycle():
    fx = FakeExchange()
    fx.fetch_order = lambda oid, m: {"id": oid, "filled": 0.002, "average": 49_900.0, "status": "closed", "fees": []}
    ex = CcxtExecutor(testnet=True, client=fx, log=lambda m: None)
    oid = ex.place_limit_buy("BTCUSDT", 0.002, 49_900.0)
    assert fx.orders[-1][1:5] == ("limit", "buy", 0.002, 49_900.0) and oid
    assert ex.limit_status("BTCUSDT", oid) == (0.002, 49_900.0, "closed")
    assert ex.place_limit_buy("BTCUSDT", 0.00001, 49_900.0) is False   # bajo el mínimo
    ex.cancel_limit("BTCUSDT", oid)
    assert fx.cancelled[-1] == oid


def test_engine_real_limit_order_waits_for_exchange_status():
    calls = []

    class Ex:
        simulated = False
        name, real_money = "fake", True

        def place_limit_buy(self, s, q, p):
            return "42"

        def limit_status(self, s, oid):
            calls.append(oid)
            return (0.0, 0.0, "open") if len(calls) == 1 else (5.0, 99.0, "closed")

        def cancel_limit(self, s, oid):
            calls.append("cancel")

        def protect(self, *a):
            pass

    eng = Engine(Config(entry_mode="limit", target_maker=False, limit_wait=3, max_exposure=1.0,
                        risk_per_trade=0.02, max_heat=1.0), cash=1000, executor=Ex())
    rep = engine_mod.StepReport()
    d = engine_mod.Decision("A", .8, .9, "tendencia", "LT|k", exit_target=1.0, p_win=0.8)
    eng.portfolio_graph.run({"prices": {"A": 100}, "time": 0, "report": rep,
                             "candidates": [(0.8, "A", d, 2.0, {"features": None, "window": []})]})
    node = next(n for n in eng.symbol_graph.nodes if n.name == "órdenes_límite")
    node.fn({"symbol": "A", "candle": Candle(1, 100, 100, 90, 95, 1), "report": rep})  # vela baja: da igual, manda el exchange
    assert "A" in eng.pf.pending
    node.fn({"symbol": "A", "candle": Candle(2, 100, 100, 99, 99, 1), "report": rep})
    assert eng.pf.positions["A"].entry == 99.0 and eng.pf.positions["A"].qty == 5.0 and calls == ["42", "42"]


def test_cost_flags():
    args = bot.parser().parse_args(["backtest", "--entry-mode", "limit", "--bnb", "--default-config"])
    cfg = bot.config_for(args)
    assert cfg.entry_mode == "limit" and cfg.maker_fee == cfg.taker_fee == 0.00075


# ---------------------------------------------------------------- asistente de Windows

def test_windows_assistant_scripts_are_well_formed():
    import re
    from pathlib import Path
    win = Path(__file__).resolve().parent.parent / "examples" / "trading_agents" / "windows"
    for name in ("asistente.ps1", "iniciar-bot.ps1"):
        raw = (win / name).read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf"), f"{name}: sin BOM, PowerShell 5.1 rompería los acentos"
        assert raw.count(b"\r\n") == raw.count(b"\n"), f"{name}: saltos de línea no CRLF"
        code = re.sub(r"<#.*?#>", "", raw.decode("utf-8-sig"), flags=re.S)
        code = re.sub(r"#[^\n]*", "", re.sub(r'"(?:`.|[^"`])*"|\'[^\']*\'', '""', code))
        for a, b in ("{}", "()", "[]"):
            assert code.count(a) == code.count(b), f"{name}: {a}{b} desbalanceados"
    assert (win / "Instalar-Bot.bat").read_bytes().isascii()


def test_windows_scripts_have_no_case_only_variable_clashes():
    """PowerShell no distingue mayúsculas en las variables: $py pisaría a $Py (el Python del bot) y
    $modo al parámetro $Modo. Dos grafías de la misma variable en un script son un error latente."""
    import re
    from pathlib import Path
    win = Path(__file__).resolve().parent.parent / "examples" / "trading_agents" / "windows"
    for name in ("asistente.ps1", "iniciar-bot.ps1"):
        code = (win / name).read_text(encoding="utf-8-sig")
        groups = {}
        for v in set(re.findall(r"\$([A-Za-z_][A-Za-z0-9_]*)", code)):
            groups.setdefault(v.lower(), set()).add(v)
        clashes = {k: g for k, g in groups.items() if len(g) > 1}
        assert not clashes, f"{name}: variables que solo difieren en mayúsculas: {clashes}"


def test_windows_assistant_only_uses_existing_bot_commands():
    """Cada orden que lanza el asistente debe ser válida para bot.py (si cambian las opciones,
    este test avisa antes de que se rompa en el PC del usuario)."""
    p = bot.parser()
    for argv in (
        ["live", "--interval", "5m", "--exchange", "papel", "--auto-optimize", "--optimize-limit", "8000", "--llm"],
        ["live", "--interval", "5m", "--exchange", "real", "--auto-optimize", "--optimize-limit", "8000", "--llm",
         "--confirm-real-money", "--max-capital", "100"],
        ["live", "--interval", "5m", "--exchange", "papel", "--llm"],
        ["optimize", "--source", "binance", "--limit", "5000", "--population", "12", "--generations", "5"],
        ["optimize", "--source", "binance", "--limit", "5000"],
        ["report", "--plain"],
        ["report", "--plain", "--exchange", "testnet"],
        ["gate"],
        ["conexion", "--exchange", "testnet", "--orden-prueba"],
        ["live", "--interval", "5m", "--exchange", "testnet", "--entry-mode", "limit", "--llm"],
        ["live", "--interval", "5m", "--exchange", "testnet", "--auto-optimize", "--optimize-limit", "8000", "--llm",
         "--entry-mode", "limit"],
        ["momentum"],
        ["senales", "--record", "--no-history", "--limit", "260"],
        ["senales", "--record"],
        ["panel"],
        ["sync"],
        ["sync", "--soft"],
        ["notificar"],
        ["dashboard-data", "--dir", "state", "--out", "state/dashboard", "--limit", "3000"],
    ):
        p.parse_args(argv)  # SystemExit si alguna opción no existe


def test_conexion_command_with_test_order(capsys):
    fx = FakeExchange()
    fx.fetch_ticker = lambda m: {"last": 50_000.0}
    fx.fetch_order = lambda oid, m: {"id": oid, "filled": 0.0, "status": "open", "fees": []}
    args = bot.parser().parse_args(["conexion", "--exchange", "testnet", "--symbols", "BTCUSDT,FOOUSDT",
                                    "--orden-prueba"])
    rc = bot.cmd_conexion(args, client=fx)
    out = capsys.readouterr().out
    assert "Saldo libre: 500.00" in out and "BTC/USDT: mínimo 5" in out and "FOO/USDT: no existe" in out
    assert "Orden de prueba colocada y cancelada" in out and fx.cancelled  # nunca queda una orden abierta
    assert fx.orders[-1][1:3] == ("limit", "buy") and fx.orders[-1][4] == pytest.approx(25_000.0)
    assert rc == 1  # FOO no existe -> aviso
    real = bot.parser().parse_args(["conexion", "--exchange", "real", "--orden-prueba"])
    assert bot.cmd_conexion(real, client=fx) == 2  # nunca orden de prueba con dinero real


# ---------------------------------------------------------------- fase 1: seguridad operativa

import safety  # noqa: E402


def _good_window(n=40, step=3_600_000):
    return [Candle(i * step, 100 + i * 0.1, 101 + i * 0.1, 99 + i * 0.1, 100.05 + i * 0.1, 10) for i in range(n)]


def test_integrity_detects_bad_data():
    assert safety.check_window(_good_window()) == []
    w = _good_window()
    del w[-5]
    assert "faltan 1 velas" in safety.check_window(w)[0]
    w = _good_window()
    w[-1] = Candle(w[-1].time, 100, 101, 99, 180, 10)       # +80 % en una vela y cierre fuera del rango
    assert safety.check_window(w)
    w = _good_window()
    w[-2] = Candle(w[-2].time, 100, 101, 99, float("nan"), 10)
    assert "inválido" in safety.check_window(w)[0]
    w = _good_window()
    w[-1] = Candle(w[-2].time, 100, 101, 99, 100, 10)        # vela repetida
    assert "fuera de orden" in safety.check_window(w)[0]


def test_engine_skips_symbols_with_bad_data():
    eng = Engine(Config())
    good = synthetic(330, seed=1)
    bad = list(synthetic(330, seed=2))
    del bad[-3]
    rep = eng.step({"A": good[-320:], "B": bad[-320:]})
    assert "A" in rep.decisions and "B" not in rep.decisions and "B" in rep.data_issues


def test_check_fresh():
    w = _good_window(5, 300_000)
    last_open_s = w[-1].time / 1000
    assert safety.check_fresh(w, 300, now_s=last_open_s + 400) is None
    assert "atrasados" in safety.check_fresh(w, 300, now_s=last_open_s + 3600)


def test_daily_loss_limit_blocks_new_entries_until_next_utc_day():
    pf, r = Portfolio(cash=1000), RiskManager(peak_equity=1000, max_daily_loss=0.03, max_drawdown=0.5)
    day = 86_400_000
    assert r.tick(1000, 10 * day) is None and r.can_open(pf) is None
    assert r.tick(975, 10 * day + 1_800_000) is None            # -2,5 %: aún dentro del límite
    assert r.tick(965, 10 * day + 3_600_000) == "DAILY"         # -3,5 %: bloquea
    assert "pérdida diaria" in r.can_open(pf)
    assert r.tick(960, 10 * day + 7_200_000) is None          # avisa una sola vez
    assert r.tick(960, 11 * day) is None and r.can_open(pf) is None   # nuevo día: se levanta


def test_decision_journal_writes_auditable_jsonl(tmp_path):
    import json as _json
    eng = Engine(Config())
    w = synthetic(330, seed=1)[-320:]
    rep = eng.step({"BTCUSDT": w})
    j = safety.DecisionJournal(str(tmp_path / "diario"))
    j.step(w[-1].time, rep, {"BTCUSDT": w[-1].close}, 100.0)
    files = list((tmp_path / "diario").iterdir())
    rows = [_json.loads(x) for x in files[0].read_text().splitlines()]
    dec = next(r for r in rows if r["tipo"] == "decision")
    assert dec["simbolo"] == "BTCUSDT" and "vetos" in dec and "equipos" in dec and "prob_verificada" in dec
    assert rows[-1]["tipo"] == "cartera"


def test_orders_are_idempotent_after_network_error():
    fx = FakeExchange()
    real_create = fx.create_order
    calls = {"n": 0}
    sent = {}

    def flaky(m, typ, side, qty, price=None, params=None):
        calls["n"] += 1
        o = real_create(m, typ, side, qty, price, params)
        o["clientOrderId"] = (params or {}).get("clientOrderId")
        sent[o["clientOrderId"]] = o
        if calls["n"] == 1:
            raise TimeoutError("la respuesta se perdió")    # la orden SÍ llegó al exchange
        return o

    fx.create_order = flaky
    fx.fetch_order = lambda oid, m, params=None: sent.get((params or {}).get("clientOrderId"))
    ex = CcxtExecutor(testnet=True, client=fx, log=lambda m: None)
    ex.step_time = 1_700_000_000_000
    qty, _ = ex.buy("BTCUSDT", 0.001, 50_000)
    assert calls["n"] == 1 and qty == pytest.approx(0.001)   # no se reenvió: se recuperó la existente
    assert list(sent)[0] == "flbBTC1700000000"


def test_reconcile_closes_positions_missing_on_exchange_and_reprotects():
    fx = FakeExchange()
    fx.balance = {"USDT": {"free": 100.0, "total": 100.0}, "BTC": {"free": 0.0, "total": 0.002},
                  "ETH": {"free": 0.0, "total": 0.0}}
    fx.fetch_open_orders = lambda m: [{"id": "old", "side": "sell", "clientOrderId": "flsBTC1"}] if m == "BTC/USDT" else []
    fx.markets["ETH/USDT"] = {"limits": {"amount": {"min": 0.0001}, "cost": {"min": 5}}}
    ex = CcxtExecutor(testnet=True, client=fx, log=lambda m: None)
    positions = {"BTCUSDT": Position("BTCUSDT", 0.002, 50_000, 49_000, 52_000, 1000, 0, 50_000, ""),
                 "ETHUSDT": Position("ETHUSDT", 0.05, 3_000, 2_900, 3_200, 100, 0, 3_000, "")}
    gone = ex.reconcile(positions)
    assert gone == ["ETHUSDT"]                                    # el stop de ETH se ejecutó con el bot apagado
    assert "old" in fx.cancelled and fx.orders[-1][5]["stopLossPrice"] == 49_000.0   # stop de BTC repuesto


def test_learn_horizon_rewards_agents_over_several_candles():
    data = {"A": synthetic(400, seed=3)}
    one, many = Engine(Config()), Engine(Config(learn_horizon=6))
    for i in range(330, 345):
        w = {"A": data["A"][i - 320:i + 1]}
        one.step(w, trading=False)
        many.step(w, trading=False)
    upd1 = one.council.updates
    upd6 = many.council.updates
    # el horizonte largo espera a que pasen h velas antes de juzgar la primera señal
    assert upd1 == 14 and upd6 == 15 - 6 and len(many._pending["A"]) == 6


def test_ic_t_is_corrected_for_overlapping_horizons():
    c = Coordinator(["a"], eta=0.3)
    for i in range(50):
        r = 0.01 if i % 2 else -0.01
        c.learn_arrays((1.0 if r > 0 else -1.0,), (1.0,), "lateral", r, 0.01)
    raw = bot.agent_ic_table({"teams": {"t": c.to_dict()}})[0][4]
    adj = bot.agent_ic_table({"config": {"learn_horizon": 4}, "teams": {"t": c.to_dict()}})[0][4]
    assert adj == pytest.approx(raw / 2)


import validation  # noqa: E402


def test_deflated_sharpe_discounts_many_trials():
    import random
    rng = random.Random(1)
    edge = [0.002 + rng.gauss(0, 0.01) for _ in range(1500)]
    noise = [rng.gauss(0, 0.01) for _ in range(1500)]
    assert validation.probabilistic_sharpe(edge) > 0.99
    assert validation.probabilistic_sharpe(noise) < 0.95
    # cuantas más pruebas se hicieron, más alto el listón del azar y más bajo el DSR
    few = validation.deflated_sharpe(edge, 2, 0.002)
    many = validation.deflated_sharpe(edge, 500, 0.002)
    assert many < few and validation.expected_max_sharpe(500, 0.002) > validation.expected_max_sharpe(2, 0.002)
    assert validation.expected_max_sharpe(1, 0.002) == 0.0


def test_pbo_detects_overfitting_and_real_edge():
    import random
    t, n = 400, 10
    pbos = []
    for seed in range(12):
        rng = random.Random(seed)
        pbos.append(validation.pbo_cscv([[rng.gauss(0, 0.01) for _ in range(n)] for _ in range(t)], blocks=8))
    # elegir la mejor de estrategias sin ventaja es lanzar una moneda: PBO medio ~50 %
    assert 0.35 < sum(pbos) / len(pbos) < 0.65
    rng = random.Random(2)
    t = 800
    real = [[rng.gauss(0.003 if j == 0 else 0.0, 0.01) for j in range(n)] for _ in range(t)]
    assert validation.pbo_cscv(real, blocks=10) < 0.1
    flat = [[0.0] * 3 for _ in range(100)]
    assert validation.pbo_cscv(flat, blocks=8) is None


def test_judge_requires_every_test_to_pass():
    import random
    rng = random.Random(3)

    def run(mu, k=300):
        eq, rs = [100.0], []
        for i in range(k):
            r = rng.gauss(mu, 0.004)
            eq.append(eq[-1] * (1 + r))
            if i % 5 == 0:
                rs.append(r / 0.004)
        return {"equity": eq, "r": rs, "max_drawdown": 0.03}

    res = {"good": run(0.004), "bad": run(-0.001), "flat": {"equity": [100.0] * 301, "r": [], "max_drawdown": 0.0}}
    rep = validation.judge(res, {"good": ["bad"]}, n_trials=3, blocks=10)
    g, f = rep["strategies"]["good"], rep["strategies"]["flat"]
    assert g["dsr"] > 0.95 and g["ci_r"][0] > 0 and g["segments"][0] > 0
    assert not g["validated"] and any("vecinos" in w for w in g["why"])  # su vecina pierde
    assert not f["validated"] and any("pocas operaciones" in w for w in f["why"])
    rep2 = validation.judge(res, {}, n_trials=3, blocks=10)
    assert rep2["strategies"]["good"]["validated"] and rep2["pbo"] is not None and rep2["pbo"] <= 0.25


def test_validate_command_offline(tmp_path, capsys):
    import json
    rc = bot.main(["validate", "--symbols", "A,B", "--limit", "760", "--dir", str(tmp_path), "--horizons", "1,6",
                   "--rules", "77", "--workers", "1", "--prior-trials", "0"])
    out = capsys.readouterr().out
    assert rc in (0, 3) and "PBO" in out and "Deflated Sharpe" in out
    saved = json.load(open(tmp_path / "validation.json"))
    assert set(saved["strategies"]) == {"77·h1", "77·h6"} and saved["n_trials"] == 2


import strategies as stg  # noqa: E402


def _series(prices):
    return [Candle(86_400_000 * i, p, p * 1.01, p * 0.99, p, 1.0) for i, p in enumerate(prices)]


def test_classic_strategies_follow_trend_and_go_to_cash():
    up = [100 * 1.01 ** i for i in range(300)]
    down = [100 * 0.99 ** i for i in range(300)]
    data = {"UP": _series(up), "DOWN": _series(down)}
    cfg = stg.StratConfig("tsmom", 50, max_positions=2, target_vol=10.0)
    t = 299
    w = stg.targets({k: [c.close for c in v] for k, v in data.items()}, t, cfg)
    assert set(w) == {"UP"} and w["UP"] == pytest.approx(0.5)  # nunca más de 1/max_positions
    res = stg.simulate(data, cfg)
    assert res["equity"][-1] > 1.0 and res["open"] == ["UP"] and res["max_drawdown"] < 0.01
    xs = stg.simulate(data, stg.StratConfig("xsmom", 20, max_positions=2, rebalance=7, target_vol=10.0))
    assert xs["equity"][-1] > 1.0


def test_classic_strategy_has_no_lookahead():
    import random
    rng = random.Random(4)
    base = [100.0]
    for _ in range(399):
        base.append(base[-1] * (1 + rng.gauss(0, 0.03)))
    other = base[:300] + [x * 3 for x in base[300:]]  # el futuro cambia por completo
    cfg = stg.StratConfig("tsmom", 50)
    a = stg.simulate({"A": _series(base[:300])}, cfg)
    b = stg.simulate({"A": _series(other)}, cfg)
    assert b["equity"][:len(a["equity"])] == pytest.approx(a["equity"])


def test_ensemble_and_neighbours():
    runs = {"a": {"equity": [1.0, 1.1, 1.21], "r": [0.1], "max_drawdown": 0.0, "buy_hold": 0.0},
            "b": {"equity": [1.0, 0.9, 0.99], "r": [-0.1], "max_drawdown": 0.1, "buy_hold": 0.0}}
    e = stg.ensemble(runs)
    assert e["equity"] == pytest.approx([1.0, 1.0, 1.1]) and sorted(e["r"]) == [-0.1, 0.1]
    nb = stg.neighbours(stg.default_family())
    assert nb["tsmom·50"] == ["tsmom·20", "tsmom·100"] and nb["xsmom·7"] == ["xsmom·14"]


def test_classic_command_offline(tmp_path, capsys):
    import json
    rc = bot.main(["classic", "--symbols", "A,B,C", "--limit", "700", "--dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc in (0, 3) and "conjunto" in out and "77 %" in out
    saved = json.load(open(tmp_path / "classic.json"))
    assert "conjunto" in saved["strategies"] and saved["interval"] == "1d" and saved["n_trials"] == 106
    assert "Robustez de calendario" in out and len(saved["phases"]) == 7 and "robust_validated" in saved
    assert "sin A" in out and "Sensibilidad al universo" in out and set(saved["leave_one_out"]) == {"A", "B", "C"}


import momentum_paper as mpp  # noqa: E402


def _daily(prices, t0=0):
    return [Candle(t0 + mpp.DAY_MS * i, p, p * 1.01, p * 0.99, p, 1.0) for i, p in enumerate(prices)]


def test_momentum_paper_steps_once_per_day_and_follows_trend():
    fam = mpp.family_for(target_vol=10.0)
    up = [100 * 1.01 ** i for i in range(260)]
    flat = [100.0 + (i % 2) for i in range(260)]
    st = mpp.new_state(100.0, fam)
    data = {"UP": _daily(up[:250]), "FLAT": _daily(flat[:250])}
    st, rep = mpp.step(st, data, fam)
    assert rep["skipped"] is None and st["days"] == 0 and "UP" in st["weights"]
    st, rep = mpp.step(st, data, fam)
    assert rep["skipped"] == "día ya procesado"  # idempotente
    for n in range(251, 256):
        st, rep = mpp.step(st, {"UP": _daily(up[:n]), "FLAT": _daily(flat[:n])}, fam)
    assert st["days"] == 5 and st["equity"] > 100.0 and sum(st["weights"].values()) <= 1.0 + 1e-9


def test_momentum_paper_halts_after_10pct_drawdown():
    fam = mpp.family_for(target_vol=10.0)
    up = [100 * 1.01 ** i for i in range(251)]
    st = mpp.new_state(100.0, fam)
    st, _ = mpp.step(st, {"A": _daily(up)}, fam)
    crash = up + [up[-1] * 0.5]
    st, rep = mpp.step(st, {"A": _daily(crash)}, fam)
    assert st["halted"] and st["weights"] == {} and "detenido" in rep["skipped"]
    sm = mpp.summary(st, [{"equity": 100.0}, {"equity": st["equity"]}])
    assert sm["halted"] and not sm["passed"]


def test_closed_daily_drops_the_forming_candle():
    cs = _daily([1.0, 2.0, 3.0])
    assert len(mpp.closed_daily(cs, 2 * mpp.DAY_MS + 10)) == 2


def test_momentum_command_paper_offline(tmp_path, monkeypatch, capsys):
    import time as _t
    t0 = int(_t.time() * 1000) // mpp.DAY_MS * mpp.DAY_MS - 300 * mpp.DAY_MS
    series = {s: _daily([100 * (1.005 if i else 0.999) ** k for k in range(300)], t0)
              for i, s in enumerate(["BTCUSDT", "ETHUSDT"])}
    monkeypatch.setattr(bot, "fetch_candles", lambda s, interval, limit: series[s][-limit:])
    args = ["momentum", "--symbols", "BTCUSDT,ETHUSDT", "--dir", str(tmp_path)]
    assert bot.main(args) == 0
    assert bot.main(args) == 0  # mismo día: no repite
    out = capsys.readouterr().out
    assert "día ya procesado" in out and "PAPEL" in out
    assert len(open(tmp_path / "momentum_track.jsonl").read().splitlines()) == 1
    assert bot.main(args + ["--report"]) == 0


def _rw(seed, n=400, drift=0.0005):
    import random
    rng = random.Random(seed)
    p = [100.0]
    for _ in range(n - 1):
        p.append(p[-1] * (1 + drift + rng.gauss(0, 0.03)))
    return p


def test_fast_engine_matches_reference_exactly():
    data = {s: _daily(_rw(i)) for i, s in enumerate("ABCD")}
    pan = stg.Panel(data)
    for cfg in (stg.StratConfig("tsmom", 50), stg.StratConfig("xsmom", 14, rebalance=7)):
        ref = stg.simulate(data, cfg)
        fast = stg.simulate_fast(pan, cfg, cfg.warmup)
        assert fast["equity"] == pytest.approx(ref["equity"], abs=1e-12) and fast["r"] == pytest.approx(ref["r"])


def test_panel_handles_coins_listed_later():
    late = _daily(_rw(2, 200), t0=200 * mpp.DAY_MS)
    pan = stg.Panel({"OLD": _daily(_rw(1)), "NEW": late})
    assert pan.n == 400 and not pan.has("NEW", 250, 100) and pan.has("NEW", 399, 150)
    res = stg.simulate_fast(pan, stg.StratConfig("tsmom", 50), 60)
    assert len(res["equity"]) == 400 - 60 + 1


def test_covariance_risk_model_sees_diversification():
    import random
    rng = random.Random(5)
    a, b = [100.0], [100.0]
    for _ in range(99):
        a.append(a[-1] * (1 + rng.gauss(0, 0.02)))
        b.append(b[-1] * (1 + rng.gauss(0, 0.02)))  # independientes
    pan = stg.Panel({"A": _daily(a), "B": _daily(b)})
    w = {"A": 0.5, "B": 0.5}
    c1 = stg.portfolio_vol(pan, w, 99, stg.StratConfig(risk_model="corr1"), 365)
    cv = stg.portfolio_vol(pan, w, 99, stg.StratConfig(risk_model="cov", shrink=0.0), 365)
    assert cv < 0.85 * c1  # sin correlación, la cartera es menos volátil que la suma
    same = stg.Panel({"A": _daily(a), "B": _daily(a)})
    assert stg.portfolio_vol(same, w, 99, stg.StratConfig(risk_model="cov"), 365) == pytest.approx(
        stg.portfolio_vol(same, w, 99, stg.StratConfig(risk_model="corr1"), 365), rel=1e-6)


def test_drawdown_control_and_rolling_peak():
    cfg = stg.StratConfig(dd_budget=0.10, dd_start=0.5)
    assert stg.dd_multiplier(0.03, cfg) == 1.0 and stg.dd_multiplier(0.075, cfg) == pytest.approx(0.5)
    assert stg.dd_multiplier(0.12, cfg) == 0.0 and stg.dd_multiplier(0.5, stg.StratConfig()) == 1.0
    crash = [100 * 1.01 ** i for i in range(250)] + [250 * 0.97 ** i for i in range(60)] + \
            [250 * 0.97 ** 59 * 1.01 ** i for i in range(400)]
    pan = stg.Panel({"A": _daily(crash)})
    base = stg.StratConfig("tsmom", 50, target_vol=10.0, max_positions=1)
    free = stg.simulate_fast(pan, base, 60)
    held = stg.simulate_fast(pan, replace(base, dd_budget=0.10), 60)
    roll = stg.simulate_fast(pan, replace(base, dd_budget=0.10, dd_window=90), 60)
    assert held["max_drawdown"] < free["max_drawdown"]
    # con máximo histórico se queda en liquidez; con máximo móvil vuelve a invertir y recupera
    assert roll["equity"][-1] > held["equity"][-1]


def test_momentum_paper_restarts_when_config_changes(tmp_path):
    p = str(tmp_path / "st.json")
    old = mpp.family_for(target_vol=0.12, risk_model="corr1")
    st = mpp.new_state(100.0, old)
    st["days"] = 3
    mpp.save(p, st)
    again = mpp.load(p, 100.0, old)
    assert again["days"] == 3 and "restarted" not in again
    new = mpp.load(p, 100.0, mpp.family_for())
    assert new["days"] == 0 and "restarted" in new and new["config"] == mpp.signature(mpp.family_for())


import signals as sgn  # noqa: E402


def test_wilson_interval():
    lo, hi = sgn.wilson(50, 100)
    assert lo < 0.5 < hi and hi - lo < 0.21
    assert sgn.wilson(0, 0) == (0.0, 1.0)


def test_signal_card_finds_edge_on_trending_coin_and_not_on_noise():
    up = [100 * 1.004 ** i * (1 + 0.01 * ((-1) ** i)) for i in range(500)]
    noise = _rw(9, 500, drift=-0.001)
    pan = stg.Panel({"UP": _daily(up), "NOISE": _daily(noise)})
    fam = {"t": stg.StratConfig("tsmom", 50, max_positions=1, target_vol=10.0)}
    card = sgn.score_history(pan, fam, 60, horizons=(1, 7))
    r = card["t"][7]
    assert r["n"] > 100 and r["edge"] > 0 and r["hit"] > r["base"]
    assert "conjunto" in card and len(sgn.format_card(card)) == 4


def test_live_signal_records_are_scored_only_with_later_prices(tmp_path):
    p = str(tmp_path / "s.jsonl")
    day = 86_400_000
    assert sgn.record(p, 0, {"v": ["A"]}, {"A": 100.0, "B": 100.0})
    assert not sgn.record(p, 0, {"v": ["A"]}, {"A": 100.0, "B": 100.0})  # una vez por día
    assert sgn.score_records(sgn.load(p))["v"][1]["n"] == 0  # aún no hay precio a 1 día
    sgn.record(p, day, {"v": []}, {"A": 110.0, "B": 90.0})
    card = sgn.score_records(sgn.load(p), horizons=(1,))
    assert card["v"][1]["n"] == 1 and card["v"][1]["hit"] == 1.0 and card["v"][1]["base"] == 0.5
    assert card["v"][1]["edge"] == pytest.approx(0.2)


def test_senales_command_offline(tmp_path, capsys):
    rc = bot.main(["senales", "--source", "synthetic", "--symbols", "A,B", "--limit", "500", "--record",
                   "--dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0 and "Tarjeta de aciertos con la HISTORIA" in out and "registradas" in out
    assert bot.main(["senales", "--live-only", "--dir", str(tmp_path)]) == 0


import cloud  # noqa: E402
import panel as panel_mod  # noqa: E402


def _paper_dir(tmp_path):
    import json
    d = tmp_path / "st"
    d.mkdir()
    (d / "momentum_track.jsonl").write_text(
        json.dumps({"t": 0, "equity": 100.0, "basket": 0.0, "weights": {}, "halted": False}) + "\n"
        + json.dumps({"t": 86400, "equity": 101.0, "basket": -0.02, "weights": {"BTCUSDT": 0.2}, "halted": False})
        + "\n")
    (d / "momentum_state.json").write_text(json.dumps({"cash0": 100.0, "equity": 101.0, "days": 1, "start_day": 0,
                                                       "weights": {"BTCUSDT": 0.2}, "halted": False}))
    sgn.record(str(d / "senales.jsonl"), 0, {"v": ["BTCUSDT", "<b>X</b>"]}, {"BTCUSDT": 100.0, "<b>X</b>": 1.0})
    sgn.record(str(d / "senales.jsonl"), 86_400_000, {"v": []}, {"BTCUSDT": 105.0, "<b>X</b>": 1.0})
    return d


def test_cloud_sync_upserts_rows_without_leaking_the_key(tmp_path):
    d = _paper_dir(tmp_path)
    rows = cloud.rows_from_state(str(d))
    assert len(rows["paper_days"]) == 2 and rows["paper_days"][1]["positions"] == {"BTCUSDT": 0.2}
    assert len(rows["signals"]) == 4 and rows["scorecard"][0]["id"] == "live"
    calls = []

    class Http:
        def post(self, url, headers, content, timeout):
            calls.append((url, headers))
            return SimpleNamespace(status_code=201, text="")

    assert cloud.sync(str(d), env={}) == {}  # sin configurar: no hace nada
    env = {"SUPABASE_URL": "https://abc.supabase.co", "SUPABASE_KEY": "sekret"}
    sent = cloud.sync(str(d), env=env, http=Http())
    assert sent == {"paper_days": 2, "signals": 4, "scorecard": 1}
    assert calls[0][0].startswith("https://abc.supabase.co/rest/v1/paper_days?on_conflict=day")
    assert "merge-duplicates" in calls[0][1]["Prefer"]

    class Bad:
        def post(self, *a, **k):
            return SimpleNamespace(status_code=401, text="invalid key")

    with pytest.raises(RuntimeError) as e:
        cloud.sync(str(d), env=env, http=Bad())
    assert "sekret" not in str(e.value) and "401" in str(e.value)


def test_panel_is_self_contained_and_escapes_data(tmp_path):
    d = _paper_dir(tmp_path)
    page = panel_mod.build(str(d))
    assert page.startswith("<!doctype html>") and "<script" not in page and "http" not in page.split("<body>")[1]
    assert "<b>X</b>" not in page and "&lt;b&gt;X&lt;/b&gt;" in page
    assert "1/20" in page and "101.00" in page and "<svg" in page
    rc = bot.main(["panel", "--dir", str(d)])
    assert rc == 0 and (d / "panel.html").exists()


def test_notifier_webhook_and_notificar_command(monkeypatch, capsys):
    sent = []

    class Http:
        def post(self, url, json, timeout):
            sent.append((url, json))
            return SimpleNamespace(status_code=200)

    n = Notifier(token="", chat_id="", http=Http(), webhook="https://hooks.example/x")
    assert n.enabled and n.send("hola") and sent[0][1]["text"] == "hola"
    assert not Notifier(token="", chat_id="", http=Http(), webhook="http://inseguro").send("x")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("FREELM_WEBHOOK_URL", raising=False)
    assert bot.main(["notificar"]) == 1 and "No hay avisos" in capsys.readouterr().out
    assert bot.main(["sync"]) == 0


def test_dashboard_data_builds_six_datasets(tmp_path):
    import dashboard_data
    d = _paper_dir(tmp_path)
    raw = {s: _daily(_rw(i, 400)) for i, s in enumerate(["AUSDT", "BUSDT", "CUSDT"])}
    data = dashboard_data.build(str(d), raw, list(raw))
    assert set(data) == {"paper", "radar", "scorecard_history", "scorecard_live", "backtest", "strategies"}
    assert data["paper"][-1]["equity"] == 101.0 and data["paper"][-1]["bot_pct"] == pytest.approx(0.01)
    assert {r["symbol"] for r in data["radar"]} == {"A", "B", "C"} and all(0 <= r["votes"] <= 10 for r in data["radar"])
    assert data["backtest"][0]["bot"] == pytest.approx(1.0) and any(r["strategy"] == "conjunto" for r in data["strategies"])
    paths = dashboard_data.write(str(tmp_path / "out"), data)
    assert len(paths) == 6 and all(os.path.getsize(p) > 1 for p in paths)
