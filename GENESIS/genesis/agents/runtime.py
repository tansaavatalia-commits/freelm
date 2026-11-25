"""Agent runtime, deterministic Verifier, Director and Intelligence Council v0.

Every model call goes through the permission layer as the agent's own principal
and then through the router (free/private rules apply). Results are checked by
deterministic rules, never only by the model that produced them. Runs are stored
in ``agent_runs`` with the agent version, steps and checks.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from ..core.clock import Now, utcnow
from ..errors import GenesisError, PermissionDenied
from ..intelligence.base import Request
from ..intelligence.local import LocalEngine, evaluate, extract_expression
from ..intelligence.router import Router
from ..memory.db import Database
from ..security.permissions import Level, PermissionManager
from ..security.redact import redact
from ..tools.registry import ToolRegistry, untrusted_block
from .catalog import AgentConfig

MAX_OUTPUT = 20_000
MAX_SUBTASKS = 6
ASSIGN = {"math": "analyst", "text.stats": "analyst", "code": "developer", "reasoning": "analyst", "chat": "researcher"}
_NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?")


def verify(task_type: str, goal: str, output: str) -> list[dict[str, Any]]:
    checks = [
        {"check": "risposta non vuota", "ok": bool(output.strip())},
        {"check": "nessun segreto nel testo", "ok": redact(output) == output},
        {"check": "lunghezza entro il limite", "ok": len(output) <= MAX_OUTPUT},
    ]
    if task_type == "math":
        try:
            expected = evaluate(extract_expression(goal))
            found = _numbers(output)
            ok = bool(found) and abs(found[-1] - float(expected)) <= 1e-9 * max(1.0, abs(float(expected)))
            checks.append({"check": "calcolo ricontrollato dal motore locale", "ok": ok, "expected": str(expected)})
        except Exception:  # noqa: BLE001 - not recomputable: say so instead of guessing
            checks.append({"check": "calcolo ricontrollato dal motore locale", "ok": None, "detail": "non ricalcolabile"})
    return checks


def _numbers(text: str) -> list[float]:
    return [float(n.replace(",", ".")) for n in _NUMBER.findall(text)]


def decompose(goal: str) -> list[str]:
    """Rule-based decomposition: numbered/bulleted lines, else ';' or ' poi ', else the goal itself."""
    lines = [re.sub(r"^\s*(\d+[.)]|[-*•])\s*", "", ln).strip() for ln in goal.splitlines()]
    parts = [ln for ln in lines if ln]
    if len(parts) <= 1:
        parts = [p.strip() for p in re.split(r";|\bpoi\b", goal) if p.strip()]
    return parts[:MAX_SUBTASKS] or [goal.strip()]


def _similarity(a: str, b: str) -> float:
    wa, wb = set(re.findall(r"\w+", a.lower())), set(re.findall(r"\w+", b.lower()))
    return len(wa & wb) / len(wa | wb) if wa | wb else 1.0


class AgentRunner:
    def __init__(self, db: Database, permissions: PermissionManager, router: Router,
                 agents: dict[str, AgentConfig], now: Now = utcnow, tools: ToolRegistry | None = None) -> None:
        self.db, self.permissions, self.router, self.agents, self._now = db, permissions, router, agents, now
        self.tools = tools

    def get(self, agent_id: str) -> AgentConfig:
        if agent_id not in self.agents:
            raise GenesisError(f"agente sconosciuto: {agent_id}")
        return self.agents[agent_id]

    def describe(self) -> list[dict[str, Any]]:
        return [{"id": a.id, "name": a.name, "version": a.version, "role": a.role, "objective": a.objective,
                 "task_types": list(a.task_types), "success_criteria": a.success_criteria, "builtin": a.builtin,
                 "level": self.permissions.grant_of(a.principal), "tools": list(a.tools)} for a in self.agents.values()]

    # -- single agent -------------------------------------------------------------

    def step(self, agent: AgentConfig, goal: str, private: bool = False, task_type: str | None = None) -> dict[str, Any]:
        """One model call by one agent, plus deterministic checks. Never raises for engine failures."""
        task_type = task_type or self.router.classify(goal)
        if task_type not in agent.task_types:
            return {"agent": agent.id, "task_type": task_type, "ok": False,
                    "error": f"{agent.name} non gestisce '{task_type}' (gestisce: {', '.join(agent.task_types)})"}
        self.permissions.require(agent.principal, "intelligence.ask", Level.READ, details={"task_type": task_type})
        deterministic = task_type in LocalEngine.spec.capabilities
        prompt = goal if deterministic else f"{agent.instructions}\n\nRichiesta: {goal}"
        try:
            result = self.router.route(Request(prompt, task_type, private))
        except GenesisError as exc:
            return {"agent": agent.id, "task_type": task_type, "ok": False, "error": str(exc)}
        checks = verify(task_type, goal, result["output"])
        return {"agent": agent.id, "task_type": task_type, "ok": all(c["ok"] is not False for c in checks),
                "engine": result["engine"], "verified": result["verified"], "output": result["output"],
                "checks": checks}

    def run(self, agent_id: str, goal: str, private: bool = False) -> dict[str, Any]:
        agent = self.get(agent_id)
        run_id = self._start(agent, "agent", goal)
        step = self.step(agent, goal, private)
        return self._finish(run_id, [step], step.get("output") or step.get("error", ""), step["ok"])

    # -- tools --------------------------------------------------------------------

    def use_tool(self, agent_id: str, tool: str, params: dict[str, Any] | None = None,
                 approval_id: str | None = None) -> dict[str, Any]:
        """An agent may use only the tools on its allowlist, and only within its own permission level."""
        agent = self.get(agent_id)
        if self.tools is None or tool not in agent.tools:
            raise PermissionDenied(f"{agent.name} non è autorizzato allo strumento {tool}")
        return self.tools.call(agent.principal, tool, params or {}, approval_id=approval_id)

    def research(self, url: str, question: str, private: bool = False) -> dict[str, Any]:
        """Researcher reads a web page (untrusted data) and answers a question about it."""
        researcher = self.get("researcher")
        run_id = self._start(researcher, "agent", f"{question} [{url}]")
        try:
            page = self.use_tool("researcher", "web.fetch", {"url": url})
        except GenesisError as exc:
            return self._finish(run_id, [{"agent": "researcher", "ok": False, "error": str(exc)}], str(exc), False)
        goal = f"{question}\n\n{untrusted_block(page['result']['text'], url)}"
        step = self.step(researcher, goal, private, task_type="chat")
        return self._finish(run_id, [step], step.get("output") or step.get("error", ""), step["ok"])

    # -- Director -----------------------------------------------------------------

    def direct(self, goal: str, private: bool = False) -> dict[str, Any]:
        director = self.get("director")
        self.permissions.require(director.principal, "agents.delegate", Level.READ)
        run_id = self._start(director, "director", goal)
        steps = []
        for sub in decompose(goal):
            step = self.step(self.get(ASSIGN[self.router.classify(sub)]), sub, private)
            steps.append({"subtask": sub, **step})
        report = "\n".join(
            f"{i}. {s['subtask']} -> {s['agent']}: " + (s["output"] if s["ok"] else f"NON RIUSCITO ({s['error'] if 'error' in s else 'controlli falliti'})")
            for i, s in enumerate(steps, 1))
        return self._finish(run_id, steps, report, all(s["ok"] for s in steps))

    # -- Intelligence Council v0 --------------------------------------------------------

    def council(self, question: str, members: list[str] | None = None, private: bool = False) -> dict[str, Any]:
        """Ask several specialists, compare, detect contradictions, consolidate, measure agreement.

        v0 honesty: specialists differ by instructions; they may run on the same model.
        """
        ids = members or ["researcher", "analyst", "manager"]
        if not 2 <= len(ids) <= 5:
            raise GenesisError("il consiglio richiede da 2 a 5 membri")
        run_id = self._start(self.get("director"), "council", question)
        steps = [self.step(self.get(i), question, private) for i in ids]
        answers = [s for s in steps if s["ok"]]
        outcome: dict[str, Any] = {"members": ids, "answered": len(answers)}
        if not answers:
            outcome.update(consensus=None, agreement=None, contradictions=[], output="nessun membro ha risposto")
        else:
            numbers = [_numbers(s["output"])[-1:] for s in answers]
            if all(numbers):
                values = {n[0] for n in numbers}
                outcome["contradictions"] = [] if len(values) == 1 else [f"valori diversi: {sorted(values)}"]
                outcome["agreement"] = round(max(sum(n[0] == v for n in numbers) for v in values) / len(answers), 2)
            else:
                outcome["contradictions"] = []
                pairs = [(a, b) for i, a in enumerate(answers) for b in answers[i + 1:]]
                outcome["agreement"] = round(sum(_similarity(a["output"], b["output"]) for a, b in pairs) / len(pairs), 2) if pairs else 1.0
            best = max(answers, key=lambda s: sum(_similarity(s["output"], o["output"]) for o in answers))
            outcome.update(consensus=best["agent"], output=best["output"])
        result = self._finish(run_id, steps, outcome["output"], bool(answers) and not outcome["contradictions"])
        result["council"] = outcome
        return result

    # -- persistence --------------------------------------------------------------

    def _start(self, agent: AgentConfig, mode: str, goal: str) -> str:
        run_id = uuid.uuid4().hex
        with self.db.transaction() as c:
            c.execute("INSERT INTO agent_runs (id, agent_id, agent_version, mode, goal, status, created_at) "
                      "VALUES (?, ?, ?, ?, ?, 'running', ?)", (run_id, agent.id, agent.version, mode, goal, self._now()))
        return run_id

    def _finish(self, run_id: str, steps: list[dict[str, Any]], output: str, ok: bool) -> dict[str, Any]:
        with self.db.transaction() as c:
            c.execute("UPDATE agent_runs SET status = ?, steps = ?, output = ?, finished_at = ? WHERE id = ?",
                      ("succeeded" if ok else "failed", json.dumps(steps, ensure_ascii=False, default=str),
                       redact(output), self._now(), run_id))
        return {"run_id": run_id, "ok": ok, "output": redact(output), "steps": steps}

    def runs(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.db.conn.execute("SELECT * FROM agent_runs ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,))
        return [{**dict(r), "steps": json.loads(r["steps"] or "[]")} for r in rows]
