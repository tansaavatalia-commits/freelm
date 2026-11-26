from __future__ import annotations

import http.client
import json

import pytest

from genesis.chat import NO_ENGINE, ChatError
from genesis.intelligence.base import EngineError, Provider, ProviderSpec

from .test_api import call, server  # noqa: F401 - pytest fixture


class FakeStreamer(Provider):
    """A free remote chat engine that streams canned deltas (no network)."""

    def __init__(self, deltas=("Ciao", ", sono ", "GÉNESIS."), fail_after=None):
        self.spec = ProviderSpec("fake-chat", "Fake chat", "1", "remote", frozenset({"chat", "code", "reasoning"}),
                                 "free", 3, "modello esterno")
        self.deltas, self.fail_after, self.calls = list(deltas), fail_after, []

    def run(self, request, task_type):
        return "".join(self.deltas)

    def stream(self, messages):
        self.calls.append(messages)
        for i, d in enumerate(self.deltas):
            if self.fail_after is not None and i == self.fail_after:
                raise EngineError("quota esaurita")
            yield d


def _online(g, streamer=None):
    fake = streamer or FakeStreamer()
    g.router.providers.append(fake)
    g.router._stats[fake.spec.id] = {"ok": 0, "fail": 0, "ms": None}
    g.router.remote_enabled = g.router.remote_free_verified = True
    return fake


def _stream(plan, g, cid):
    """Consume a stream plan the way the API does."""
    text = "".join(plan["provider"].stream(plan["messages"]))
    return g.chat.finish(cid, plan["provider"], text, ok=True, ms=12.0,
                         chars=sum(len(m["content"]) for m in plan["messages"]), task_type=plan["task_type"])


def test_conversations_lifecycle_and_titles(app):
    c = app.chat.create()
    assert c["title"] == "Nuova conversazione" and c["private"] is False
    app.chat.prepare(c["id"], "quanto fa 6*7?")
    conv = app.chat.get(c["id"])
    assert conv["title"] == "quanto fa 6*7?"  # named after the first question
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
    assert app.chat.rename(c["id"], "  Conti  ")["title"] == "Conti"
    assert app.chat.list()[0]["messages"] == 2
    app.chat.delete(c["id"])
    assert app.chat.list() == []
    with pytest.raises(ChatError, match="inesistente"):
        app.chat.get(c["id"])
    with pytest.raises(ChatError, match="vuoto"):
        app.chat.prepare(app.chat.create()["id"], "   ")


def test_math_is_answered_locally_and_verified(app):
    cid = app.chat.create()["id"]
    plan = app.chat.prepare(cid, "quanto fa 12*(3+4)?")
    assert plan["mode"] == "done" and plan["message"]["content"].strip().startswith("84")
    assert plan["message"]["engine"] == "local" and plan["message"]["status"] == "ok"


def test_without_online_engine_the_answer_is_honest(app):
    cid = app.chat.create()["id"]
    plan = app.chat.prepare(cid, "Raccontami la storia di Roma")
    assert plan["mode"] == "done" and plan["message"]["status"] == "error"
    assert plan["message"]["content"] == NO_ENGINE and "remote_enabled" not in NO_ENGINE


def test_remember_then_memory_reaches_the_model(app):
    fake = _online(app)
    cid = app.chat.create()["id"]
    plan = app.chat.prepare(cid, "ricorda che il mio colore preferito è il verde")
    assert plan["mode"] == "done" and plan["message"]["engine"] == "memory"
    plan = app.chat.prepare(cid, "qual è il mio colore preferito?")
    assert plan["mode"] == "stream" and plan["provider"] is fake
    system = plan["messages"][0]
    assert system["role"] == "system" and "verde" in system["content"]
    assert plan["messages"][-1] == {"role": "user", "content": "qual è il mio colore preferito?"}
    msg = _stream(plan, app, cid)
    assert msg["content"] == "Ciao, sono GÉNESIS." and msg["engine"] == "fake-chat"
    assert any(r["action"] == "intelligence.remote_call" for r in app.audit.tail(5))


def test_history_is_sent_in_order_within_budget(app, monkeypatch):
    _online(app)
    cid = app.chat.create()["id"]
    for q in ("prima domanda", "seconda domanda"):
        _stream(app.chat.prepare(cid, q), app, cid)
    plan = app.chat.prepare(cid, "terza domanda")
    roles = [m["role"] for m in plan["messages"]]
    assert roles == ["system", "user", "assistant", "user", "assistant", "user"]
    monkeypatch.setattr("genesis.chat.HISTORY_BUDGET", 10)  # tiny budget: only the current question survives
    plan = app.chat.prepare(cid, "quarta domanda")
    assert [m["role"] for m in plan["messages"]] == ["system", "user"]


