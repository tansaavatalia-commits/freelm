"""Gate results: every business-rule check returns a structured, auditable outcome."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class GateResult:
    rule_id: str  # e.g. "BR-010"
    passed: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "passed": self.passed,
            "message": self.message,
            "details": self.details,
        }


def all_passed(results: list[GateResult]) -> bool:
    return bool(results) and all(r.passed for r in results)


def failures(results: list[GateResult]) -> list[GateResult]:
    return [r for r in results if not r.passed]
