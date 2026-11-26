"""The owner's documents: text files kept in ``<home>/workspace/documenti`` (inside the tool sandbox), indexed
by ``text.find`` and usable as sources in the chat. Removing a document moves it to ``workspace/.cestino``
(never a permanent deletion)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .core.clock import file_stamp
from .errors import GenesisError
from .security.permissions import OWNER
from .tools.registry import MAX_FILE, ToolRegistry

FOLDER = "documenti"
TRASH = ".cestino"
TEXT_EXT = {".txt", ".md", ".csv", ".json", ".html", ".htm", ".xml", ".log", ".py", ".js", ".ts", ".css",
            ".ini", ".toml", ".yaml", ".yml", ".srt"}
NAME_RE = re.compile(r"^[^\\/:*?\"<>|\x00-\x1f]{1,120}$")


class DocumentError(GenesisError):
    pass


class DocumentStore:
    def __init__(self, tools: ToolRegistry) -> None:
        self.tools = tools

    @property
    def folder(self) -> Path:
        path = self.tools.workspace.root / FOLDER
        path.mkdir(parents=True, exist_ok=True)
        return path

    def list(self) -> list[dict[str, Any]]:
        out = []
        for f in sorted(self.folder.iterdir(), key=lambda p: p.name.lower()):
            if f.is_file():
                st = f.stat()
                out.append({"name": f.name, "size": st.st_size, "modified": st.st_mtime})
        return out

    def save(self, name: str, content: str, overwrite: bool = False) -> dict[str, Any]:
        name = (name or "").strip()
        if not NAME_RE.match(name) or name.startswith(".") or name in (".", ".."):
            raise DocumentError("nome di file non valido")
        if Path(name).suffix.lower() not in TEXT_EXT:
            raise DocumentError("per ora solo file di testo (.txt, .md, .csv, .json, .html…): PDF e Word non ancora")
        if len(content.encode("utf-8")) > MAX_FILE:
            raise DocumentError("file troppo grande (massimo 1 MB di testo)")
        self.folder  # make sure the folder exists
        result = self.tools.call(OWNER, "files.write", {"path": f"{FOLDER}/{name}", "content": content,
                                                        "overwrite": overwrite})["result"]
        return {"name": name, "bytes": result["bytes"]}

    def remove(self, name: str) -> dict[str, Any]:
        source = self.folder / name
        if not NAME_RE.match(name or "") or not source.is_file() or source.parent != self.folder:
            raise DocumentError(f"documento inesistente: {name}")
        trash = self.tools.workspace.root / TRASH
        trash.mkdir(parents=True, exist_ok=True)
        target = trash / f"{file_stamp()}-{name}"
        source.replace(target)
        self.tools.audit.record(OWNER, "documents.remove", "ok", 2, {"name": name, "moved_to": f"{TRASH}/{target.name}"})
        return {"name": name, "moved_to": f"{TRASH}/{target.name}"}
