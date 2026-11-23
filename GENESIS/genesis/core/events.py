"""In-process publish/subscribe event bus.

Handlers run synchronously on the publisher's thread. A failing handler is
logged and never affects the publisher or the other handlers. Patterns use
shell-style wildcards: ``"task.*"``, ``"*"``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from fnmatch import fnmatchcase
from types import MappingProxyType
from typing import Any, Callable, Mapping

from .clock import Now, utcnow

MAX_DEPTH = 16  # nested publishes (a handler publishing) beyond this are dropped


@dataclass(frozen=True)
class Event:
    topic: str
    data: Mapping[str, Any]
    ts: str
    source: str


Handler = Callable[[Event], None]


class EventBus:
    def __init__(self, logger: logging.Logger | None = None, now: Now = utcnow) -> None:
        self._subs: list[tuple[str, Handler]] = []
        self._depth = 0
        self._now = now
        self.log = logger or logging.getLogger("genesis.events")

    def subscribe(self, pattern: str, handler: Handler) -> Callable[[], None]:
        """Register ``handler`` for topics matching ``pattern``; returns an unsubscribe function."""
        entry = (pattern, handler)
        self._subs.append(entry)

        def unsubscribe() -> None:
            if entry in self._subs:
                self._subs.remove(entry)

        return unsubscribe

    def publish(self, topic: str, data: Mapping[str, Any] | None = None, source: str = "core") -> int:
        """Deliver an event; returns how many handlers completed without raising."""
        if self._depth >= MAX_DEPTH:
            self.log.error("event dropped: nesting too deep", extra={"fields": {"topic": topic}})
            return 0
        event = Event(topic, MappingProxyType(dict(data or {})), self._now(), source)
        delivered = 0
        self._depth += 1
        try:
            for pattern, handler in list(self._subs):
                if not fnmatchcase(topic, pattern):
                    continue
                try:
                    handler(event)
                    delivered += 1
                except Exception:
                    self.log.exception("event handler failed", extra={"fields": {"topic": topic}})
        finally:
            self._depth -= 1
        return delivered
