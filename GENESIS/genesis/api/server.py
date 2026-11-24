"""Local HTTP API and web interface (Phase 2a), standard library only.

Security model
* Listens on 127.0.0.1 only. Requests whose ``Host`` header is not this exact
  address are refused, which blocks DNS-rebinding attacks from web pages.
* Every ``/api`` call needs the installation token (header ``X-Genesis-Token``).
  It lives in the data folder (owner-only file) and is injected into the page
  served from the same origin. Other web sites cannot read it: no CORS headers
  are ever sent, and requests carrying a foreign ``Origin`` are refused.
* The page runs under a strict Content-Security-Policy: no inline scripts, no
  external hosts, no framing.

Threads
HTTP requests are parsed by a small thread pool, but every call into the core
runs on one dedicated thread (an SQLite connection belongs to the thread that
opened it). Tasks run on a separate worker thread with its own connection and
the worker lock, so a long task never blocks the interface.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import re
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

from .. import __version__
from ..app import Genesis
from ..core.worker import TaskWorker
from ..errors import ApprovalRequired, GenesisError, PermissionDenied
from ..hardware.detect import HardwareInfo, memory_now, process_memory_mb
from ..security.permissions import OWNER

DEFAULT_PORT = 8765
MAX_BODY_BYTES = 64 * 1024
TOKEN_FILENAME = "api_token"
TOKEN_PLACEHOLDER = "%GENESIS_TOKEN%"
STATIC_DIR = Path(__file__).with_name("static")
HEX_ID = r"[0-9a-f]{32}"
CONTENT_TYPES = {  # explicit: on Windows `mimetypes` can map .js to text/plain from the registry
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".json": "application/json",
    ".woff2": "font/woff2",
}
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'; object-src 'none'")
FALLBACK_PAGE = """<!doctype html><html lang="it"><meta charset="utf-8"><title>GÉNESIS</title>
<body style="font-family:system-ui;padding:2rem;background:#0b0d12;color:#e7e9ee">
<h1>GÉNESIS</h1><p>L'interfaccia non è stata compilata in questa copia.</p>
<p>L'API funziona: <code>/api/status</code> con l'intestazione <code>X-Genesis-Token</code>.</p>
<p>Per compilare l'interfaccia: <code>cd GENESIS/desktop/frontend &amp;&amp; npm ci &amp;&amp; npm run build</code></p>
</body></html>"""

log = logging.getLogger("genesis.api")


class ApiError(Exception):
    def __init__(self, status: int, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.extra = extra


def load_or_create_token(data_dir: Path) -> str:
    path = data_dir / TOKEN_FILENAME
    try:
        token = path.read_text(encoding="ascii").strip()
        if len(token) >= 32:
            return token
    except (OSError, UnicodeDecodeError):
        pass
    token = secrets.token_urlsafe(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as fh:
        fh.write(token)
    return token


class _Core:
    """The API's own Genesis instance, used only from one dedicated thread."""

    def __init__(self, home: Path | str | None, hardware: HardwareInfo | None) -> None:
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="genesis-core")
        try:
            self.app: Genesis = self._pool.submit(Genesis, home, hardware=hardware).result()
        except BaseException:
            self._pool.shutdown(wait=True)
            raise

    def run(self, fn: Callable[[Genesis], Any]) -> Any:
        return self._pool.submit(fn, self.app).result()

    def close(self) -> None:
        try:
            self._pool.submit(self.app.close).result()
        finally:
            self._pool.shutdown(wait=True)


class _WorkerThread(threading.Thread):
    """Executes queued tasks with its own Genesis instance while the server runs."""

    def __init__(self, home: Path | str | None, hardware: HardwareInfo | None) -> None:
        super().__init__(name="genesis-worker", daemon=True)
        self.home, self.hardware = home, hardware
        self.stop_event, self.wake, self.ready = threading.Event(), threading.Event(), threading.Event()
        self.error: BaseException | None = None
        self.recovered = 0

    def run(self) -> None:
        try:
            app = Genesis(self.home, hardware=self.hardware)
        except BaseException as exc:
            self.error = exc
            self.ready.set()
            return
        try:
            TaskWorker(app).serve(self.stop_event, self.wake, on_ready=self._on_ready)
        except BaseException as exc:  # reported through /api/status (worker_running=false)
            self.error = exc
            app.log.exception("task worker stopped")
        finally:
            app.close()
            self.ready.set()

    def _on_ready(self, recovered: int) -> None:
        self.recovered = recovered
        self.ready.set()


