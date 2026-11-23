from __future__ import annotations

import pytest

from genesis.core.events import MAX_DEPTH, EventBus


def test_patterns_and_unsubscribe():
    bus, seen = EventBus(), []
    bus.subscribe("task.started", lambda e: seen.append(("exact", e.topic)))
    off = bus.subscribe("task.*", lambda e: seen.append(("prefix", e.topic)))
    bus.subscribe("*", lambda e: seen.append(("all", e.topic)))
    assert bus.publish("task.started", {"id": 1}) == 3
    off()
    assert bus.publish("task.failed") == 1
    assert seen == [("exact", "task.started"), ("prefix", "task.started"), ("all", "task.started"),
                    ("all", "task.failed")]


def test_failing_handler_is_isolated():
    bus, seen = EventBus(), []
    bus.subscribe("x", lambda e: 1 / 0)
    bus.subscribe("x", lambda e: seen.append(e.data["v"]))
    assert bus.publish("x", {"v": 7}) == 1
    assert seen == [7]


def test_event_data_is_read_only():
    bus, events = EventBus(), []
    bus.subscribe("x", events.append)
    bus.publish("x", {"v": 1})
    with pytest.raises(TypeError):
        events[0].data["v"] = 2  # type: ignore[index]


def test_runaway_recursion_is_cut():
    bus, calls = EventBus(), []

    def again(event):
        calls.append(1)
        bus.publish("loop")

    bus.subscribe("loop", again)
    bus.publish("loop")
    assert len(calls) == MAX_DEPTH
