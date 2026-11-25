from __future__ import annotations

import struct
import wave

import pytest

from genesis.app import Genesis, import_data
from genesis.engines.base import KINDS, EngineOpError
from genesis.engines.code import analyze_python, check_json
from genesis.engines.data import aggregate, profile
from genesis.engines.reasoning import classify_v2, math_v2, normalize_math_text, solve_word_problem
from genesis.engines.research import summarize
from genesis.errors import ApprovalRequired, GenesisError, PermissionDenied
from genesis.intelligence.base import EngineError
from genesis.security.permissions import OWNER
from genesis.tools import web

from .conftest import LITE_HW

TEXT = ("GÉNESIS è una piattaforma di intelligenza estensibile. La piattaforma coordina motori e agenti. "
        "Gli agenti usano strumenti con permessi minimi. Il laboratorio misura ogni miglioramento con esperimenti. "
        "Oggi piove a Roma e non c'entra nulla.")


def test_every_engine_declares_its_nature(app):
    manifests = app.engines.describe()
    assert {m["id"] for m in manifests} == {"reasoning", "code", "research", "data", "memory", "multimodal"}
    for m in manifests:
        assert m["components"] and all(c["kind"] in KINDS for c in m["components"]) and m["operations"]
        assert m["uses_external_model"] is False  # no engine silently wraps an external model


@pytest.mark.parametrize("text,answer", [("Quanto fa 15 per 4?", "60"), ("radice quadrata di 49", "7"),
                                         ("il 20% di 150", "30"), ("100 diviso 4", "25"),
                                         ("Ho 2 dozzine di uova: quante uova sono?", "24")])
def test_reasoning_math_v2(text, answer):
    assert math_v2(text)[0] == answer


def test_word_problems_explain_and_refuse_when_unsure():
    value, how = solve_word_problem("Marco ha 15 figurine e ne regala 6. Quante gli rimangono?")
    assert value == 9 and how == "15 − 6 = 9"
    for unsure in ("Ho 3 mele", "Ho 1, 2 e 3 euro: quanti ne ho?", "Il 5 e il 7 sono numeri primi"):
        with pytest.raises(EngineError):
            solve_word_problem(unsure)
    assert normalize_math_text("calcola 3 più 4") == "3+4"


def test_classifier_v2_rules():
    assert classify_v2("Quante parole ci sono in questa frase?") == "text.stats"
    assert classify_v2("come leggo un file CSV in Java?") == "code"
    assert classify_v2("come mai d'inverno fa più freddo?") == "reasoning"
    assert classify_v2("Se ho 20 euro e ne spendo 7, quanti me ne restano?") == "math"
    assert classify_v2("chi ha vinto i mondiali del 2006?") == "chat"


def test_reasoning_engine_ops(app):
    run = lambda op, **p: app.engines.run(OWNER, "reasoning", op, p)["result"]  # noqa: E731
    assert run("classify", text="come mai piove?", version="v1") == {"task_type": "chat", "version": "v1"}
    assert run("classify", text="come mai piove?")["task_type"] == "reasoning"
    assert run("solve", text="Un libro costa 12 euro: quanto costano 5 libri?")["answer"] == "60"
    assert run("decompose", text="1. a\n2. b")["subtasks"] == ["a", "b"]
    with pytest.raises(EngineOpError):
        run("solve", text="scrivi una poesia")
    with pytest.raises(EngineOpError):
        run("fly", text="x")


def test_code_engine():
    src = "import os, json\n\ndef f(x):\n    if x and x > 1:\n        return eval(x)\n    return os.system('ls')\n"
    report = analyze_python(src)
    assert report["syntax_ok"] and report["unused_imports"] == ["json"] and report["functions"][0]["complexity"] == 3
    assert {r["call"] for r in report["risky_calls"]} == {"eval", "os.system"}
    bad = analyze_python("def broken(:\n  pass")
    assert not bad["syntax_ok"] and bad["error"]["line"] == 1
    assert check_json('{"a": 1}')["valid"] and check_json('{"a": }')["error"]["line"] == 1
    assert analyze_python("import subprocess\nsubprocess.run('x', shell=True)")["risky_calls"][0]["reason"] == "shell=True"


