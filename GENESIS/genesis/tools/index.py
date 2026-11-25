"""Indexed full-text search over the sandbox workspace (SQLite FTS5, BM25 ranking, accents ignored).

The index is a disposable cache in ``<home>/cache``: it is never exported or backed up and can be
deleted at any time. Before each search it is brought up to date by *stat-ing* the workspace files
(size + modification time): only new or changed files are read again, which matters on slow disks.
Without FTS5 the caller falls back to the linear ``text.search``.
"""

from __future__ import annotations

import os
import re
import sqlite3
import unicodedata
from contextlib import closing
from pathlib import Path
from typing import Any, Callable, Iterator

from ..errors import ToolError

MAX_FILE = 1_000_000
MAX_FILES = 5_000  # safety bound on a 4 GB PC
MAX_WORDS = 12
TOP_FILES = 20
Cancel = Callable[[], bool]


def fold(text: str) -> str:
    """Lowercase without accents, like the FTS5 tokenizer (remove_diacritics)."""
    return unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()


def words_of(query: str) -> list[str]:
    return re.findall(r"\w+", fold(query))[:MAX_WORDS]


class WorkspaceIndex:
    def __init__(self, root: Path, path: Path) -> None:
        self.root, self.path = root, path

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE IF NOT EXISTS files (id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, "
                     "mtime_ns INTEGER NOT NULL, size INTEGER NOT NULL)")
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS docs USING fts5(text, "
                     "tokenize='unicode61 remove_diacritics 2')")
        return conn

    def available(self) -> bool:
        try:
            with closing(self._connect()):
                return True
        except sqlite3.OperationalError:
            return False

    def refresh(self, cancelled: Cancel = lambda: False) -> dict[str, int]:
        """Index new/changed files, drop removed ones. Returns counters."""
        stats = {"files": 0, "indexed": 0, "removed": 0}
        with closing(self._connect()) as conn, conn:
            known = {p: (i, m, s) for i, p, m, s in conn.execute("SELECT id, path, mtime_ns, size FROM files")}
            seen: set[str] = set()
            for rel, f, st in self._walk(cancelled):
                if st.st_size > MAX_FILE:
                    continue
                seen.add(rel)
                stats["files"] += 1
                if stats["files"] > MAX_FILES:
                    raise ToolError(f"troppi file nella cartella di lavoro (oltre {MAX_FILES})")
                old = known.get(rel)
                if old and old[1] == st.st_mtime_ns and old[2] == st.st_size:
                    continue
                try:
                    text = f.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                if "\x00" in text[:4096]:
                    text = ""  # binary file: tracked but not searchable
                if old:
                    conn.execute("DELETE FROM docs WHERE rowid = ?", (old[0],))
                    conn.execute("UPDATE files SET mtime_ns = ?, size = ? WHERE id = ?",
                                 (st.st_mtime_ns, st.st_size, old[0]))
                    rowid = old[0]
                else:
                    rowid = conn.execute("INSERT INTO files (path, mtime_ns, size) VALUES (?, ?, ?)",
                                         (rel, st.st_mtime_ns, st.st_size)).lastrowid
                conn.execute("INSERT INTO docs (rowid, text) VALUES (?, ?)", (rowid, text))
                stats["indexed"] += 1
            for rel, (rowid, _, _) in known.items():
                if rel not in seen:
                    conn.execute("DELETE FROM docs WHERE rowid = ?", (rowid,))
                    conn.execute("DELETE FROM files WHERE id = ?", (rowid,))
                    stats["removed"] += 1
        return stats

    def _walk(self, cancelled: Cancel) -> Iterator[tuple[str, Path, os.stat_result]]:
        """Regular files under the root. Symlinks and junctions are skipped, never followed, so nothing
        outside the sandbox is reached; ``scandir`` gives size/mtime without one extra call per file
        (on Windows), which keeps a warm refresh cheap on a slow disk."""
        stack = [(self.root, "")]
        while stack:
            folder, prefix = stack.pop()
            try:
                entries = sorted(os.scandir(folder), key=lambda e: e.name)
            except OSError:
                continue
            for e in entries:
                if cancelled():
                    raise ToolError("annullato")
                try:
                    if e.is_symlink() or (hasattr(e, "is_junction") and e.is_junction()):
                        continue
                    rel = prefix + e.name
                    if e.is_dir(follow_symlinks=False):
                        stack.append((Path(e.path), rel + "/"))
                    elif e.is_file(follow_symlinks=False):
                        yield rel, Path(e.path), e.stat(follow_symlinks=False)
                except OSError:
                    continue

    def search(self, query: str, limit: int, cancelled: Cancel = lambda: False) -> list[dict[str, Any]]:
        words = words_of(query)
        if not words:
            raise ToolError("la ricerca non contiene parole")
        self.refresh(cancelled)
        match = " AND ".join(f'"{w}"' for w in words)  # quoted tokens: no FTS syntax injection
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT f.path, bm25(docs) AS score FROM docs JOIN files f ON f.id = docs.rowid "
                                "WHERE docs MATCH ? ORDER BY score LIMIT ?", (match, TOP_FILES)).fetchall()
        found: list[dict[str, Any]] = []
        for rel, score in rows:
            if cancelled():
                raise ToolError("annullato")
            try:
                text = (self.root / rel).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for n, line in enumerate(text.splitlines(), 1):
                folded = fold(line)
                if any(w in folded for w in words):
                    found.append({"file": rel, "line": n, "text": line.strip()[:300], "score": round(-score, 4)})
                    if len(found) >= limit:
                        return found
        return found
