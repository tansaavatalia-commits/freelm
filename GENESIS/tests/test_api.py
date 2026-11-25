from __future__ import annotations

import http.client
import json
import time

import pytest

from genesis.api.server import TOKEN_PLACEHOLDER, ApiServer
from genesis.errors import WorkerBusy

from .conftest import LITE_HW


@pytest.fixture
def server(home, tmp_path):
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text(
        f'<!doctype html><meta name="genesis-token" content="{TOKEN_PLACEHOLDER}"><script src="assets/app.js"></script>',
        encoding="utf-8")
    (static / "assets" / "app.js").write_text("console.log('ok')", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("not for the browser", encoding="utf-8")
    srv = ApiServer(home, port=0, hardware=LITE_HW, static_dir=static)
    srv.start_in_background()
    yield srv
    srv.shutdown()


def call(srv, method, path, body=None, *, token=True, host=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=10)
    hdrs = {"Host": host or f"127.0.0.1:{srv.port}", **(headers or {})}
    if token:
        hdrs["X-Genesis-Token"] = srv.token
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    conn.request(method, path, body=data, headers=hdrs)
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    is_json = resp.getheader("Content-Type", "").startswith("application/json")
    return resp.status, (json.loads(raw) if is_json else raw.decode()), resp


def wait_for(srv, task_id, status="succeeded", timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _, task, _ = call(srv, "GET", f"/api/tasks/{task_id}")
        if task["status"] == status:
            return task
        time.sleep(0.05)
    raise AssertionError(f"task {task_id} did not reach {status}: {task}")


def test_security_checks(server):
    assert call(server, "GET", "/api/status", token=False)[0] == 401
    assert call(server, "GET", "/api/status", headers={"X-Genesis-Token": "wrong"}, token=False)[0] == 401
    assert call(server, "GET", "/api/status", host="evil.example:8765")[0] == 403  # DNS rebinding
    assert call(server, "POST", "/api/projects", {"name": "x"}, headers={"Origin": "https://evil.example"})[0] == 403
    status, _, resp = call(server, "GET", "/api/status")
    assert status == 200 and resp.getheader("Access-Control-Allow-Origin") is None
    assert resp.getheader("X-Content-Type-Options") == "nosniff"


def test_index_gets_the_token_and_static_files_are_confined(server):
    status, html, resp = call(server, "GET", "/", token=False)
    assert status == 200 and server.token in html and TOKEN_PLACEHOLDER not in html
    assert "script-src 'self'" in resp.getheader("Content-Security-Policy")
    status, js, resp = call(server, "GET", "/assets/app.js", token=False)
    assert status == 200 and resp.getheader("Content-Type").startswith("text/javascript")
    for path in ("/../secret.txt", "/assets/../../secret.txt", "/%2e%2e/secret.txt", "/missing.js"):
        assert call(server, "GET", path, token=False)[0] == 404


def test_status_doctor_and_memory(server):
    status, data, _ = call(server, "GET", "/api/status")
    assert status == 200 and data["profile"] == "lite-4gb" and data["worker_running"] is True
    assert data["profile_details"]["max_workers"] == 1 and "memory" in data
    status, data, _ = call(server, "GET", "/api/doctor")
    assert status == 200 and any(c["check"] == "Catena di audit" for c in data["checks"])


def test_projects_and_tasks_end_to_end(server):
    status, project, _ = call(server, "POST", "/api/projects", {"name": "Web", "description": "dalla UI"})
    assert status == 201 and project["name"] == "Web"
    assert call(server, "POST", "/api/projects", {"name": "web"})[0] == 400  # duplicate
    status, task, _ = call(server, "POST", "/api/tasks", {"kind": "system.echo", "payload": {"x": 1},
                                                          "project": "Web"})
    assert status == 201 and task["project_id"] == project["id"]
    done = wait_for(server, task["id"])  # executed by the background worker
    assert done["result"] == {"x": 1}
    _, tasks, _ = call(server, "GET", f"/api/tasks?project={project['id']}")
    assert [t["id"] for t in tasks] == [task["id"]]
    _, kinds, _ = call(server, "GET", "/api/task-kinds")
    assert {"kind": "memory.backup", "level": 2, "description": kinds[[k["kind"] for k in kinds].index(
        "memory.backup")]["description"]} in kinds
    status, archived, _ = call(server, "POST", "/api/projects/Web/archive", {})
    assert status == 200 and archived["status"] == "archived"
    _, active, _ = call(server, "GET", "/api/projects")
    _, everything, _ = call(server, "GET", "/api/projects?all=1")
    assert active == [] and len(everything) == 1


def test_backup_task_and_listing(server):
    _, task, _ = call(server, "POST", "/api/tasks", {"kind": "memory.backup"})
    wait_for(server, task["id"])
    status, backups, _ = call(server, "GET", "/api/backups")
    assert status == 200 and len(backups) == 1 and backups[0]["name"].endswith(".db")


def test_validation_errors(server):
    assert call(server, "POST", "/api/tasks", {"kind": "nope"})[0] == 400
    assert call(server, "POST", "/api/tasks", {"kind": "system.echo", "payload": [1]})[0] == 400
    assert call(server, "POST", "/api/tasks", {"kind": "system.echo", "priority": True})[0] == 400
    assert call(server, "POST", "/api/tasks", {})[0] == 400
    assert call(server, "GET", "/api/tasks?status=weird")[0] == 400
    assert call(server, "GET", "/api/tasks/" + "0" * 32)[0] == 404
    assert call(server, "GET", "/api/nothing")[0] == 404
    assert call(server, "POST", "/api/status", {})[0] == 405
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=10)
    conn.request("POST", "/api/projects", body=b"{not json", headers={
        "Host": f"127.0.0.1:{server.port}", "X-Genesis-Token": server.token, "Content-Type": "application/json"})
    assert conn.getresponse().status == 400
    conn.close()
    big = {"name": "x" * (70 * 1024)}
    assert call(server, "POST", "/api/projects", big)[0] == 413


def test_cancel_and_approvals(server):
    _, task, _ = call(server, "POST", "/api/tasks", {"kind": "system.echo"})
    wait_for(server, task["id"])
    assert call(server, "POST", f"/api/tasks/{task['id']}/cancel", {})[2].status == 200
    _, empty, _ = call(server, "GET", "/api/approvals?status=pending")
    assert empty == []
    approval = server.core.run(lambda g: g.permissions.request_approval("owner", "system.install", 4))
    _, pending, _ = call(server, "GET", "/api/approvals?status=pending")
    assert [a["id"] for a in pending] == [approval]
    status, decided, _ = call(server, "POST", f"/api/approvals/{approval}/deny", {})
    assert status == 200 and decided == {"status": "denied"}
    assert call(server, "POST", f"/api/approvals/{approval}/approve", {})[0] == 400  # already decided


def test_audit_endpoint(server):
    call(server, "POST", "/api/projects", {"name": "Audit"})
    status, audit, _ = call(server, "GET", "/api/audit?n=5")
    assert status == 200 and audit["chain_ok"] and audit["entries"][-1]["action"] == "project.create"


def test_second_server_on_same_data_folder_is_refused(server, home):
    with pytest.raises(WorkerBusy):
        ApiServer(home, port=0, hardware=LITE_HW)


def test_fallback_page_when_ui_is_not_built(home, tmp_path):
    srv = ApiServer(home, port=0, hardware=LITE_HW, static_dir=tmp_path / "empty")
    srv.start_in_background()
    try:
        status, html, _ = call(srv, "GET", "/", token=False)
        assert status == 200 and "non è stata compilata" in html
    finally:
        srv.shutdown()


def test_lab_endpoints(server):
    _, task, _ = call(server, "POST", "/api/tasks", {"kind": "lab.run", "payload": {"dataset": "classify-it",
                                                                                    "subject": "classifier"}})
    exp_id = wait_for(server, task["id"])["result"]["experiment_id"]
    _, base_task, _ = call(server, "POST", "/api/tasks", {"kind": "lab.run", "payload": {
        "dataset": "classify-it", "subject": "baseline:majority"}})
    base_id = wait_for(server, base_task["id"])["result"]["experiment_id"]
    assert len(call(server, "GET", "/api/lab/datasets")[1]) == 5
    assert "classifier" in call(server, "GET", "/api/lab/subjects")[1]
    assert call(server, "GET", "/api/lab/experiments")[1][0]["id"] in (exp_id, base_id)
    detail = call(server, "GET", f"/api/lab/experiments/{exp_id}")[1]
    assert detail["experiment"]["metrics"]["correct"] == 27 and len(detail["results"]) == 30
    cmp = call(server, "GET", f"/api/lab/compare?a={base_id}&b={exp_id}")[1]
    assert cmp["significant"] and call(server, "GET", "/api/lab/compare?a=x")[0] == 400


def test_improvement_endpoints(server):
    _, task, _ = call(server, "POST", "/api/tasks", {"kind": "improve.cycle", "payload": {"component": "classifier",
                                                                                         "candidate": "v2"}})
    imp = wait_for(server, task["id"], timeout=30)["result"]["improvement_id"]
    assert call(server, "GET", "/api/improvement/components")[1][0]["active"] == "v1"
    assert call(server, "GET", "/api/improvement/proposals")[1][0]["evaluation"]["promotable"]
    status, promoted, _ = call(server, "POST", f"/api/improvement/proposals/{imp}/approve", {})
    assert status == 200 and promoted["status"] == "promoted"
    assert call(server, "GET", "/api/improvement/components")[1][0]["active"] == "v2"
    assert call(server, "POST", "/api/improvement/components/classifier/rollback", {})[1]["active"] == "v1"
    assert call(server, "POST", "/api/improvement/components/permissions/rollback", {})[0] == 403
