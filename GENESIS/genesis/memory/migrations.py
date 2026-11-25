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
    (
        2,
        "agent runs (Phase 4)",
        """
CREATE TABLE agent_runs (
    id            TEXT PRIMARY KEY,
    agent_id      TEXT NOT NULL,
    agent_version TEXT NOT NULL,
    mode          TEXT NOT NULL CHECK (mode IN ('agent', 'director', 'council')),
    goal          TEXT NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    steps         TEXT,
    output        TEXT,
    created_at    TEXT NOT NULL,
    finished_at   TEXT
);
CREATE INDEX idx_agent_runs_created ON agent_runs (created_at);
""",
    ),
    (
        3,
        "research lab: datasets, experiments, per-item results (Phase 6)",
        """
CREATE TABLE datasets (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    version     TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    hash        TEXT NOT NULL,
    items       TEXT NOT NULL,
    builtin     INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    UNIQUE (name, version)
);
CREATE TABLE experiments (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    objective       TEXT NOT NULL DEFAULT '',
    hypothesis      TEXT NOT NULL DEFAULT '',
    dataset_id      TEXT NOT NULL REFERENCES datasets (id),
    dataset_hash    TEXT NOT NULL,
    subject         TEXT NOT NULL,
    subject_version TEXT NOT NULL,
    deterministic   INTEGER NOT NULL,
    config          TEXT NOT NULL,
    config_hash     TEXT NOT NULL,
    seed            INTEGER NOT NULL,
    environment     TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed', 'interrupted')),
    metrics         TEXT,
    resources       TEXT,
    errors          TEXT,
    evaluation      TEXT,
    baseline_id     TEXT,
    reproduced_from TEXT,
    created_at      TEXT NOT NULL,
    finished_at     TEXT
);
CREATE INDEX idx_experiments_created ON experiments (created_at);
CREATE TABLE experiment_results (
    experiment_id TEXT NOT NULL REFERENCES experiments (id) ON DELETE CASCADE,
    item_idx      INTEGER NOT NULL,
    input         TEXT NOT NULL,
    expected      TEXT NOT NULL,
    output        TEXT,
    correct       INTEGER NOT NULL,
    latency_ms    REAL NOT NULL,
    engine        TEXT,
    error         TEXT,
    PRIMARY KEY (experiment_id, item_idx)
);
""",
    ),
    (
        4,
        "memory engine: project, permanent and operational memories (Phase 7)",
        """
CREATE TABLE memories (
    id         TEXT PRIMARY KEY,
    level      TEXT NOT NULL CHECK (level IN ('project', 'permanent', 'operational')),
    project_id TEXT REFERENCES projects (id) ON DELETE CASCADE,
    content    TEXT NOT NULL,
    tags       TEXT NOT NULL DEFAULT '',
    source     TEXT NOT NULL DEFAULT '',
    principal  TEXT NOT NULL,
    deleted    INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_memories_level ON memories (level, deleted);
""",
    ),
    (
        5,
        "self-improvement: proposals and active component versions (Phase 9)",
        """
CREATE TABLE improvements (
    id          TEXT PRIMARY KEY,
    component   TEXT NOT NULL,
    stable      TEXT NOT NULL,
    candidate   TEXT NOT NULL,
    problem     TEXT NOT NULL,
    evidence    TEXT NOT NULL,
    cause       TEXT NOT NULL,
    proposal    TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('proposed', 'evaluated', 'promoted', 'rejected', 'rolled_back')),
    evaluation  TEXT,
    decision    TEXT,
    approval_id TEXT,
    proposed_by TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE component_versions (
    component      TEXT PRIMARY KEY,
    active         TEXT NOT NULL,
    previous       TEXT,
    improvement_id TEXT,
    updated_at     TEXT NOT NULL,
    updated_by     TEXT NOT NULL
);
""",
    ),
)


def latest() -> int:
    return MIGRATIONS[-1][0] if MIGRATIONS else 0
