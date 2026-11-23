from __future__ import annotations

import pytest

from genesis.app import Genesis
from genesis.errors import ApprovalRequired, GenesisError, PermissionDenied, TaskError
from genesis.security.permissions import OWNER, Level

from .conftest import LITE_HW, write_config


def test_echo_task_runs_and_stores_result(app):
    task = app.tasks.submit("system.echo", {"x": [1, 2]})
    assert task["status"] == "pending" and task["level"] == 1
    done = app.tasks.run_next()
    assert done["status"] == "succeeded" and done["result"] == {"x": [1, 2]} and done["attempts"] == 1
    assert app.tasks.run_next() is None


def test_invalid_submissions(app):
    with pytest.raises(TaskError):
        app.tasks.submit("does.not.exist")
    with pytest.raises(TaskError):
        app.tasks.submit("system.echo", ["not", "a", "dict"])  # type: ignore[arg-type]
    with pytest.raises(TaskError):
        app.tasks.submit("system.echo", {"x": object()})
    with pytest.raises(TaskError):
        app.tasks.submit("system.echo", max_attempts=0)
    with pytest.raises(TaskError):
        app.tasks.submit("system.echo", project_id="missing-project")


def test_priority_then_fifo(app):
    low = app.tasks.submit("system.echo", {"n": "low"})
    high = app.tasks.submit("system.echo", {"n": "high"}, priority=5)
    second_low = app.tasks.submit("system.echo", {"n": "low2"})
    order = [t["id"] for t in app.tasks.run_pending()]
    assert order == [high["id"], low["id"], second_low["id"]]


def test_retry_then_success_and_final_failure_is_redacted(app):
    calls = []

    def flaky(ctx):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("temporary")
        return "ok"

    app.tasks.register("test.flaky", flaky, Level.READ)
    app.tasks.register("test.broken", lambda ctx: (_ for _ in ()).throw(ValueError("key sk-or-v1-" + "s" * 40)),
                       Level.READ)
    flaky_task = app.tasks.submit("test.flaky", max_attempts=2)
    broken = app.tasks.submit("test.broken")
    app.tasks.run_pending()
    assert app.tasks.get(flaky_task["id"])["status"] == "succeeded"
    assert app.tasks.get(flaky_task["id"])["attempts"] == 2
    failed = app.tasks.get(broken["id"])
    assert failed["status"] == "failed" and "ValueError" in failed["error"] and "s" * 40 not in failed["error"]


def test_cancel_pending_and_running(app):
    pending = app.tasks.submit("system.echo")
    assert app.tasks.cancel(pending["id"]) == "cancelled"

    def long_job(ctx):
        app.tasks.cancel(ctx.task["id"])  # the owner asks to stop while it runs
        ctx.check_cancelled()
        return "should not get here"

    app.tasks.register("test.long", long_job, Level.READ)
    running = app.tasks.submit("test.long")
    app.tasks.run_pending()
    assert app.tasks.get(running["id"])["status"] == "cancelled"
    assert app.tasks.cancel(running["id"]) == "cancelled"  # already final: unchanged


def test_interrupted_tasks_are_recovered_on_restart(home):
    g = Genesis(home, hardware=LITE_HW)
    again = g.tasks.submit("system.echo", {"v": 1}, max_attempts=2)
    exhausted = g.tasks.submit("system.echo", {"v": 2}, max_attempts=1)
    with g.db.transaction() as c:  # simulate a power cut in the middle of both runs
        c.execute("UPDATE tasks SET status = 'running', attempts = 1")
    g.close()
    g = Genesis(home, hardware=LITE_HW)
    try:
        assert g.recovered_tasks == 2
        assert g.tasks.get(again["id"])["status"] == "pending"
        assert g.tasks.get(exhausted["id"])["status"] == "failed"
        assert g.tasks.run_next()["status"] == "succeeded"
    finally:
        g.close()


def test_permissions_apply_to_tasks(home):
    write_config(home, "[permissions.grants]\nhelper = 1\n")
    g = Genesis(home, hardware=LITE_HW)
    try:
        with pytest.raises(PermissionDenied):  # backup is level 2
            g.tasks.submit("memory.backup", principal="helper")
        g.tasks.register("test.install", lambda ctx: "installed", Level.SYSTEM_CHANGE)
        with pytest.raises(ApprovalRequired) as info:
            g.tasks.submit("test.install")
        g.permissions.decide(info.value.approval_id, True, decided_by=OWNER)
        task = g.tasks.submit("test.install", approval_id=info.value.approval_id)
        assert g.tasks.run_next()["status"] == "succeeded" and task["approval_id"] == info.value.approval_id
    finally:
        g.close()


def test_revoked_grant_stops_queued_task(home):
    write_config(home, "[permissions.grants]\nhelper = 2\n")
    g = Genesis(home, hardware=LITE_HW)
    task = g.tasks.submit("memory.backup", principal="helper")
    g.close()
    write_config(home, "[permissions.grants]\nhelper = 0\n")  # the owner lowers the grant
    g = Genesis(home, hardware=LITE_HW)
    try:
        done = g.tasks.run_next()
        assert done["id"] == task["id"] and done["status"] == "failed" and "revocato" in done["error"]
    finally:
        g.close()


def test_missing_handler_fails_cleanly(app):
    app.tasks.register("test.temp", lambda ctx: 1, Level.READ)
    task = app.tasks.submit("test.temp")
    del app.tasks._handlers["test.temp"]  # e.g. a task written by a newer version
    assert app.tasks.run_next()["status"] == "failed"
    assert "nessun gestore" in app.tasks.get(task["id"])["error"]


def test_task_events_are_published(app):
    topics = []
    app.bus.subscribe("task.*", lambda e: topics.append(e.topic))
    app.tasks.submit("system.echo")
    app.tasks.run_next()
    assert topics == ["task.submitted", "task.started", "task.succeeded"]


def test_backup_task_and_builtin_kinds(app):
    kinds = {s.kind for s in app.tasks.kinds()}
    assert {"system.echo", "system.hardware_snapshot", "memory.backup", "memory.integrity_check"} <= kinds
    app.tasks.submit("memory.backup")
    app.tasks.submit("system.hardware_snapshot")
    results = [t["result"] for t in app.tasks.run_pending()]
    assert results[0]["path"].endswith(".db") and len(app.backups()) == 1
    assert "ram_total_mb" in results[1]


def test_projects(app):
    p = app.projects.create("  Ricerca modelli  ", "studio")
    assert p["name"] == "Ricerca modelli" and app.projects.get("ricerca MODELLI")["id"] == p["id"]
    with pytest.raises(GenesisError):
        app.projects.create("RICERCA modelli")
    for bad in ("", "x" * 81, "due\nrighe"):
        with pytest.raises(GenesisError):
            app.projects.create(bad)
    app.projects.archive(p["id"])
    assert app.projects.list() == [] and len(app.projects.list(include_archived=True)) == 1
    with pytest.raises(PermissionDenied):
        app.projects.create("altro", principal="random-agent")
