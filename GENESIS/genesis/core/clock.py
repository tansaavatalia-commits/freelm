"""Wall-clock helpers. Components take ``now`` as a parameter so tests can inject time."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

Now = Callable[[], str]


def utcnow() -> str:
    """Current UTC time as ISO-8601 with microseconds (sorts chronologically as text)."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def file_stamp() -> str:
    """Current UTC time for file names (no ':' so it is valid on Windows)."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
