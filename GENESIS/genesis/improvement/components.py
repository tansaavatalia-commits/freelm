"""Improvable components and their versions. Only what is listed here can change, and only by
promotion through the improvement cycle. Protected areas are never improvable."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..engines.reasoning import classify_v2, math_v2
from ..intelligence.local import classify as classify_v1
from ..intelligence.local import evaluate, extract_expression, format_number

PROTECTED = frozenset({"permissions", "security", "audit", "cost_policy", "budget", "access_control",
                       "grants", "approvals", "config", "improvement"})


def _math_v1(prompt: str) -> str:
    return format_number(evaluate(extract_expression(prompt)))


def _math_v2(prompt: str) -> str:
    return math_v2(prompt)[0]


@dataclass(frozen=True)
class ComponentSpec:
    name: str
    description: str
    default: str
    versions: dict[str, Callable[[str], str]]
    subjects: dict[str, str]  # version -> Research Lab subject
    benchmarks: tuple[str, ...]


COMPONENTS: dict[str, ComponentSpec] = {
    "classifier": ComponentSpec(
        "classifier", "classificazione delle richieste nel router e negli agenti", "v1",
        {"v1": classify_v1, "v2": classify_v2}, {"v1": "classifier", "v2": "classifier@v2"},
        ("classify-it", "classify-holdout")),
    "math": ComponentSpec(
        "math", "calcolo del motore locale (aritmetica e problemi a parole)", "v1",
        {"v1": _math_v1, "v2": _math_v2}, {"v1": "local.math", "v2": "math@v2"},
        ("math-basic", "math-words")),
}
