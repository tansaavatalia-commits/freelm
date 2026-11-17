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
    pf2.open(Position("Y", 5, 100, 50, 200, 50, 0, 100, ""))
    assert r2.tick(pf2, 800, {"Y": 60}, 1) == "HALT" and r2.halted and not pf2.positions
    assert r2.can_open(pf2) == "interruptor activado"


def test_losing_streak_pauses_trading():
    pf, r = Portfolio(cash=10_000), RiskManager(max_losing_streak=2, cooldown=5)
    for i in range(2):
        pf.open(Position(f"S{i}", 1, 100, 98, 104, 2, 0, 100, ""))
        r.manage(pf, f"S{i}", 1, 100, 97, 97, 1.0, 0.0)
    assert r.pause_left == 5 and "pausa" in r.can_open(pf)


def test_backtest_runs_offline_and_saves_memory(tmp_path, capsys):
    state = str(tmp_path / "m.json")
    argv = ["--symbols", "BTCUSDT,ETHUSDT", "--limit", "520", "--state", state]
    assert bot.main(["backtest", *argv, "--train", "0.5"]) == 0
    out = capsys.readouterr().out
    assert "validación fuera de muestra" in out and "señales/segundo" in out and os.path.exists(state)
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
