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
from learning import Coordinator, detect_regime  # noqa: E402
from market import Candle, synthetic  # noqa: E402
from risk import PaperBroker, RiskManager  # noqa: E402


def test_indicators_basic():
    xs = [float(i) for i in range(1, 41)]
    assert ta.sma(xs, 5)[4] == 3.0
    assert ta.ema(xs, 5)[3] is None and ta.ema(xs, 5)[-1] == pytest.approx(38.0)
    assert ta.rsi(xs)[-1] == 100.0  # only gains
    assert ta.rsi(list(reversed(xs)))[-1] == pytest.approx(0.0)
    lo, mid, up = ta.bollinger([5.0] * 30)
    assert lo[-1] == mid[-1] == up[-1] == 5.0
    assert ta.obv([1, 2, 1, 1], [10, 10, 5, 7]) == [0, 10, 5, 5]


def test_agents_emit_bounded_signals():
    cs = synthetic(300, seed=1)
    for a in agents.default_agents():
        s = a.analyze(cs)
        assert -1 <= s.score <= 1 and 0 <= s.confidence <= 1 and s.reason


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
    assert c.weights["tendencia"]["good"] == pytest.approx(0.5)  # other regimes untouched


def test_coordinator_persists(tmp_path):
    p = str(tmp_path / "m.json")
    c = Coordinator(["a", "b"])
    c.learn([agents.Signal("a", 1, 1, "")], "lateral", 0.02, 0.01)
    c.save(p)
    c2 = Coordinator.load(p, ["a", "b", "new"])
    assert c2.updates == 1 and c2.weights["lateral"]["a"] > c2.weights["lateral"]["b"]
    assert "new" in c2.weights["lateral"]


def test_regime_detection():
    up = [Candle(i, 100 + i, 101 + i, 99 + i, 100 + i, 1) for i in range(100)]
    assert detect_regime(up) == "tendencia"
    flat = [Candle(i, 100, 101, 99, 100 + (1 if i % 2 else -1), 1) for i in range(100)]
    assert detect_regime(flat) == "lateral"


def test_risk_stop_and_kill_switch():
    b, r = PaperBroker(cash=1000), RiskManager(peak_equity=1000)
    assert r.act(b, 0, 100, 99, 1.0, 0.8) == "BUY" and b.qty > 0
    assert r.act(b, 1, 99, 97, 1.0, 0.5) == "STOP" and b.qty == 0
    b2, r2 = PaperBroker(cash=1000), RiskManager(peak_equity=1000, max_drawdown=0.1)
    r2.act(b2, 0, 100, 99, 0.1, 0.9)
    assert r2.act(b2, 1, 50, 50, None, 0.9) in ("HALT", "STOP")
    assert r2.act(b2, 2, 120, 119, 1.0, 0.9) is None or r2.halted


def test_backtest_runs_offline_and_saves_memory(tmp_path, capsys):
    state = str(tmp_path / "BTC.json")
    assert bot.main(["backtest", "--limit", "400", "--state", state]) == 0
    assert os.path.exists(state)
    assert "Lo que ha aprendido" in capsys.readouterr().out
    assert bot.main(["status", "--state", state]) == 0


def test_llm_agent_parses_json_and_survives_failures():
    ok = SimpleNamespace(chat=lambda *a, **k: SimpleNamespace(
        text='Claro: {"score": 0.6, "confidence": 0.7, "reason": "tendencia sana"}', provider="groq"))
    s = agents.LLMAnalystAgent(ok).analyze(synthetic(120))
    assert s.score == 0.6 and "groq" in s.reason

    def boom(*a, **k):
        raise RuntimeError("no keys")

    s2 = agents.LLMAnalystAgent(SimpleNamespace(chat=boom)).analyze(synthetic(120))
    assert s2.value == 0.0


def test_metrics():
    m = bot.metrics([100, 110, 99, 120], 365)
    assert m["return"] == pytest.approx(0.2) and m["max_drawdown"] == pytest.approx(0.1)
    assert not math.isnan(m["sharpe"])
