"""Engine registry: every engine operation passes the permission layer as the caller's principal."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..errors import ToolError
from ..intelligence.base import EngineError
from .base import EngineOpError, GenesisEngine
from .code import CodeEngine
from .data import DataEngine
from .memory import MemoryEngine
from .multimodal import MultimodalEngine
from .reasoning import ReasoningEngine
from .research import ResearchEngine

if TYPE_CHECKING:
    from ..app import Genesis

MAX_FILE = 1_000_000


class EngineRegistry:
    def __init__(self, app: Genesis) -> None:
        self.permissions = app.permissions
        workspace = app.tools.workspace

        def read(path: str) -> str:
            target = workspace.path(path)
            if not target.is_file():
                raise EngineOpError("file inesistente nella cartella di lavoro")
            if target.stat().st_size > MAX_FILE:
                raise EngineOpError("file troppo grande (oltre 1 MB)")
            return target.read_text(encoding="utf-8", errors="replace")

        def fetch(url: str, principal: str) -> dict[str, Any]:
            return app.tools.call(principal, "web.fetch", {"url": url})["result"]

        self.memory = MemoryEngine(app.db, app.permissions, app.projects)
        engines: list[GenesisEngine] = [ReasoningEngine(), CodeEngine(read), ResearchEngine(read, fetch),
                                        DataEngine(read), self.memory, MultimodalEngine(workspace.path)]
        self.engines = {e.id: e for e in engines}

    def describe(self) -> list[dict[str, Any]]:
        return [e.manifest() for e in self.engines.values()]

    def run(self, principal: str, engine_id: str, op: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        engine = self.engines.get(engine_id)
        if engine is None:
            raise EngineOpError(f"motore sconosciuto: {engine_id} (disponibili: {', '.join(self.engines)})")
        operation = engine.op(op)
        ok, reason = engine.available()
        if not ok:
            raise EngineOpError(f"{engine.name} non disponibile: {reason}")
        if not isinstance(payload or {}, dict):
            raise EngineOpError("payload deve essere un oggetto JSON")
        self.permissions.require(principal, f"engine:{engine_id}.{op}", operation.level)
        try:
            result = engine.run(op, payload or {}, principal)
        except (EngineError, ToolError) as exc:
            raise EngineOpError(str(exc)) from exc
        return {"engine": engine_id, "op": op, "version": engine.version,
                "uses_external_model": engine.manifest()["uses_external_model"], "result": result}
