"""One task worker per data folder.

Only one process at a time may execute tasks: it holds an exclusive OS file
lock (``data/worker.lock``) for as long as it runs. The operating system
releases the lock automatically if the process dies, so the next worker that
gets it can safely put interrupted tasks back in the queue — no live worker can
still own them. Read-only commands (``status``, the API) never take the lock.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from ..errors import WorkerBusy

if TYPE_CHECKING:
    from ..app import Genesis

LOCK_FILENAME = "worker.lock"


class WorkerLock:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._fd: int | None = None

    @property
    def held(self) -> bool:
        return self._fd is not None

    def acquire(self) -> None:
        if self._fd is not None:
            raise WorkerBusy("questo worker possiede già il lock")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            _lock(fd)
        except OSError as exc:
            os.close(fd)
            raise WorkerBusy(
                "un altro processo sta già eseguendo i compiti (per esempio 'genesis serve'): "
                "i compiti vengono eseguiti lì"
            ) from exc
        self._fd = fd

    def release(self) -> None:
        if self._fd is None:
            return
        try:
            _unlock(self._fd)
        finally:
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> WorkerLock:
        self.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()


def _lock(fd: int) -> None:
    if sys.platform == "win32":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(fd: int) -> None:
    if sys.platform == "win32":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)


class TaskWorker:
    """Runs the queue of one :class:`~genesis.app.Genesis` instance, one task at a time."""

    def __init__(self, app: Genesis, poll_seconds: float = 1.0) -> None:
        self.app = app
        self.lock = app.worker_lock()
        self.poll_seconds = poll_seconds

    def run_once(self, max_tasks: int | None = None) -> tuple[int, list[dict[str, Any]]]:
        """Recover interrupted tasks, run what is queued, release. Returns (recovered, done)."""
        with self.lock:
            recovered = self.app.tasks.recover()
            return recovered, self.app.tasks.run_pending(max_tasks)

    def serve(
        self,
        stop: threading.Event,
        wake: threading.Event,
        on_ready: Callable[[int], None] | None = None,
    ) -> None:
        """Keep running tasks until ``stop`` is set. ``wake`` short-cuts the idle wait."""
        with self.lock:
            recovered = self.app.tasks.recover()
            if on_ready:
                on_ready(recovered)
            while not stop.is_set():
                if self.app.tasks.run_next() is None:
                    wake.wait(self.poll_seconds)
                    wake.clear()
