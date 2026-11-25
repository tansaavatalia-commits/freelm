"""Self-improvement cycle: detect -> evidence -> cause -> proposal -> isolated tests -> comparison ->
owner decision -> record. Promotion requires (1) at least one benchmark with a statistically
demonstrated improvement, (2) no benchmark with a demonstrated regression, (3) an explicit,
single-use owner approval (level 4). Protected areas (permissions, security, costs, access
control, the cycle itself) cannot be targeted. Every step is recorded and audited.
"""

from __future__ import annotations

import json
import uuid
from collections import Counter
from typing import TYPE_CHECKING, Any, Callable

from ..core.clock import Now, utcnow
from ..errors import GenesisError, PermissionDenied
from ..security.permissions import OWNER, Level
from .components import COMPONENTS, PROTECTED, ComponentSpec

if TYPE_CHECKING:
    from ..app import Genesis

STATUSES = ("proposed", "evaluated", "promoted", "rejected", "rolled_back")


class ImprovementLab:
    def __init__(self, app: Genesis, now: Now = utcnow) -> None:
        self.app, self.db, self._now = app, app.db, now

    # -- components ---------------------------------------------------------------------

    def spec(self, component: str) -> ComponentSpec:
        if component in PROTECTED:
            raise PermissionDenied(f"'{component}' è un'area protetta: politiche di sicurezza, permessi, limiti di costo "
                                   "e controlli di accesso non possono essere modificati dal ciclo di miglioramento")
        if component not in COMPONENTS:
            raise GenesisError(f"componente sconosciuto: {component} (migliorabili: {', '.join(COMPONENTS)})")
        return COMPONENTS[component]

    def active(self, component: str) -> str:
        row = self.db.conn.execute("SELECT active FROM component_versions WHERE component = ?", (component,)).fetchone()
        return row["active"] if row else COMPONENTS[component].default

    def active_fn(self, component: str) -> Callable[[str], str]:
        return COMPONENTS[component].versions[self.active(component)]

    def components(self) -> list[dict[str, Any]]:
        out = []
        for spec in COMPONENTS.values():
            row = self.db.conn.execute("SELECT * FROM component_versions WHERE component = ?", (spec.name,)).fetchone()
            out.append({"name": spec.name, "description": spec.description, "active": self.active(spec.name),
                        "previous": row["previous"] if row else None, "versions": sorted(spec.versions),
                        "benchmarks": list(spec.benchmarks), "updated_at": row["updated_at"] if row else None})
        return out

    # -- cycle --------------------------------------------------------------------------

    def detect(self, component: str, principal: str = OWNER) -> dict[str, Any]:
        """Measure the active version on its benchmarks and collect the errors as evidence."""
        spec = self.spec(component)
        self.app.permissions.require(principal, f"improve.detect:{component}", Level.EXECUTE)
        version = self.active(component)
        experiments, failures = [], []
        for bench in spec.benchmarks:
            exp = self.app.lab.run(dataset=bench, subject=spec.subjects[version],
                                   name=f"rilevamento {component}@{version} su {bench}",
                                   objective=f"trovare gli errori di {component}@{version}")
            experiments.append({"dataset": exp["config"]["dataset"], "id": exp["id"], "metrics": exp["metrics"]})
            failures += [{"dataset": bench, "input": r["input"], "expected": r["expected"], "got": r["output"] or r["error"]}
                         for r in self.app.lab.results(exp["id"]) if not r["correct"]]
        patterns = Counter(f"atteso {f['expected']} → ottenuto {f['got']}" for f in failures)
        return {"component": component, "version": version, "experiments": experiments,
                "errors": len(failures), "failures": failures[:50],
                "patterns": [{"pattern": p, "count": c} for p, c in patterns.most_common(10)]}

    def propose(self, component: str, candidate: str, principal: str = OWNER, cause: str = "",
                proposal: str = "") -> dict[str, Any]:
        spec = self.spec(component)
        stable = self.active(component)
        if candidate not in spec.versions:
            raise GenesisError(f"versione candidata sconosciuta: {candidate} (disponibili: {', '.join(spec.versions)})")
        if candidate == stable:
            raise GenesisError(f"{candidate} è già la versione attiva")
        evidence = self.detect(component, principal)
        problem = (f"{component}@{stable}: {evidence['errors']} errori sui benchmark "
                   + ", ".join(f"{e['dataset']} {e['metrics']['correct']}/{e['metrics']['n']}" for e in evidence["experiments"]))
        cause = cause or ("schemi di errore più frequenti: "
                          + "; ".join(f"{p['pattern']} ({p['count']})" for p in evidence["patterns"][:5]) or "nessun errore")
        proposal = proposal or f"sostituire {component}@{stable} con {component}@{candidate}"
        imp_id, ts = uuid.uuid4().hex, self._now()
        with self.db.transaction() as c:
            c.execute("INSERT INTO improvements (id, component, stable, candidate, problem, evidence, cause, proposal, "
                      "status, proposed_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'proposed', ?, ?, ?)",
                      (imp_id, component, stable, candidate, problem, json.dumps(evidence, ensure_ascii=False),
                       cause, proposal, principal, ts, ts))
        self.app.audit.record(principal, "improve.propose", "ok", Level.EXECUTE, {"id": imp_id, "component": component,
                                                                                  "candidate": candidate})
        return self.get(imp_id)

    def evaluate(self, imp_id: str, principal: str = OWNER) -> dict[str, Any]:
        """Isolated tests: stable and candidate on every benchmark (pure functions, no state change), compared."""
        imp = self.get(imp_id)
        if imp["status"] != "proposed":
            raise GenesisError(f"si valuta solo una proposta in stato 'proposed' (stato attuale: {imp['status']})")
        spec = self.spec(imp["component"])
        self.app.permissions.require(principal, f"improve.evaluate:{spec.name}", Level.EXECUTE)
        results, improved, regressed = [], [], []
        for bench in spec.benchmarks:
            a = self.app.lab.run(dataset=bench, subject=spec.subjects[imp["stable"]], name=f"stabile {spec.name}@{imp['stable']}")
            b = self.app.lab.run(dataset=bench, subject=spec.subjects[imp["candidate"]], name=f"candidata {spec.name}@{imp['candidate']}",
                                 baseline_id=a["id"], hypothesis=f"{imp['candidate']} migliore di {imp['stable']}")
            cmp = self.app.lab.compare(a["id"], b["id"])
            results.append({"dataset": cmp.get("dataset", bench), "stable_experiment": a["id"], "candidate_experiment": b["id"],
                            "accuracy_stable": cmp.get("accuracy_a"), "accuracy_candidate": cmp.get("accuracy_b"),
                            "p": cmp.get("mcnemar_p"), "verdict": cmp["verdict"]})
            if cmp.get("significant") and cmp["accuracy_diff"] > 0:
                improved.append(bench)
            elif cmp.get("significant") and cmp["accuracy_diff"] < 0:
                regressed.append(bench)
        if regressed:
            recommendation = f"non promuovere: peggioramento dimostrato su {', '.join(regressed)}"
        elif improved:
            recommendation = f"promuovere: miglioramento dimostrato su {', '.join(improved)}, nessun peggioramento dimostrato"
        else:
            recommendation = "non promuovere: nessun miglioramento dimostrato"
        caveat = ("Attenzione: tutti i benchmark sono interni (scritti con GÉNESIS); per una prova indipendente "
                  "importare un dataset del proprietario e aggiungerlo ai benchmark.")
        evaluation = {"results": results, "improved": improved, "regressed": regressed,
                      "recommendation": recommendation, "promotable": bool(improved) and not regressed, "caveat": caveat}
        self._update(imp_id, status="evaluated", evaluation=json.dumps(evaluation, ensure_ascii=False))
        self.app.audit.record(principal, "improve.evaluate", "ok", Level.EXECUTE, {"id": imp_id, "promotable": evaluation["promotable"]})
        return self.get(imp_id)

    def approve(self, imp_id: str, approval_id: str | None) -> dict[str, Any]:
        """Owner decision (level 4, single-use approval). Only evidence-backed proposals can be promoted."""
        imp = self.get(imp_id)
        if imp["status"] != "evaluated" or not (imp["evaluation"] or {}).get("promotable"):
            raise GenesisError("promozione rifiutata: la proposta non è valutata o le prove non bastano")
        spec = self.spec(imp["component"])
        self.app.permissions.require(OWNER, f"improve.promote:{spec.name}", Level.SYSTEM_CHANGE, approval_id=approval_id,
                                     details={"id": imp_id, "candidate": imp["candidate"]})
        self._set_active(spec.name, imp["candidate"], imp["stable"], imp_id)
        self._update(imp_id, status="promoted", decision=f"promossa dal proprietario ({approval_id})", approval_id=approval_id)
        self.app.audit.record(OWNER, "improve.promote", "ok", Level.SYSTEM_CHANGE,
                              {"id": imp_id, "component": spec.name, "from": imp["stable"], "to": imp["candidate"]})
        return self.get(imp_id)

    def reject(self, imp_id: str, reason: str) -> dict[str, Any]:
        imp = self.get(imp_id)
        if imp["status"] not in ("proposed", "evaluated"):
            raise GenesisError(f"impossibile rifiutare una proposta in stato '{imp['status']}'")
        self._update(imp_id, status="rejected", decision=f"rifiutata dal proprietario: {reason or 'nessun motivo'}")
        self.app.audit.record(OWNER, "improve.reject", "ok", None, {"id": imp_id})
        return self.get(imp_id)

    def rollback(self, component: str, approval_id: str | None) -> dict[str, Any]:
        spec = self.spec(component)
        row = self.db.conn.execute("SELECT * FROM component_versions WHERE component = ?", (component,)).fetchone()
        if row is None or not row["previous"]:
            raise GenesisError(f"nessuna versione precedente per {component}")
        self.app.permissions.require(OWNER, f"improve.rollback:{component}", Level.SYSTEM_CHANGE, approval_id=approval_id)
        current, previous = row["active"], row["previous"]
        self._set_active(spec.name, previous, current, row["improvement_id"])
        if row["improvement_id"]:
            self._update(row["improvement_id"], status="rolled_back", decision=f"annullata: tornati a {previous}")
        self.app.audit.record(OWNER, "improve.rollback", "ok", Level.SYSTEM_CHANGE, {"component": component, "to": previous})
        return {"component": component, "active": previous, "previous": current}

    # -- storage ------------------------------------------------------------------------

    def _set_active(self, component: str, active: str, previous: str, imp_id: str | None) -> None:
        with self.db.transaction() as c:
            c.execute("INSERT INTO component_versions (component, active, previous, improvement_id, updated_at, updated_by) "
                      "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(component) DO UPDATE SET active = excluded.active, "
                      "previous = excluded.previous, improvement_id = excluded.improvement_id, "
                      "updated_at = excluded.updated_at, updated_by = excluded.updated_by",
                      (component, active, previous, imp_id, self._now(), OWNER))

    def _update(self, imp_id: str, **fields: Any) -> None:
        sets = ", ".join(f"{k} = ?" for k in fields)
        with self.db.transaction() as c:
            c.execute(f"UPDATE improvements SET {sets}, updated_at = ? WHERE id = ?", (*fields.values(), self._now(), imp_id))

    def resolve(self, ref: str) -> str:
        if not isinstance(ref, str) or not ref or any(ch not in "0123456789abcdef" for ch in ref) or len(ref) < 4:
            raise GenesisError("id di proposta non valido")
        rows = self.db.conn.execute("SELECT id FROM improvements WHERE id LIKE ? LIMIT 2", (ref + "%",)).fetchall()
        if len(rows) != 1:
            raise GenesisError(f"proposta {'inesistente' if not rows else 'ambigua'}: {ref}")
        return rows[0]["id"]

    def get(self, ref: str) -> dict[str, Any]:
        row = dict(self.db.conn.execute("SELECT * FROM improvements WHERE id = ?", (self.resolve(ref),)).fetchone())
        for key in ("evidence", "evaluation"):
            row[key] = json.loads(row[key]) if row[key] else None
        return row

    def list(self, limit: int = 30) -> list[dict[str, Any]]:
        rows = self.db.conn.execute("SELECT id FROM improvements ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,))
        return [self.get(r["id"]) for r in rows.fetchall()]
