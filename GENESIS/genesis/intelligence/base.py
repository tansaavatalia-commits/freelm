"""Contract every engine/provider implements. The router depends only on this, never on a vendor API."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

TASK_TYPES = ("chat", "code", "reasoning", "math", "text.stats")


@dataclass(frozen=True)
class Request:
    prompt: str
    task_type: str | None = None  # None: classified automatically
    private: bool = False  # True: the request never leaves this computer


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    name: str
    version: str
    kind: str  # "local" | "remote"
    capabilities: frozenset[str]
    cost: str  # "free" | "paid" | "unknown"
    quality: int  # 1-5, declared; to be measured by the Research Lab (Phase 6)
    method: str  # "deterministico" (algorithm written in GÉNESIS) | "modello esterno"
    requirements: str = ""


class EngineError(Exception):
    """This engine could not handle the request; the router tries the next one."""


class Provider(ABC):
    spec: ProviderSpec

    def status(self) -> tuple[bool, str]:
        return True, "pronto"

    @abstractmethod
    def run(self, request: Request, task_type: str) -> str: ...
