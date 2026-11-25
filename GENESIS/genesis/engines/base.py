"""Common contract for GÉNESIS engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from ..errors import GenesisError

KINDS = ("algoritmo", "strumento", "modello esterno")


class EngineOpError(GenesisError):
    """An engine operation could not be carried out."""


@dataclass(frozen=True)
class Component:
    name: str
    kind: str  # one of KINDS
    description: str
    available: bool = True


@dataclass(frozen=True)
class Operation:
    name: str
    level: int
    description: str
    params: str


class GenesisEngine(ABC):
    id: str
    name: str
    version: str
    description: str
    components: tuple[Component, ...]
    operations: tuple[Operation, ...]

    def available(self) -> tuple[bool, str]:
        return True, "pronto"

    def op(self, name: str) -> Operation:
        for o in self.operations:
            if o.name == name:
                return o
        raise EngineOpError(f"{self.name}: operazione sconosciuta '{name}' "
                            f"(disponibili: {', '.join(o.name for o in self.operations)})")

    @abstractmethod
    def run(self, op: str, payload: dict[str, Any], principal: str = "owner") -> Any: ...

    def manifest(self) -> dict[str, Any]:
        ok, reason = self.available()
        return {"id": self.id, "name": self.name, "version": self.version, "description": self.description,
                "available": ok, "reason": reason,
                "uses_external_model": any(c.kind == "modello esterno" and c.available for c in self.components),
                "components": [c.__dict__ for c in self.components],
                "operations": [o.__dict__ for o in self.operations]}


def text_arg(payload: dict[str, Any], key: str = "text", limit: int = 200_000) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EngineOpError(f"serve il campo '{key}' (testo non vuoto)")
    if len(value) > limit:
        raise EngineOpError(f"'{key}' troppo lungo (massimo {limit} caratteri)")
    return value
