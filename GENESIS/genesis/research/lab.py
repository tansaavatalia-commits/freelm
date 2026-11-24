"""Research Lab: run benchmarks as recorded experiments, compare them fairly, reproduce them, report.

Every experiment stores the 12 fields required by the master prompt: identifier, objective,
hypothesis, data (dataset ref + hash), model and version (subject + version + engines),
configuration (+ hash), result (metrics + per-item results), time, resources, errors,
evaluation, reproducibility (seed, environment, deterministic flag, reproduced_from).
No improvement is claimed without a paired comparison on the same dataset hash.
"""

from __future__ import annotations

import hashlib
import json
import platform
import random
import re
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .. import __version__
from ..core.clock import Now, file_stamp, utcnow
from ..errors import GenesisError
from ..hardware.detect import process_memory_mb, process_peak_memory_mb
from .datasets import DatasetStore
from .scoring import score
from .stats import bootstrap_diff_ci, mcnemar_exact, percentile
from .subjects import make_subject

if TYPE_CHECKING:
    from ..app import Genesis

MAX_REMOTE_CALLS = 40  # below OpenRouter's ~50 free requests/day (freelm data, not verified on the account)
MIN_PAIRED = 20
ALPHA = 0.05
JSON_FIELDS = ("config", "environment", "metrics", "resources", "errors")


