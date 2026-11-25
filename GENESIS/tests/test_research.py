from __future__ import annotations

import json

import pytest

from genesis.cli import main
from genesis.errors import GenesisError
from genesis.intelligence.local import evaluate, extract_expression
from genesis.research.datasets import BUILTIN, parse_dataset
from genesis.research.scoring import score
from genesis.research.stats import bootstrap_diff_ci, mcnemar_exact, percentile

from .test_agents import _online

REQUIRED_FIELDS = ("Identificatore", "Obiettivo", "Ipotesi", "Dati", "Modello e versione", "Configurazione",
                   "Risultato", "Tempo", "Risorse", "Errori", "Valutazione", "Riproducibilità")


def test_statistics():
    assert mcnemar_exact(0, 0) == 1.0 and mcnemar_exact(5, 5) == 1.0
    assert mcnemar_exact(17, 0) == pytest.approx(2 * 0.5**17)
    assert mcnemar_exact(10, 2) == pytest.approx(0.0386, abs=1e-4)  # textbook value
    pairs = [(0, 1)] * 10 + [(1, 1)] * 10
    assert bootstrap_diff_ci(pairs, seed=1) == bootstrap_diff_ci(pairs, seed=1)  # seeded = reproducible
    lo, hi = bootstrap_diff_ci(pairs, seed=1)
    assert 0 < lo <= 0.5 <= hi <= 1
    assert percentile([1, 2, 3, 4], 50) == 2 and percentile([], 50) is None


@pytest.mark.parametrize("scorer,expected,output,ok", [
    ("numeric", 2.5, "Il risultato è 2,5", True), ("numeric", 84, "84", True), ("numeric", 84, "circa 85", False),
    ("contains", "Roma", "La capitale è ROMA.", True), ("contains", "Au", "L'aurora", False),
    ("contains", ["7", "sette"], "Sono sette giorni", True), ("label", "math", " Math ", True),
    ("exact", "Città", "citta", True), ("numeric", 1, None, False),
])
def test_scorers(scorer, expected, output, ok):
    assert score(scorer, expected, output) is ok


def test_builtin_datasets_are_valid_and_correct():
    math_ds = next(d for d in BUILTIN if d.name == "math-basic")
    for item in math_ds.items[:24]:  # the computable ones: expected values verified independently
        assert evaluate(extract_expression(item.input)) == pytest.approx(item.expected)
    assert len({d.ref for d in BUILTIN}) == 5 and all(len(d.hash) == 64 for d in BUILTIN)


@pytest.mark.parametrize("bad", [{"name": "X"}, {"items": []}, {"items": [{"input": "a", "expected": "x", "scorer": "numeric"}]},
                                 {"items": [{"input": "a", "expected": 1, "scorer": "magic"}]}, {"extra": 1}])
def test_dataset_validation(bad):
    raw = {"name": "ok", "version": "1", "description": "", "items": [{"input": "a", "expected": 1, "scorer": "numeric"}]}
    with pytest.raises(GenesisError):
        parse_dataset({**raw, **bad})


def test_dataset_import_and_version_discipline(app, tmp_path):
    path = tmp_path / "d.json"
    path.write_text(json.dumps({"name": "mio", "version": "1", "description": "prova",
                                "items": [{"input": "1+1", "expected": 2, "scorer": "numeric"}]}), encoding="utf-8")
    assert app.lab.datasets.import_file(path)["ref"] == "mio@1"
    assert app.lab.datasets.import_file(path)["ref"] == "mio@1"  # same content: idempotent
    path.write_text(json.dumps({"name": "mio", "version": "1", "description": "prova",
                                "items": [{"input": "1+2", "expected": 3, "scorer": "numeric"}]}), encoding="utf-8")
    with pytest.raises(GenesisError, match="aumenta la versione"):
        app.lab.datasets.import_file(path)


def test_classifier_beats_majority_baseline_with_evidence(app):
    base = app.lab.run(dataset="classify-it", subject="baseline:majority")
    rules = app.lab.run(dataset="classify-it", subject="classifier", objective="misurare il classificatore",
                        hypothesis="le regole battono la baseline", baseline_id=base["id"])
    assert base["metrics"]["correct"] == 10 and rules["metrics"]["correct"] == 27
    cmp = app.lab.compare(base["id"], rules["id"])
    assert cmp["comparable"] and cmp["significant"] and cmp["only_b_correct"] == 17 and cmp["only_a_correct"] == 0
    assert cmp["mcnemar_p"] < 0.001 and cmp["diff_ci95"][0] > 0
    assert "sostenuta dai dati" in rules["evaluation"]
    for field in ("id", "objective", "hypothesis", "dataset_hash", "subject_version", "config", "metrics",
                  "resources", "errors", "evaluation", "environment", "seed"):
        assert rules[field] not in (None, "")
    assert rules["resources"]["wall_s"] >= 0 and rules["environment"]["genesis"]


