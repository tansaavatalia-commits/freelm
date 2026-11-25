from __future__ import annotations

import pytest

from genesis.app import Genesis
from genesis.cli import main
from genesis.errors import ApprovalRequired, GenesisError, PermissionDenied
from genesis.improvement.components import PROTECTED
from genesis.intelligence.base import Request
from genesis.security.permissions import OWNER

from .conftest import LITE_HW


def _approval(app, imp_id):
    comp = app.improvement.get(imp_id)["component"]
    aid = app.permissions.request_approval(OWNER, f"improve.promote:{comp}", 4)
    app.permissions.decide(aid, True, decided_by=OWNER)
    return aid


def test_protected_areas_cannot_be_targeted(app):
    for area in PROTECTED:
        with pytest.raises(PermissionDenied, match="protetta"):
            app.improvement.propose(area, "v2")
    with pytest.raises(GenesisError):
        app.improvement.propose("classifier", "v9")
    with pytest.raises(GenesisError, match="già la versione attiva"):
        app.improvement.propose("classifier", "v1")


def test_detect_collects_evidence(app):
    found = app.improvement.detect("classifier")
    assert found["version"] == "v1" and found["errors"] == 3 + 23
    assert {e["dataset"] for e in found["experiments"]} == {"classify-it@1", "classify-holdout@1"}
    assert found["patterns"][0]["count"] >= 2


def test_full_cycle_promote_and_rollback(app):
    assert app.router.classify("come mai piove?") == "chat"  # v1 active
    proposal = app.improvement.propose("classifier", "v2")
    assert proposal["status"] == "proposed" and "errori" in proposal["problem"] and proposal["cause"]
    with pytest.raises(GenesisError):  # cannot promote before evaluation
        app.improvement.approve(proposal["id"], _approval(app, proposal["id"]))
    evaluated = app.improvement.evaluate(proposal["id"])
    ev = evaluated["evaluation"]
    assert ev["promotable"] and ev["improved"] == ["classify-holdout"] and not ev["regressed"]
    assert "interni" in ev["caveat"]
    with pytest.raises(ApprovalRequired):  # owner approval is mandatory
        app.improvement.approve(proposal["id"], None)
    done = app.improvement.approve(proposal["id"], _approval(app, proposal["id"]))
    assert done["status"] == "promoted" and app.improvement.active("classifier") == "v2"
    assert app.router.classify("come mai piove?") == "reasoning"  # the router uses the new version at once
    assert any(r["action"] == "improve.promote" for r in app.audit.tail(10))
    aid = app.permissions.request_approval(OWNER, "improve.rollback:classifier", 4)
    app.permissions.decide(aid, True, decided_by=OWNER)
    assert app.improvement.rollback("classifier", aid)["active"] == "v1"
    assert app.improvement.get(proposal["id"])["status"] == "rolled_back"


def test_math_promotion_reaches_the_local_engine(app):
    with pytest.raises(GenesisError):
        app.router.route(Request("Ho 3 mele e ne compro altre 4: quante mele ho?", "math", private=True))
    p = app.improvement.propose("math", "v2")
    assert app.improvement.evaluate(p["id"])["evaluation"]["promotable"]
    app.improvement.approve(p["id"], _approval(app, p["id"]))
    answer = app.router.route(Request("Ho 3 mele e ne compro altre 4: quante mele ho?", "math", private=True))
    assert answer["output"] == "7" and answer["engine"] == "local"


def test_no_promotion_without_evidence(app, monkeypatch):
    from genesis.improvement import components
    spec = components.COMPONENTS["classifier"]
    monkeypatch.setitem(components.COMPONENTS, "classifier", components.ComponentSpec(
        spec.name, spec.description, spec.default, spec.versions, spec.subjects, ("classify-it",)))
    p = app.improvement.propose("classifier", "v2")
    ev = app.improvement.evaluate(p["id"])["evaluation"]
    assert not ev["promotable"] and ev["recommendation"].startswith("non promuovere")
    with pytest.raises(GenesisError, match="prove non bastano"):
        app.improvement.approve(p["id"], _approval(app, p["id"]))
    assert app.improvement.reject(p["id"], "prove insufficienti")["status"] == "rejected"


def test_promotion_persists_across_restarts(home):
    g = Genesis(home, hardware=LITE_HW)
    try:
        p = g.improvement.propose("classifier", "v2")
        g.improvement.evaluate(p["id"])
        g.improvement.approve(p["id"], _approval(g, p["id"]))
    finally:
        g.close()
    g = Genesis(home, hardware=LITE_HW)
    try:
        assert g.improvement.active("classifier") == "v2" and g.router.classify("come mai piove?") == "reasoning"
    finally:
        g.close()


def test_improvement_cli_and_task(app, capsys):
    home = str(app.config.home)
    assert main(["--home", home, "improve", "components"]) == 0
    assert "classifier  attiva v1" in capsys.readouterr().out
    app.tasks.submit("improve.cycle", {"component": "classifier", "candidate": "v2"})
    result = app.tasks.run_next()["result"]
    assert result["promotable"] and result["recommendation"].startswith("promuovere")
    imp = result["improvement_id"]
    assert main(["--home", home, "improve", "approve", imp[:8]]) == 2  # needs --confirm
    assert main(["--home", home, "improve", "approve", imp[:8], "--confirm"]) == 0
    assert "Promossa" in capsys.readouterr().out
    assert main(["--home", home, "improve", "rollback", "classifier", "--confirm"]) == 0
    assert main(["--home", home, "improve", "list"]) == 0
    assert main(["--home", home, "improve", "propose", "permissions", "v2"]) == 1
