"""Versioned schema migrations. Append new versions; never edit a released one.

The applied version is stored in ``PRAGMA user_version``.
"""

from __future__ import annotations

MIGRATIONS: tuple[tuple[int, str, str], ...] = (
    (
        1,
        "initial schema: projects, tasks, approvals, append-only audit log",
        """
CREATE TABLE projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    description TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE tasks (
    id               TEXT PRIMARY KEY,
    project_id       TEXT REFERENCES projects (id) ON DELETE SET NULL,
    kind             TEXT NOT NULL,
    payload          TEXT NOT NULL DEFAULT '{}',
    principal        TEXT NOT NULL,
    level            INTEGER NOT NULL CHECK (level BETWEEN 1 AND 5),
    status           TEXT NOT NULL
                     CHECK (status IN ('pending', 'running', 'succeeded', 'failed', 'cancelled')),
    priority         INTEGER NOT NULL DEFAULT 0,
    attempts         INTEGER NOT NULL DEFAULT 0,
    max_attempts     INTEGER NOT NULL DEFAULT 1,
    approval_id      TEXT,
    result           TEXT,
    error            TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    started_at       TEXT,
    finished_at      TEXT
);
CREATE INDEX idx_tasks_queue ON tasks (status, priority DESC, created_at);
CREATE INDEX idx_tasks_project ON tasks (project_id);

CREATE TABLE approvals (
    id         TEXT PRIMARY KEY,
    principal  TEXT NOT NULL,
    action     TEXT NOT NULL,
    level      INTEGER NOT NULL CHECK (level BETWEEN 1 AND 5),
    details    TEXT NOT NULL DEFAULT '{}',
    status     TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'denied', 'used')),
    created_at TEXT NOT NULL,
    decided_at TEXT,
    decided_by TEXT
);

CREATE TABLE audit_log (
    seq       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT NOT NULL,
    principal TEXT NOT NULL,
    action    TEXT NOT NULL,
    level     INTEGER,
    outcome   TEXT NOT NULL,
    details   TEXT NOT NULL DEFAULT '{}',
    prev_hash TEXT NOT NULL,
    hash      TEXT NOT NULL
);
CREATE TRIGGER audit_log_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER audit_log_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
""",
    ),
)


def latest() -> int:
    return MIGRATIONS[-1][0] if MIGRATIONS else 0