def test_local_math_and_router_measure_their_limits(app):
    local = app.lab.run(dataset="math-basic", subject="local.math")
    routed = app.lab.run(dataset="math-basic", subject="router")  # private: local engines only
    assert local["metrics"]["correct"] == 24 and routed["metrics"]["correct"] == 24  # word problems fail honestly
    assert local["metrics"]["errors"] == 2 and routed["metrics"]["engines"]["local"] == 24
    cmp = app.lab.compare(local["id"], routed["id"])
    assert cmp["comparable"] and not cmp["significant"] and "nessuna differenza dimostrata" in cmp["verdict"]


def test_not_comparable_and_small_samples(app):
    a = app.lab.run(dataset="classify-it", subject="classifier")
    b = app.lab.run(dataset="math-basic", subject="local.math")
    assert app.lab.compare(a["id"], b["id"])["comparable"] is False
    small = app.lab.run(dataset="classify-it", subject="baseline:majority", sample=10, seed=3)
    assert "troppo piccolo" in app.lab.compare(small["id"], a["id"])["verdict"]


def test_reproduction(app):
    first = app.lab.run(dataset="classify-it", subject="classifier", seed=7, sample=25)
    again = app.lab.reproduce(first["id"][:8])
    assert again["reproducible"] is True and again["identical_items"] == 25
    assert app.lab.get(again["reproduction"])["reproduced_from"] == first["id"]
    assert app.lab.get(first["id"])["config"]["order"] == app.lab.get(again["reproduction"])["config"]["order"]


def test_remote_quota_guard_and_agent_subject(app):
    with pytest.raises(GenesisError, match="chiamate remote"):
        app.lab.run(dataset="qa-facts", subject="council", allow_remote=True)
    _online(app, ["La capitale è Roma."])
    exp = app.lab.run(dataset="qa-facts", subject="agent:researcher", allow_remote=True, sample=5, seed=1)
    assert exp["metrics"]["n"] == 5 and exp["deterministic"] is False
    assert exp["metrics"]["engines"] == {"fake": 5}
    private = app.lab.run(dataset="qa-facts", subject="agent:researcher", sample=5, seed=1)
    assert private["metrics"]["correct"] == 0 and private["metrics"]["errors"] == 5  # stays local: no engine for chat


def test_interrupted_experiments_and_resolve(app):
    exp = app.lab.run(dataset="math-basic", subject="local.math", sample=3)
    with app.db.transaction() as c:
        c.execute("UPDATE experiments SET status = 'running' WHERE id = ?", (exp["id"],))
    app.lab.run(dataset="math-basic", subject="local.math", sample=3)
    assert app.lab.get(exp["id"])["status"] == "interrupted"
    for bad in ("zz", "'; DROP TABLE experiments; --", "0000"):
        with pytest.raises(GenesisError):
            app.lab.resolve(bad)


def test_report_has_all_required_fields(app):
    base = app.lab.run(dataset="classify-it", subject="baseline:majority")
    rules = app.lab.run(dataset="classify-it", subject="classifier")
    path = app.lab.report(rules["id"], compare_with=base["id"])
    text = path.read_text(encoding="utf-8")
    assert path.parent == app.config.reports_dir
    for field in REQUIRED_FIELDS:
        assert f"| {field} |" in text
    assert "B migliore di A: dimostrato" in text


def test_lab_cli_and_task(app, capsys):
    home = str(app.config.home)
    assert main(["--home", home, "lab", "datasets"]) == 0
    assert "classify-it@1" in capsys.readouterr().out
    assert main(["--home", home, "lab", "run", "--dataset", "classify-it", "--subject", "baseline:majority"]) == 0
    base = json.loads(capsys.readouterr().out)["experiment_id"]
    assert main(["--home", home, "lab", "run", "--dataset", "classify-it", "--subject", "classifier",
                 "--baseline", base[:8], "--hypothesis", "regole meglio"]) == 0
    rules = json.loads(capsys.readouterr().out)["experiment_id"]
    assert main(["--home", home, "lab", "compare", base[:8], rules[:8]]) == 0
    assert "B migliore di A" in capsys.readouterr().out
    assert main(["--home", home, "lab", "reproduce", rules[:8]]) == 0
    assert main(["--home", home, "lab", "report", rules[:8], "--compare", base[:8]]) == 0
    assert main(["--home", home, "lab", "run", "--dataset", "nope", "--subject", "classifier"]) == 1
    assert main(["--home", home, "lab", "list"]) == 0
