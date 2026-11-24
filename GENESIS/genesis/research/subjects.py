"""Systems under test. Without allow_remote every request is sent as *private*, so the router can
only use local engines: no data leaves the PC and no free quota is consumed."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from .. import __version__
from ..errors import GenesisError
from ..intelligence.base import Request
from ..intelligence.local import LocalEngine, classify
from ..security.redact import redact
from .datasets import Dataset, Item

if TYPE_CHECKING:
    from ..app import Genesis

FIXED = ("classifier", "baseline:majority", "local.math", "router", "council")


@dataclass(frozen=True)
class Subject:
    spec: str
    version: str
    deterministic: bool
    remote_calls_per_item: int
    run: Callable[[Item], dict[str, Any]]


def available(app: Genesis) -> list[str]:
    return list(FIXED) + [f"agent:{a}" for a in app.agents.agents]


def _guard(fn: Callable[[Item], dict[str, Any]]) -> Callable[[Item], dict[str, Any]]:
    def run(item: Item) -> dict[str, Any]:
        try:
            return fn(item)
        except Exception as exc:  # any failure of the system under test is a measured error
            return {"output": None, "engine": None, "error": redact(str(exc))[:500]}
    return run


def make_subject(app: Genesis, spec: str, dataset: Dataset, allow_remote: bool) -> Subject:
    private = not allow_remote
    if spec == "classifier":
        return Subject(spec, f"regole@{__version__}", True, 0,
                       _guard(lambda it: {"output": classify(it.input), "engine": "regole", "error": None}))
    if spec == "baseline:majority":
        label = Counter(str(i.expected) for i in dataset.items).most_common(1)[0][0]
        return Subject(spec, f"maggioranza={label}", True, 0,
                       _guard(lambda it: {"output": label, "engine": "baseline", "error": None}))
    if spec == "local.math":
        engine = LocalEngine()
        return Subject(spec, f"local@{__version__}", True, 0, _guard(
            lambda it: {"output": engine.run(Request(it.input), "math"), "engine": "local", "error": None}))
    if spec == "router":
        def route(it: Item) -> dict[str, Any]:
            r = app.router.route(Request(it.input, it.task_type, private))
            return {"output": r["output"], "engine": r["engine"], "error": None}
        engines = ",".join(f"{p.spec.id}@{p.spec.version}" for p in app.router.providers)
        return Subject(spec, f"router@{__version__}[{engines}]", private, 0 if private else 3, _guard(route))
    if spec == "council":
        def council(it: Item) -> dict[str, Any]:
            r = app.agents.council(it.input, None, private)
            if not r["council"]["answered"]:
                return {"output": None, "engine": None, "error": r["output"]}
            return {"output": r["output"], "engine": "consiglio", "error": None}
        return Subject(spec, f"council@{__version__}", private, 0 if private else 9, _guard(council))
    if spec.startswith("agent:"):
        agent = app.agents.get(spec.split(":", 1)[1])

        def run_agent(it: Item) -> dict[str, Any]:
            r = app.agents.run(agent.id, it.input, private)
            step = r["steps"][0]
            if not r["ok"] and "output" not in step:
                return {"output": None, "engine": None, "error": r["output"]}
            return {"output": step.get("output"), "engine": step.get("engine"), "error": None}
        return Subject(spec, f"{agent.id}@{agent.version}", private, 0 if private else 3, _guard(run_agent))
    raise GenesisError(f"soggetto sconosciuto: {spec} (disponibili: {', '.join(FIXED)}, agent:<id>)")