class ResearchLab:
    def __init__(self, app: Genesis, now: Now = utcnow) -> None:
        self.app, self.db, self._now = app, app.db, now
        self.datasets = DatasetStore(app.db, now)

    # -- running -------------------------------------------------------------------

    def run(self, *, dataset: str, subject: str, seed: int = 0, sample: int | None = None,
            allow_remote: bool = False, name: str | None = None, objective: str = "", hypothesis: str = "",
            baseline_id: str | None = None, reproduced_from: str | None = None) -> dict[str, Any]:
        ds_id, ds = self.datasets.get(dataset)
        if sample is not None and not 1 <= sample <= len(ds.items):
            raise GenesisError(f"sample deve essere tra 1 e {len(ds.items)}")
        subj = make_subject(self.app, subject, ds, allow_remote)
        order = list(range(len(ds.items)))
        random.Random(seed).shuffle(order)
        order = order[:sample] if sample else order
        estimate = len(order) * subj.remote_calls_per_item
        if estimate > MAX_REMOTE_CALLS:
            raise GenesisError(f"fino a {estimate} chiamate remote stimate: oltre il limite di {MAX_REMOTE_CALLS} "
                               "per esperimento (quota gratuita). Riduci --sample.")
        baseline = self.resolve(baseline_id) if baseline_id else None
        config = {"dataset": ds.ref, "subject": subject, "seed": seed, "sample": sample,
                  "allow_remote": allow_remote, "order": order}
        config_hash = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
        exp_id = uuid.uuid4().hex
        with self.db.transaction() as c:
            # Only the task worker runs experiments (worker lock): anything still 'running' is stale.
            c.execute("UPDATE experiments SET status = 'interrupted' WHERE status = 'running'")
            c.execute(
                "INSERT INTO experiments (id, name, objective, hypothesis, dataset_id, dataset_hash, subject, "
                "subject_version, deterministic, config, config_hash, seed, environment, status, baseline_id, "
                "reproduced_from, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'running', ?, ?, ?)",
                (exp_id, name or f"{subject} su {ds.ref}", objective, hypothesis, ds_id, ds.hash, subject,
                 subj.version, int(subj.deterministic), json.dumps(config), config_hash, seed,
                 json.dumps(self._environment()), baseline, reproduced_from, self._now()))
        rss_before, wall, cpu = process_memory_mb(), time.perf_counter(), time.process_time()
        rows = []
        for idx in order:
            item = ds.items[idx]
            t0 = time.perf_counter()
            out = subj.run(item)
            latency = round((time.perf_counter() - t0) * 1000, 2)
            correct = out["error"] is None and score(item.scorer, item.expected, out["output"])
            rows.append((exp_id, idx, item.input, json.dumps(item.expected, ensure_ascii=False), out["output"],
                         int(correct), latency, out["engine"], out["error"]))
        resources = {"wall_s": round(time.perf_counter() - wall, 3), "cpu_s": round(time.process_time() - cpu, 3),
                     "rss_mb_before": rss_before, "rss_mb_after": process_memory_mb(),
                     "peak_rss_mb_process": process_peak_memory_mb(), "remote_calls_max": estimate}
        metrics = _metrics(rows)
        errors = [{"item": r[1], "input": r[2], "error": r[8]} for r in rows if r[8]]
        evaluation = (f"Accuratezza {metrics['correct']}/{metrics['n']} ({metrics['accuracy']:.1%}). "
                      f"Errori di esecuzione: {len(errors)}. "
                      + ("Soggetto deterministico: deve riprodursi identico." if subj.deterministic
                         else "Soggetto non deterministico (modello esterno): riproduzione solo statistica."))
        with self.db.transaction() as c:
            c.executemany("INSERT INTO experiment_results (experiment_id, item_idx, input, expected, output, correct, "
                          "latency_ms, engine, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
            c.execute("UPDATE experiments SET status = 'completed', metrics = ?, resources = ?, errors = ?, "
                      "evaluation = ?, finished_at = ? WHERE id = ?",
                      (json.dumps(metrics), json.dumps(resources), json.dumps(errors, ensure_ascii=False),
                       evaluation, self._now(), exp_id))
        if baseline:
            verdict = self.compare(baseline, exp_id)
            text = f"{evaluation} Confronto con {baseline[:8]}: {verdict['verdict']}"
            if hypothesis:
                text += f" Ipotesi «{hypothesis}»: " + ("sostenuta dai dati." if verdict.get("significant")
                                                        and verdict["accuracy_diff"] > 0 else "non dimostrata.")
            with self.db.transaction() as c:
                c.execute("UPDATE experiments SET evaluation = ? WHERE id = ?", (text, exp_id))
        return self.get(exp_id)

    def reproduce(self, ref: str) -> dict[str, Any]:
        original = self.get(ref)
        cfg = original["config"]
        try:
            _, ds = self.datasets.get(cfg["dataset"])
        except GenesisError as exc:
            return {"reproducible": False, "reason": str(exc), "original": original["id"]}
        if ds.hash != original["dataset_hash"]:
            return {"reproducible": False, "reason": "il dataset è cambiato", "original": original["id"]}
        new = self.run(dataset=cfg["dataset"], subject=cfg["subject"], seed=cfg["seed"], sample=cfg["sample"],
                       allow_remote=cfg["allow_remote"], name=f"riproduzione di {original['name']}",
                       objective=original["objective"], hypothesis=original["hypothesis"],
                       reproduced_from=original["id"])
        a = {r["item_idx"]: r for r in self.results(original["id"])}
        b = {r["item_idx"]: r for r in self.results(new["id"])}
        same = sum(1 for k in a if k in b and a[k]["output"] == b[k]["output"] and a[k]["correct"] == b[k]["correct"])
        identical = same == len(a) == len(b)
        deterministic = bool(original["deterministic"])
        outcome = {"original": original["id"], "reproduction": new["id"], "deterministic": deterministic,
                   "identical_items": same, "items": len(a),
                   "accuracy_original": original["metrics"]["accuracy"], "accuracy_reproduction": new["metrics"]["accuracy"],
                   "reproducible": identical if deterministic else None,
                   "reason": ("risultati identici elemento per elemento" if identical else
                              "risultati diversi" if deterministic else
                              "modello esterno: confrontare le accuratezze, non le singole risposte")}
        with self.db.transaction() as c:
            c.execute("UPDATE experiments SET evaluation = evaluation || ? WHERE id = ?",
                      (f" Riproduzione di {original['id'][:8]}: {outcome['reason']}.", new["id"]))
        return outcome

    # -- comparison ----------------------------------------------------------------

    def compare(self, a_ref: str, b_ref: str) -> dict[str, Any]:
        a, b = self.get(a_ref), self.get(b_ref)
        base = {"a": a["id"], "b": b["id"], "a_subject": a["subject"], "b_subject": b["subject"]}
        if a["status"] != "completed" or b["status"] != "completed":
            return {**base, "comparable": False, "verdict": "non comparabili: un esperimento non è completato"}
        if a["dataset_hash"] != b["dataset_hash"]:
            return {**base, "comparable": False,
                    "verdict": "non comparabili: dataset diversi (hash diverso). Nessuna conclusione possibile."}
        ra = {r["item_idx"]: r for r in self.results(a["id"])}
        rb = {r["item_idx"]: r for r in self.results(b["id"])}
        common = sorted(set(ra) & set(rb))
        pairs = [(ra[i]["correct"], rb[i]["correct"]) for i in common]
        n = len(pairs)
        only_a = sum(1 for x, y in pairs if x and not y)
        only_b = sum(1 for x, y in pairs if y and not x)
        acc_a = sum(x for x, _ in pairs) / n if n else 0.0
        acc_b = sum(y for _, y in pairs) / n if n else 0.0
        p = mcnemar_exact(only_a, only_b)
        ci = bootstrap_diff_ci(pairs, seed=0)
        diff = round(acc_b - acc_a, 4)
        if n < MIN_PAIRED:
            verdict, significant = f"campione troppo piccolo ({n} < {MIN_PAIRED} elementi in comune): nessuna conclusione", False
        elif p < ALPHA and diff > 0:
            verdict, significant = f"B migliore di A: dimostrato (McNemar p={p:.2g}, differenza {diff:+.1%})", True
        elif p < ALPHA and diff < 0:
            verdict, significant = f"B peggiore di A: dimostrato (McNemar p={p:.2g}, differenza {diff:+.1%})", True
        else:
            verdict, significant = f"nessuna differenza dimostrata (McNemar p={p:.2g}, differenza {diff:+.1%})", False
        lat = lambda rows: round(sum(rows[i]["latency_ms"] for i in common) / n, 2) if n else None  # noqa: E731
        return {**base, "comparable": True, "dataset": a["config"]["dataset"], "paired_items": n,
                "accuracy_a": round(acc_a, 4), "accuracy_b": round(acc_b, 4), "accuracy_diff": diff,
                "only_a_correct": only_a, "only_b_correct": only_b, "mcnemar_p": p, "diff_ci95": ci,
                "mean_latency_ms_a": lat(ra), "mean_latency_ms_b": lat(rb),
                "significant": significant, "verdict": verdict}

    # -- reading ---------------------------------------------------------------------

    def resolve(self, ref: str) -> str:
        if not isinstance(ref, str) or not re.fullmatch(r"[0-9a-f]{4,32}", ref):
            raise GenesisError("id di esperimento non valido (almeno 4 caratteri esadecimali)")
        rows = self.db.conn.execute("SELECT id FROM experiments WHERE id LIKE ? LIMIT 2", (ref + "%",)).fetchall()
        if len(rows) != 1:
            raise GenesisError(f"esperimento {'inesistente' if not rows else 'ambiguo'}: {ref}")
        return rows[0]["id"]

    def get(self, ref: str) -> dict[str, Any]:
        row = self.db.conn.execute("SELECT * FROM experiments WHERE id = ?", (self.resolve(ref),)).fetchone()
        exp = dict(row)
        for key in JSON_FIELDS:
            exp[key] = json.loads(exp[key]) if exp[key] else None
        exp["deterministic"] = bool(exp["deterministic"])
        return exp

    def results(self, ref: str) -> list[dict[str, Any]]:
        rows = self.db.conn.execute("SELECT * FROM experiment_results WHERE experiment_id = ? ORDER BY item_idx",
                                    (self.resolve(ref),)).fetchall()
        return [{**dict(r), "expected": json.loads(r["expected"]), "correct": bool(r["correct"])} for r in rows]

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.db.conn.execute("SELECT id FROM experiments ORDER BY created_at DESC, rowid DESC LIMIT ?",
                                    (limit,)).fetchall()
        out = []
        for r in rows:
            e = self.get(r["id"])
            out.append({k: e[k] for k in ("id", "name", "subject", "subject_version", "status", "created_at",
                                          "seed", "deterministic", "reproduced_from", "baseline_id")}
                       | {"dataset": e["config"]["dataset"], "metrics": e["metrics"], "evaluation": e["evaluation"]})
        return out

    # -- reports -----------------------------------------------------------------------

    def report(self, ref: str, compare_with: str | None = None) -> Path:
        e = self.get(ref)
        m, res = e["metrics"] or {}, e["resources"] or {}
        env, cfg = e["environment"], e["config"]
        lines = [
            f"# Esperimento {e['id'][:8]} — {e['name']}", "",
            "| Campo | Valore |", "|---|---|",
            f"| Identificatore | `{e['id']}` |",
            f"| Obiettivo | {e['objective'] or '—'} |",
            f"| Ipotesi | {e['hypothesis'] or '—'} |",
            f"| Dati | `{cfg['dataset']}` (sha256 `{e['dataset_hash'][:16]}…`), {m.get('n', 0)} elementi |",
            f"| Modello e versione | `{e['subject']}` → `{e['subject_version']}` |",
            f"| Configurazione | seed {cfg['seed']}, campione {cfg['sample'] or 'tutto'}, remoto "
            f"{'sì' if cfg['allow_remote'] else 'no'} (hash `{e['config_hash'][:12]}`) |",
            f"| Risultato | accuratezza {m.get('correct', 0)}/{m.get('n', 0)} ({m.get('accuracy', 0):.1%}) |",
            f"| Tempo | {res.get('wall_s', '—')} s reali, {res.get('cpu_s', '—')} s CPU; latenza media "
            f"{m.get('latency_ms_mean', '—')} ms, p95 {m.get('latency_ms_p95', '—')} ms |",
            f"| Risorse | RAM processo {res.get('rss_mb_before', '—')} → {res.get('rss_mb_after', '—')} MB "
            f"(picco del processo {res.get('peak_rss_mb_process', '—')} MB); chiamate remote max {res.get('remote_calls_max', 0)} |",
            f"| Errori | {len(e['errors'] or [])} |",
            f"| Valutazione | {e['evaluation'] or '—'} |",
            f"| Riproducibilità | {'deterministico' if e['deterministic'] else 'non deterministico'}; GÉNESIS "
            f"{env['genesis']}, Python {env['python']}, {env['os']}; profilo {env['profile']}"
            + (f"; riproduzione di `{e['reproduced_from'][:8]}`" if e["reproduced_from"] else "") + " |",
            "", f"Stato: {e['status']} · creato {e['created_at']} · concluso {e['finished_at']}", "",
            "## Risultati per elemento", "", "| # | Input | Atteso | Output | Esito | ms |", "|---|---|---|---|---|---|",
        ]
        for r in self.results(e["id"])[:100]:
            out = (r["output"] or r["error"] or "").replace("|", "\\|").replace("\n", " ")[:80]
            lines.append(f"| {r['item_idx']} | {r['input'][:60].replace('|', '/')} | {r['expected']} | {out} | "
                         f"{'✓' if r['correct'] else '✗'} | {r['latency_ms']} |")
        if compare_with:
            c = self.compare(compare_with, e["id"])
            lines += ["", f"## Confronto con `{c['a'][:8]}` ({c['a_subject']})", "", f"**{c['verdict']}**", ""]
            if c["comparable"]:
                lines += [f"- elementi appaiati: {c['paired_items']}",
                          f"- accuratezza A {c['accuracy_a']:.1%} · B {c['accuracy_b']:.1%}",
                          f"- solo A corretto: {c['only_a_correct']} · solo B corretto: {c['only_b_correct']}",
                          f"- McNemar esatto p = {c['mcnemar_p']:.3g}; IC 95% bootstrap della differenza {c['diff_ci95']}"]
        folder = self.app.config.reports_dir
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"esperimento-{e['id'][:8]}-{file_stamp()}.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def _environment(self) -> dict[str, Any]:
        return {"genesis": __version__, "python": platform.python_version(),
                "os": f"{platform.system()} {platform.release()}", "profile": self.app.profile.name,
                "engines": [{"id": e["id"], "version": e["version"], "usable": e["usable"]}
                            for e in self.app.router.describe()],
                "remote_enabled": self.app.config.remote_enabled}


def _metrics(rows: list[tuple[Any, ...]]) -> dict[str, Any]:
    n = len(rows)
    correct = sum(r[5] for r in rows)
    latencies = [r[6] for r in rows]
    return {"n": n, "correct": correct, "accuracy": round(correct / n, 4) if n else 0.0,
            "errors": sum(1 for r in rows if r[8]),
            "latency_ms_mean": round(sum(latencies) / n, 2) if n else None,
            "latency_ms_median": percentile(latencies, 50), "latency_ms_p95": percentile(latencies, 95),
            "engines": dict(Counter(r[7] or "nessuno" for r in rows))}
