"""Stato persistente (SQLite, solo stdlib): video, apprendimenti, quota, trend."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,
    created REAL NOT NULL,
    day TEXT NOT NULL,
    format TEXT NOT NULL,            -- short | long
    status TEXT NOT NULL,            -- idea | scripted | rejected | rendered | uploaded | failed
    topic TEXT,
    title TEXT,
    data TEXT,                       -- JSON: script, seo, review
    file TEXT,
    youtube_id TEXT,
    publish_at TEXT,
    views INTEGER DEFAULT 0,
    likes INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    stats_at REAL,
    error TEXT
);
CREATE INDEX IF NOT EXISTS videos_channel ON videos(channel, day);
CREATE TABLE IF NOT EXISTS learnings (channel TEXT, created REAL, text TEXT);
CREATE TABLE IF NOT EXISTS quota (project TEXT, day TEXT, units INTEGER, PRIMARY KEY(project, day));
CREATE TABLE IF NOT EXISTS trends (channel TEXT, created REAL, data TEXT);
CREATE TABLE IF NOT EXISTS channel_stats (channel TEXT, created REAL, data TEXT);
"""


class DB:
    def __init__(self, path: Path):
        self.path = path
        self.con = sqlite3.connect(str(path))
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA)

    def close(self) -> None:
        self.con.close()

    # -- video ---------------------------------------------------------------
    def add_video(self, channel: str, day: str, fmt: str, topic: str) -> int:
        cur = self.con.execute(
            "INSERT INTO videos(channel, created, day, format, status, topic, data) VALUES (?,?,?,?,?,?,?)",
            (channel, time.time(), day, fmt, "idea", topic, "{}"),
        )
        self.con.commit()
        return int(cur.lastrowid)

    def update_video(self, vid: int, **fields: Any) -> None:
        if "data" in fields and not isinstance(fields["data"], str):
            fields["data"] = json.dumps(fields["data"], ensure_ascii=False)
        cols = ", ".join(f"{k}=?" for k in fields)
        self.con.execute(f"UPDATE videos SET {cols} WHERE id=?", (*fields.values(), vid))
        self.con.commit()

    def video(self, vid: int) -> Dict[str, Any]:
        row = self.con.execute("SELECT * FROM videos WHERE id=?", (vid,)).fetchone()
        return _row(row)

    def videos(self, channel: Optional[str] = None, status: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        q, args = "SELECT * FROM videos WHERE 1=1", []
        if channel:
            q += " AND channel=?"
            args.append(channel)
        if status:
            q += " AND status=?"
            args.append(status)
        q += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        return [_row(r) for r in self.con.execute(q, args)]

    def count_day(self, channel: str, day: str, fmt: str) -> int:
        """Video già prodotti (non scartati/falliti) per quel giorno: rende `run` idempotente."""
        return int(self.con.execute(
            "SELECT COUNT(*) FROM videos WHERE channel=? AND day=? AND format=? AND status IN ('rendered','uploaded')",
            (channel, day, fmt),
        ).fetchone()[0])

    def recent_topics(self, channel: str, limit: int = 120) -> List[str]:
        rows = self.con.execute(
            "SELECT COALESCE(title, topic) FROM videos WHERE channel=? AND status!='rejected' ORDER BY id DESC LIMIT ?",
            (channel, limit),
        )
        return [r[0] for r in rows if r[0]]

    # -- apprendimenti, trend, statistiche ------------------------------------
    def add_learning(self, channel: str, text: str) -> None:
        self.con.execute("INSERT INTO learnings VALUES (?,?,?)", (channel, time.time(), text))
        self.con.commit()

    def latest_learning(self, channel: str) -> str:
        r = self.con.execute("SELECT text FROM learnings WHERE channel=? ORDER BY created DESC LIMIT 1", (channel,)).fetchone()
        return r[0] if r else ""

    def save_json(self, table: str, channel: str, data: Any) -> None:
        assert table in ("trends", "channel_stats")
        self.con.execute(f"INSERT INTO {table} VALUES (?,?,?)", (channel, time.time(), json.dumps(data, ensure_ascii=False)))
        self.con.commit()

    def latest_json(self, table: str, channel: str, max_age: float = 1e12) -> Any:
        assert table in ("trends", "channel_stats")
        r = self.con.execute(f"SELECT created, data FROM {table} WHERE channel=? ORDER BY created DESC LIMIT 1", (channel,)).fetchone()
        if not r or time.time() - r[0] > max_age:
            return None
        return json.loads(r[1])

    # -- quota YouTube -------------------------------------------------------
    def quota_used(self, project: str, day: str) -> int:
        r = self.con.execute("SELECT units FROM quota WHERE project=? AND day=?", (project, day)).fetchone()
        return int(r[0]) if r else 0

    def spend_quota(self, project: str, day: str, units: int) -> None:
        self.con.execute(
            "INSERT INTO quota VALUES (?,?,?) ON CONFLICT(project, day) DO UPDATE SET units = units + excluded.units",
            (project, day, units),
        )
        self.con.commit()


def _row(row: Optional[sqlite3.Row]) -> Dict[str, Any]:
    if row is None:
        return {}
    d = dict(row)
    d["data"] = json.loads(d.get("data") or "{}")
    return d
