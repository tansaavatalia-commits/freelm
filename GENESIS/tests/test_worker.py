from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from genesis.core.logs import close_handler, setup_logging
from genesis.core.worker import TaskWorker, WorkerLock
from genesis.errors import WorkerBusy
from genesis.hardware.detect import memory_now, process_memory_mb
from genesis.security.permissions import Level

GENESIS_ROOT = Path(__file__).resolve().parents[1]


def test_lock_is_exclusive_and_released(tmp_path):
    first, second = WorkerLock(tmp_path / "w.lock"), WorkerLock(tmp_path / "w.lock")
    first.acquire()
    with pytest.raises(WorkerBusy):
        second.acquire()
    first.release()
    second.acquire()  # free again
    second.release()


def test_lock_is_freed_when_the_holder_process_dies(tmp_path):
    lock_path = tmp_path / "w.lock"
    script = (
        "import os, sys\n"
        "from genesis.core.worker import WorkerLock\n"
        "WorkerLock(sys.argv[1]).acquire()\n"
        "print('held', flush=True)\n"
        "sys.stdin.readline()\n"
        "os._exit(1)  # crash without releasing\n"
    )
    proc = subprocess.Popen([sys.executable, "-c", script, str(lock_path)], cwd=GENESIS_ROOT,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == "held"
        with pytest.raises(WorkerBusy):
            WorkerLock(lock_path).acquire()
        proc.stdin.write("\n")
        proc.stdin.flush()
        proc.wait(timeout=30)
    finally:
        proc.kill()
    lock = WorkerLock(lock_path)
    lock.acquire()  # the OS released it with the dead process
    lock.release()


def test_serve_loop_runs_tasks_until_stopped(app):
    stop, wake, ready = threading.Event(), threading.Event(), threading.Event()
    app.tasks.register("test.slow", lambda ctx: time.sleep(0.05) or "ok", Level.READ)
    task = app.tasks.submit("test.slow")

    # The serving worker needs its own core (one SQLite connection per thread).
    from genesis.app import Genesis

    from .conftest import LITE_HW

    def run() -> None:
        g = Genesis(app.config.home, hardware=LITE_HW)
        g.tasks.register("test.slow", lambda ctx: time.sleep(0.05) or "ok", Level.READ)
        try:
            TaskWorker(g, poll_seconds=0.05).serve(stop, wake, on_ready=lambda n: ready.set())
        finally:
            g.close()

    thread = threading.Thread(target=run)
    thread.start()
    assert ready.wait(10)
    with pytest.raises(WorkerBusy):  # 'genesis task run' while the server works
        TaskWorker(app).run_once()
    deadline = time.monotonic() + 10
    while app.tasks.get(task["id"])["status"] != "succeeded" and time.monotonic() < deadline:
        time.sleep(0.02)
    stop.set()
    wake.set()
    thread.join(10)
    assert app.tasks.get(task["id"])["status"] == "succeeded" and not thread.is_alive()


def test_restore_is_refused_while_a_worker_runs(app):
    backup = app.create_backup()
    approval = app.permissions.request_approval("owner", "memory.restore", Level.SYSTEM_CHANGE)
    app.permissions.decide(approval, True, decided_by="owner")
    with app.worker_lock():
        with pytest.raises(WorkerBusy):
            app.restore_backup(backup, approval)


def test_shared_log_handler_is_reference_counted(tmp_path):
    logger, first = setup_logging(tmp_path, "INFO", 10_000, 1)
    _, second = setup_logging(tmp_path, "INFO", 10_000, 1)
    assert first is second
    close_handler(first)
    assert first in logger.handlers  # still used by the second core
    close_handler(second)
    assert first not in logger.handlers


def test_live_memory_readings():
    total, available = memory_now()
    rss = process_memory_mb()
    if sys.platform.startswith(("linux", "win")):
        assert total and available and 0 < available <= total
        assert rss and rss > 1