def test_research_engine(app, monkeypatch):
    result = summarize(TEXT, 2)
    assert result["summary"].count(".") == 2 and "Roma" not in result["summary"]
    assert any(k["word"] == "piattaforma" for k in result["keywords"])
    out = app.engines.run(OWNER, "research", "keywords", {"text": TEXT})
    assert out["uses_external_model"] is False
    with pytest.raises(EngineOpError, match="disattivato"):  # web goes through the tool: internet is off
        app.engines.run(OWNER, "research", "summarize", {"url": "https://example.org"})
    monkeypatch.setattr(web, "fetch", lambda p, c, opener=None: {"text": TEXT, "url": p["url"]})
    app.tools._specs["web.fetch"] = app.tools._web_tool(True)
    page = app.engines.run(OWNER, "research", "summarize", {"url": "https://example.org", "sentences": 1})["result"]
    assert page["source"]["untrusted"] and len(page["source"]["sha256"]) == 64


def test_data_engine(app):
    csv_text = "città;vendite;mese\nRoma;10,5;gen\nMilano;20;gen\nRoma;4,5;feb\nNapoli;;feb\n"
    p = profile(csv_text)
    vendite = next(c for c in p["columns"] if c["name"] == "vendite")
    assert p["rows"] == 4 and vendite["type"] == "numerico" and vendite["missing"] == 1 and vendite["mean"] == pytest.approx(11.6667, abs=1e-4)
    agg = aggregate(csv_text, "città", "vendite", "sum")
    assert agg["rows"] == [{"group": "Milano", "value": 20.0}, {"group": "Roma", "value": 15.0}]
    assert agg["skipped_non_numeric"] == 1
    assert aggregate(csv_text, "mese", None, "count")["rows"] == [{"group": "feb", "value": 2}, {"group": "gen", "value": 2}]
    app.tools.call(OWNER, "files.write", {"path": "v.csv", "content": csv_text})
    assert app.engines.run(OWNER, "data", "profile", {"path": "v.csv"})["result"]["rows"] == 4
    with pytest.raises(EngineOpError):
        aggregate(csv_text, "nope", None, "count")


def test_memory_levels_search_and_permissions(app):
    mem = app.engines.memory
    project = app.projects.create("Ricerca")
    run = lambda p, op, **kw: app.engines.run(p, "memory", op, kw)["result"]  # noqa: E731
    run(OWNER, "remember", content="Il gatto di Anna si chiama Pallino", level="project", project="Ricerca", tags=["animali"])
    run(OWNER, "remember", content="La chiave è sk-or-v1-" + "s" * 40, level="permanent")
    run(OWNER, "remember", content="Nota veloce sulla città", level="immediate")
    hits = run(OWNER, "recall", query="gatto Pallino")
    assert hits[0]["content"].startswith("Il gatto") and hits[0]["project_id"] == project["id"]
    assert run(OWNER, "recall", query="citta")[0]["level"] == "immediate"  # accents ignored, immediate included
    assert "s" * 40 not in mem.recall("chiave")[0]["content"]  # secrets never stored
    with pytest.raises(PermissionDenied):  # agents are level 1: project memory is level 2
        run("agent.researcher", "remember", content="x", level="project", project="Ricerca")
    with pytest.raises(PermissionDenied):  # level-1 agent: cannot even ask for a level-4 action
        mem.remember("agent.researcher", "ricorda questo", "permanent")
    with pytest.raises(EngineOpError, match="sistema"):
        mem.remember(OWNER, "x", "operational")
    assert mem.remember("system", "avvio completato", "operational")["level"] == "operational"
    memory_id = hits[0]["id"]
    assert run(OWNER, "forget", id=memory_id)["forgotten"] and not run(OWNER, "recall", query="Pallino")
    ctx = run(OWNER, "context", query="chiave città", budget=200)
    assert ctx["characters"] <= 200 and ctx["memories"]
    with pytest.raises(EngineOpError):
        mem.recall("!!!")  # no words: refused
    assert mem.recall('" OR content MATCH "x') == []  # FTS syntax is quoted, never interpreted


