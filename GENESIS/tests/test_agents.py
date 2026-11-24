from __future__ import annotations

import json

import pytest

from genesis.agents.catalog import BUILTIN, load_agents
from genesis.agents.runtime import decompose, verify
from genesis.app import Genesis
from genesis.errors import GenesisError, PermissionDenied
from genesis.intelligence.base import Provider, ProviderSpec

from .conftest import LITE_HW, write_config


class FakeRemote(Provider):
    def __init__(self, answers):
        self.spec = ProviderSpec("fake", "fake", "1", "remote", frozenset({"chat", "code", "reasoning", "math"}),
                                 "free", 3, "modello esterno")
        self.answers, self.prompts = list(answers), []

    def run(self, request, task_type):
        self.prompts.append(request.prompt)
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]


def _online(g, answers):
    fake = FakeRemote(answers)
    g.router.providers.append(fake)
    g.router._stats["fake"] = {"ok": 0, "fail": 0, "ms": None}
    g.router.remote_enabled = g.router.remote_free_verified = True
    return fake


def test_catalog_has_the_eight_agents_with_level_1(app):
    assert {a.id for a in BUILTIN} == {"director", "researcher", "developer", "analyst", "creator", "manager",
                                       "verifier", "security"}
    assert all(a["level"] == 1 for a in app.agents.describe())


def test_custom_agent_starts_without_permissions(home):
    folder = home / "agents"
    folder.mkdir(parents=True)
    (folder / "trad.json").write_text(json.dumps({
        "id": "traduttore", "name": "Traduttore", "version": "1.0", "role": "lingue", "objective": "Tradurre",
        "instructions": "Traduci in inglese.", "task_types": ["chat"], "success_criteria": "traduzione fedele"}),
        encoding="utf-8")
    g = Genesis(home, hardware=LITE_HW)
    try:
        assert g.agents.get("traduttore").version == "1.0"
        with pytest.raises(PermissionDenied):  # no grant until the owner adds one
            g.agents.run("traduttore", "ciao mondo")
    finally:
        g.close()
    write_config(home, '[permissions.grants]\n"agent.traduttore" = 1\n')
    g = Genesis(home, hardware=LITE_HW)
    try:
        assert g.agents.run("traduttore", "ciao")["ok"] is False  # allowed now; fails only for lack of an engine
    finally:
        g.close()


@pytest.mark.parametrize("bad", [{"id": "X"}, {"task_types": ["paid"]}, {"max_steps": 9}, {"extra": 1}])
def test_invalid_agent_definitions(tmp_path, bad):
    base = {"id": "ok", "name": "n", "version": "1", "role": "r", "objective": "o", "instructions": "i",
            "task_types": ["chat"], "success_criteria": "s"}
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "a.json").write_text(json.dumps({**base, **bad}), encoding="utf-8")
    with pytest.raises(GenesisError):
        load_agents(tmp_path)


def test_analyst_math_is_local_and_verified(app):
    result = app.agents.run("analyst", "quanto fa 12*(3+4)?")
    step = result["steps"][0]
    assert result["ok"] and result["output"] == "84" and step["engine"] == "local" and step["verified"]
    assert app.agents.runs()[0]["status"] == "succeeded"


def test_agent_refuses_task_types_outside_its_role(app):
    result = app.agents.run("developer", "2+2")
    assert not result["ok"] and "non gestisce 'math'" in result["output"]


def test_verifier_catches_a_wrong_model_answer(app):
    _online(app, ["Il risultato è 85"])
    result = app.agents.run("analyst", "12*(3+4)", private=False)
    assert result["steps"][0]["engine"] == "local"  # the router prefers the exact engine anyway
    checks = verify("math", "12*(3+4)", "Il risultato è 85")
    assert [c["ok"] for c in checks][-1] is False
    assert verify("chat", "x", "token: sk-or-v1-" + "a" * 40)[1]["ok"] is False


def test_agent_prompt_carries_instructions_for_models(app):
    fake = _online(app, ["Ecco una risposta"])
    result = app.agents.run("researcher", "Che cos'è SQLite?")
    assert result["ok"] and fake.prompts[0].startswith("Rispondi in modo fattuale")


def test_director_decomposes_and_delegates(app):
    _online(app, ["def f(): pass  # codice"])
    assert decompose("1. calcola 2+2\n2. scrivi codice python per sommare") == ["calcola 2+2",
                                                                              "scrivi codice python per sommare"]
    result = app.agents.direct("1. calcola 2+2\n2. scrivi codice python per sommare")
    agents = [s["agent"] for s in result["steps"]]
    assert agents == ["analyst", "developer"] and result["ok"] and "-> analyst: 4" in result["output"]


def test_director_reports_failures_honestly(app):
    result = app.agents.direct("calcola 3*3; scrivi una poesia")
    assert not result["ok"] and "-> analyst: 9" in result["output"] and "NON RIUSCITO" in result["output"]


def test_council_detects_contradictions_and_agreement(app):
    _online(app, ["La risposta è 42", "Direi 42", "Secondo me 41"])
    result = app.agents.council("Quante sono le risposte giuste? Ragiona", ["researcher", "analyst", "manager"])
    council = result["council"]
    assert council["answered"] == 3 and council["contradictions"] and council["agreement"] == 0.67
    assert not result["ok"]
    with pytest.raises(GenesisError):
        app.agents.council("x", ["researcher"])


def test_agent_tasks_and_cli(app, capsys):
    app.tasks.submit("agents.run", {"agent": "analyst", "goal": "7*6"})
    assert app.tasks.run_next()["result"]["output"] == "42"
    app.tasks.submit("agents.run", {"agent": "analyst"})
    assert app.tasks.run_next()["status"] == "failed"
    from genesis.cli import main
    assert main(["--home", str(app.config.home), "agents", "list"]) == 0
    assert main(["--home", str(app.config.home), "agents", "run", "analyst", "10/4"]) == 0
    assert "2.5" in capsys.readouterr().out
    assert main(["--home", str(app.config.home), "agents", "direct", "calcola 1+1; scrivi una poesia"]) == 1
    assert main(["--home", str(app.config.home), "agents", "runs"]) == 0