class _HTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    api: ApiServer


class ApiServer:
    def __init__(
        self,
        home: Path | str | None = None,
        *,
        port: int = DEFAULT_PORT,
        hardware: HardwareInfo | None = None,
        static_dir: Path = STATIC_DIR,
    ) -> None:
        self.static_dir = Path(static_dir)
        self.worker = _WorkerThread(home, hardware)
        self.worker.start()
        self.worker.ready.wait(60)
        if self.worker.error is not None:
            raise self.worker.error  # e.g. WorkerBusy: another 'genesis serve' already runs
        try:
            self.core = _Core(home, hardware)
            self.token = load_or_create_token(self.core.app.config.data_dir)
            self.httpd = _HTTPServer(("127.0.0.1", port), _Handler)
        except BaseException:
            self._stop_worker()
            if hasattr(self, "core"):
                self.core.close()
            raise
        self.httpd.api = self
        self.port = int(self.httpd.server_address[1])
        self.allowed_hosts = {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}
        self.allowed_origins = {f"http://{h}" for h in self.allowed_hosts}
        self._routes = self._build_routes()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def serve_forever(self) -> None:
        self.httpd.serve_forever(poll_interval=0.5)

    def start_in_background(self) -> threading.Thread:
        thread = threading.Thread(target=self.serve_forever, name="genesis-http", daemon=True)
        thread.start()
        return thread

    def shutdown(self) -> None:
        """Stop accepting requests, let the running task finish, close everything."""
        self.httpd.shutdown()
        self.httpd.server_close()
        self._stop_worker()
        self.core.close()

    def _stop_worker(self) -> None:
        self.worker.stop_event.set()
        self.worker.wake.set()
        self.worker.join(timeout=300)

    # -- routing ----------------------------------------------------------------

    def _build_routes(self) -> list[tuple[str, re.Pattern[str], Callable[..., tuple[int, Any]]]]:
        table = [
            ("GET", r"/api/status", self._status),
            ("GET", r"/api/doctor", self._doctor),
            ("GET", r"/api/projects", self._projects),
            ("POST", r"/api/projects", self._project_create),
            ("POST", r"/api/projects/(?P<ref>[^/]{1,120})/archive", self._project_archive),
            ("GET", r"/api/task-kinds", self._task_kinds),
            ("GET", r"/api/tasks", self._tasks),
            ("POST", r"/api/tasks", self._task_submit),
            ("GET", rf"/api/tasks/(?P<task_id>{HEX_ID})", self._task_get),
            ("POST", rf"/api/tasks/(?P<task_id>{HEX_ID})/cancel", self._task_cancel),
            ("GET", r"/api/approvals", self._approvals),
            ("POST", rf"/api/approvals/(?P<approval_id>{HEX_ID})/(?P<decision>approve|deny)", self._approval_decide),
            ("GET", r"/api/audit", self._audit),
            ("GET", r"/api/backups", self._backups),
        ]
        return [(m, re.compile(p), fn) for m, p, fn in table]

    def route(self, method: str, path: str, query: dict[str, list[str]], body: dict[str, Any]) -> tuple[int, Any]:
        path_known = False
        for route_method, pattern, fn in self._routes:
            match = pattern.fullmatch(path)
            if not match:
                continue
            path_known = True
            if route_method != method:
                continue
            try:
                return fn(query=query, body=body, **match.groupdict())
            except ApprovalRequired as exc:
                raise ApiError(409, str(exc), approval_id=exc.approval_id) from exc
            except PermissionDenied as exc:
                raise ApiError(403, str(exc)) from exc
            except GenesisError as exc:
                raise ApiError(400, str(exc)) from exc
        if path_known:
            raise ApiError(405, "metodo non ammesso")
        raise ApiError(404, "risorsa inesistente")

    # -- handlers -----------------------------------------------------------------

    def _status(self, **_: Any) -> tuple[int, Any]:
        def collect(g: Genesis) -> dict[str, Any]:
            total, available = memory_now()
            p = g.profile
            return {
                **g.status(),
                "profile_details": {"max_workers": p.max_workers, "max_parallel_online": p.max_parallel_online,
                                    "local_models": p.local_models, "description": p.description},
                "hardware": g.hardware.to_dict(),
                "memory": {"ram_total_mb": total, "ram_available_mb": available,
                           "process_rss_mb": process_memory_mb()},
                "worker_running": self.worker.is_alive(),
                "recovered_at_start": self.worker.recovered,
            }

        return 200, self.core.run(collect)

    def _doctor(self, **_: Any) -> tuple[int, Any]:
        return 200, self.core.run(lambda g: {"version": __version__, "checks": g.doctor(),
                                             "hardware": g.hardware.to_dict(), "profile": g.profile.name,
                                             "profile_reason": g.profile_reason})

    def _projects(self, query: dict[str, list[str]], **_: Any) -> tuple[int, Any]:
        include = _flag(query, "all")
        return 200, self.core.run(lambda g: g.projects.list(include_archived=include))

    def _project_create(self, body: dict[str, Any], **_: Any) -> tuple[int, Any]:
        name = _field(body, "name", str)
        description = _field(body, "description", str, "")
        return 201, self.core.run(lambda g: g.projects.create(name, description, principal=OWNER))

    def _project_archive(self, ref: str, **_: Any) -> tuple[int, Any]:
        return 200, self.core.run(lambda g: g.projects.archive(ref, principal=OWNER))

    def _task_kinds(self, **_: Any) -> tuple[int, Any]:
        return 200, self.core.run(lambda g: [{"kind": s.kind, "level": int(s.level), "description": s.description}
                                             for s in g.tasks.kinds()])

    def _tasks(self, query: dict[str, list[str]], **_: Any) -> tuple[int, Any]:
        status = _param(query, "status")
        limit = _int_param(query, "limit", 50, 1, 500)
        project_ref = _param(query, "project")

        def collect(g: Genesis) -> list[dict[str, Any]]:
            project_id = _project_id(g, project_ref)
            return g.tasks.list(status=status, project_id=project_id, limit=limit)

        return 200, self.core.run(collect)

    def _task_submit(self, body: dict[str, Any], **_: Any) -> tuple[int, Any]:
        kind = _field(body, "kind", str)
        payload = _field(body, "payload", dict, {})
        priority = _field(body, "priority", int, 0)
        attempts = _field(body, "attempts", int, 1)
        approval_id = _field(body, "approval_id", str, None)
        project_ref = _field(body, "project", str, None)

        def submit(g: Genesis) -> dict[str, Any]:
            return g.tasks.submit(kind, payload, principal=OWNER, project_id=_project_id(g, project_ref),
                                  priority=priority, max_attempts=attempts, approval_id=approval_id)

        task = self.core.run(submit)
        self.worker.wake.set()
        return 201, task

    def _task_get(self, task_id: str, **_: Any) -> tuple[int, Any]:
        task = self.core.run(lambda g: g.tasks.get(task_id))
        if task is None:
            raise ApiError(404, f"compito inesistente: {task_id}")
        return 200, task

    def _task_cancel(self, task_id: str, **_: Any) -> tuple[int, Any]:
        return 200, {"outcome": self.core.run(lambda g: g.tasks.cancel(task_id, principal=OWNER))}

    def _approvals(self, query: dict[str, list[str]], **_: Any) -> tuple[int, Any]:
        status = _param(query, "status")
        if status not in (None, "pending", "approved", "denied", "used"):
            raise ApiError(400, f"stato sconosciuto: {status}")
        return 200, self.core.run(lambda g: g.permissions.list_approvals(status))

    def _approval_decide(self, approval_id: str, decision: str, **_: Any) -> tuple[int, Any]:
        approve = decision == "approve"
        self.core.run(lambda g: g.permissions.decide(approval_id, approve, decided_by=OWNER))
        return 200, {"status": "approved" if approve else "denied"}

    def _audit(self, query: dict[str, list[str]], **_: Any) -> tuple[int, Any]:
        n = _int_param(query, "n", 50, 1, 500)

        def collect(g: Genesis) -> dict[str, Any]:
            ok, first_bad = g.audit.verify()
            return {"entries": g.audit.tail(n), "chain_ok": ok, "first_bad_seq": first_bad, "total": g.audit.count()}

        return 200, self.core.run(collect)

    def _backups(self, **_: Any) -> tuple[int, Any]:
        def collect(g: Genesis) -> list[dict[str, Any]]:
            return [{"name": p.name, "size_kb": p.stat().st_size // 1024} for p in reversed(g.backups())]

        return 200, self.core.run(collect)


def _project_id(g: Genesis, ref: str | None) -> str | None:
    if not ref:
        return None
    project = g.projects.get(ref)
    if project is None:
        raise GenesisError(f"progetto inesistente: {ref}")
    return project["id"]


_MISSING = object()


def _field(body: dict[str, Any], key: str, kind: type, default: Any = _MISSING) -> Any:
    if key not in body or body[key] is None:
        if default is _MISSING:
            raise ApiError(400, f"campo obbligatorio mancante: {key}")
        return default
    value = body[key]
    if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
        raise ApiError(400, f"il campo {key} deve essere di tipo {kind.__name__}")
    return value


def _param(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    return values[0] if values and values[0] != "" else None


def _int_param(query: dict[str, list[str]], key: str, default: int, low: int, high: int) -> int:
    raw = _param(query, key)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ApiError(400, f"{key} deve essere un intero") from exc
    return max(low, min(high, value))


def _flag(query: dict[str, list[str]], key: str) -> bool:
    return (_param(query, key) or "").lower() in ("1", "true", "yes")


class _Handler(BaseHTTPRequestHandler):
    server: _HTTPServer
    server_version = "GENESIS"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature
        log.debug("http " + format, *args)

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def _dispatch(self, method: str) -> None:
        api = self.server.api
        try:
            body = self._read_body() if method == "POST" else {}
            self._check_origin(api)
            url = urlsplit(self.path)
            if url.path.startswith("/api/"):
                token = self.headers.get("X-Genesis-Token", "").encode("utf-8", "replace")
                if not hmac.compare_digest(token, api.token.encode("ascii")):
                    raise ApiError(401, "token mancante o non valido")
                status, data = api.route(method, url.path, parse_qs(url.query), body)
                self._send_json(status, data)
            elif method == "GET":
                self._send_static(api, url.path)
            else:
                raise ApiError(405, "metodo non ammesso")
        except ApiError as exc:
            self._send_json(exc.status, {"error": exc.message, **exc.extra})
        except Exception:
            log.exception("unhandled API error")
            self._send_json(500, {"error": "errore interno: dettagli nel log di GÉNESIS"})

    def _read_body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError as exc:
            self.close_connection = True
            raise ApiError(400, "Content-Length non valido") from exc
        if length > MAX_BODY_BYTES:
            self.close_connection = True  # the unread body would corrupt the next request
            raise ApiError(413, "richiesta troppo grande")
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise ApiError(400, "il corpo della richiesta non è JSON valido") from exc
        if not isinstance(data, dict):
            raise ApiError(400, "il corpo della richiesta deve essere un oggetto JSON")
        return data

    def _check_origin(self, api: ApiServer) -> None:
        if self.headers.get("Host", "") not in api.allowed_hosts:
            raise ApiError(403, "host non ammesso: GÉNESIS risponde solo su 127.0.0.1")
        origin = self.headers.get("Origin")
        if origin is not None and origin not in api.allowed_origins:
            raise ApiError(403, "origine non ammessa")

    def _common_headers(self, content_type: str, length: int) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")

    def _send_json(self, status: int, data: Any) -> None:
        payload = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self._common_headers("application/json; charset=utf-8", len(payload))
        self.end_headers()
        self.wfile.write(payload)

    def _send_static(self, api: ApiServer, path: str) -> None:
        root = api.static_dir.resolve()
        relative = "index.html" if path in ("", "/") else path.lstrip("/")
        target = (root / relative).resolve()
        index = root / "index.html"
        if relative == "index.html" and not index.is_file():
            content, content_type = FALLBACK_PAGE.encode("utf-8"), CONTENT_TYPES[".html"]
        elif root not in target.parents or not target.is_file():
            raise ApiError(404, "risorsa inesistente")
        else:
            content = target.read_bytes()
            content_type = CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream")
            if target.name == "index.html":
                content = content.replace(TOKEN_PLACEHOLDER.encode(), api.token.encode("ascii"))
        self.send_response(200)
        self._common_headers(content_type, len(content))
        if content_type.startswith("text/html"):
            self.send_header("Content-Security-Policy", CSP)
        self.end_headers()
        self.wfile.write(content)