def test_memories_travel_with_export_and_are_reindexed(app, tmp_path):
    app.engines.memory.remember(OWNER, "Ricordo importante sul progetto GÉNESIS", "permanent")
    path, _ = app.export_data(tmp_path / "export.json")
    new_home = tmp_path / "nuovo-pc"
    import_data(new_home, path)
    g = Genesis(new_home, hardware=LITE_HW)
    try:
        assert g.engines.memory.recall("ricordo importante")[0]["level"] == "permanent"
    finally:
        g.close()


def test_multimodal_engine(app):
    ws = app.config.workspace_dir
    (ws / "a.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", 640, 480) + b"\x00" * 20)
    (ws / "a.gif").write_bytes(b"GIF89a" + struct.pack("<HH", 32, 16) + b"\x00" * 10)
    (ws / "a.bmp").write_bytes(b"BM" + b"\x00" * 16 + struct.pack("<ii", 100, -50) + b"\x00" * 30)
    (ws / "a.jpg").write_bytes(b"\xff\xd8\xff\xc0\x00\x11\x08" + struct.pack(">HH", 200, 300) + b"\x00" * 20)
    (ws / "a.pdf").write_bytes(b"%PDF-1.7\n/Type /Page\n/Type /Page\n/Type /Pages\n")
    with wave.open(str(ws / "a.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 8000)
    run = lambda p: app.engines.run(OWNER, "multimodal", "inspect", {"path": p})["result"]  # noqa: E731
    assert (run("a.png")["width"], run("a.png")["height"]) == (640, 480)
    assert run("a.gif")["width"] == 32 and run("a.bmp")["height"] == 50 and run("a.jpg")["width"] == 300
    assert run("a.pdf")["pages_estimate"] == 2 and run("a.wav")["duration_s"] == 1.0
    assert "non disponibile" in run("a.png")["content_understanding"]
    with pytest.raises(GenesisError):
        run("../fuori.png")


def test_engine_task_and_lab_subjects(app):
    app.tasks.submit("engines.run", {"engine": "reasoning", "op": "solve", "payload": {"text": "6 per 7"}})
    assert app.tasks.run_next()["result"]["result"]["answer"] == "42"
    v1 = app.lab.run(dataset="classify-holdout", subject="classifier")
    v2 = app.lab.run(dataset="classify-holdout", subject="classifier@v2")
    assert (v1["metrics"]["correct"], v2["metrics"]["correct"]) == (17, 39)
    cmp = app.lab.compare(v1["id"], v2["id"])
    assert cmp["significant"] and cmp["accuracy_diff"] > 0
    words = app.lab.run(dataset="math-words", subject="math@v2")
    assert words["metrics"]["correct"] == 20


def test_engines_cli(app, capsys):
    from genesis.cli import main
    home = str(app.config.home)
    assert main(["--home", home, "engines", "list"]) == 0
    assert "solo algoritmi propri" in capsys.readouterr().out
    assert main(["--home", home, "engines", "run", "reasoning", "solve", "--payload", '{"text": "3 per 3"}']) == 0
    assert '"answer": "9"' in capsys.readouterr().out
    assert main(["--home", home, "engines", "run", "nope", "x"]) == 1


def test_agent_with_grant_4_still_needs_approval_for_permanent_memory(home):
    from .conftest import write_config
    write_config(home, '[permissions.grants]\n"agent.researcher" = 4\n')
    g = Genesis(home, hardware=LITE_HW)
    try:
        with pytest.raises(ApprovalRequired) as info:
            g.engines.memory.remember("agent.researcher", "ricorda questo", "permanent")
        g.permissions.decide(info.value.approval_id, True, decided_by=OWNER)
        saved = g.engines.memory.remember("agent.researcher", "ricorda questo", "permanent", approval_id=info.value.approval_id)
        assert saved["principal"] == "agent.researcher"
    finally:
        g.close()