def test_private_conversation_never_uses_remote_engines(app):
    fake = _online(app)
    cid = app.chat.create(private=True)["id"]
    plan = app.chat.prepare(cid, "Raccontami la storia di Roma")
    assert plan["mode"] == "done" and plan["message"]["status"] == "error" and fake.calls == []


def test_interrupted_stream_keeps_partial_text_and_marks_error(app):
    fake = _online(app, FakeStreamer(fail_after=2))
    cid = app.chat.create()["id"]
    plan = app.chat.prepare(cid, "dimmi qualcosa")
    parts = []
    with pytest.raises(EngineError):
        for d in fake.stream(plan["messages"]):
            parts.append(d)
    msg = app.chat.finish(cid, fake, "".join(parts), ok=False, ms=5.0, chars=10, task_type="chat",
                          error="quota esaurita")
    assert msg["status"] == "error" and msg["content"].startswith("Ciao, sono") and "quota esaurita" in msg["content"]
    # a failed answer is not sent back to the model as history
    nxt = app.chat.prepare(cid, "riprova")
    assert all("quota" not in m["content"] for m in nxt["messages"])


def test_conversations_travel_in_export(app, tmp_path, home):
    from genesis.app import Genesis

    from .conftest import LITE_HW
    cid = app.chat.create()["id"]
    app.chat.prepare(cid, "quanto fa 2+2?")
    counts = app.db.export_json(tmp_path / "x.json")
    assert counts["conversations"] == 1 and counts["messages"] == 2
    other = Genesis(tmp_path / "other", hardware=LITE_HW)
    try:
        other.db.import_json(tmp_path / "x.json")
        assert other.chat.get(cid)["messages"][1]["content"].startswith("4")
    finally:
        other.close()


def _events(srv, cid, text):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=10)
    conn.request("POST", f"/api/chat/{cid}/send", body=json.dumps({"text": text}).encode(),
                 headers={"Host": f"127.0.0.1:{srv.port}", "X-Genesis-Token": srv.token,
                          "Content-Type": "application/json"})
    resp = conn.getresponse()
    assert resp.status == 200 and resp.getheader("Content-Type").startswith("text/event-stream")
    raw = resp.read().decode("utf-8")
    conn.close()
    return [json.loads(line[6:]) for line in raw.splitlines() if line.startswith("data: ")]


def test_api_chat_streams_events(server):  # noqa: F811 - pytest fixture
    status, conv, _ = call(server, "POST", "/api/chat", {"title": ""})
    assert status == 201
    assert call(server, "GET", "/api/chat-status")[1]["online"] is False
    events = _events(server, conv["id"], "quanto fa 3*3?")
    assert [e["type"] for e in events] == ["user", "done"] and events[1]["message"]["content"].startswith("9")

    server.core.run(lambda g: _online(g))
    assert call(server, "GET", "/api/chat-status")[1]["online"] is True
    events = _events(server, conv["id"], "presentati")
    assert [e["type"] for e in events] == ["user", "start", "delta", "delta", "delta", "done"]
    assert "".join(e["text"] for e in events if e["type"] == "delta") == "Ciao, sono GÉNESIS."
    assert events[-1]["message"]["engine"] == "fake-chat"
    _, full, _ = call(server, "GET", f"/api/chat/{conv['id']}")
    assert len(full["messages"]) == 4 and full["messages"][-1]["content"] == "Ciao, sono GÉNESIS."
    assert call(server, "GET", "/api/chat")[1][0]["messages"] == 4


def test_api_chat_errors(server):  # noqa: F811 - pytest fixture
    _, conv, _ = call(server, "POST", "/api/chat", {})
    assert call(server, "POST", f"/api/chat/{conv['id']}/send", {"text": ""})[0] == 400
    assert call(server, "POST", f"/api/chat/{'0' * 32}/send", {"text": "ciao"})[0] == 400
    assert call(server, "POST", "/api/chat", {"private": "si"})[0] == 400
    assert call(server, "POST", f"/api/chat/{conv['id']}/rename", {"title": "Prova"})[1]["title"] == "Prova"
    assert call(server, "POST", f"/api/chat/{conv['id']}/delete")[1]["deleted"] is True
