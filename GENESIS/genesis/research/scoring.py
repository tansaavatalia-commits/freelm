"""Deterministic scorers: the model being tested never grades itself."""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any

SCORERS = ("numeric", "label", "contains", "exact")
_NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?")


def last_number(text: str) -> float | None:
    found = _NUMBER.findall(text)
    return float(found[-1].replace(",", ".")) if found else None


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def score(scorer: str, expected: Any, output: str | None) -> bool:
    if output is None:
        return False
    if scorer == "numeric":
        value = last_number(output)
        return value is not None and math.isclose(value, float(expected), rel_tol=1e-6, abs_tol=1e-9)
    if scorer == "label":
        return output.strip().lower() == str(expected).strip().lower()
    if scorer == "contains":
        options = expected if isinstance(expected, list) else [expected]
        text = _norm(output)
        return any(re.search(rf"(?<!\w){re.escape(_norm(o))}(?!\w)", text) for o in options)
    if scorer == "exact":
        return _norm(output) == _norm(expected)
    raise ValueError(f"scorer sconosciuto: {scorer}")
