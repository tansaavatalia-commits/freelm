"""Minimal MCP client: stdio transport, JSON-RPC 2.0, one JSON message per line.

A server process lives only for one operation (start, initialize, request, stop),
so nothing stays resident on a 4 GB PC. Servers are declared only by the owner in
genesis.toml; their output is untrusted data.
"""

from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from typing import Any, Callable

from .. import __version__
from ..errors import ToolError

PROTOCOL_VERSION = "2025-06-18"
MAX_TEXT = 20_000


class McpSession:
    def __init__(self, command: list[str], timeout: float, cancelled: Callable[[], bool] = lambda: False) -> None:
        self.command, self.timeout, self.cancelled = command, timeout, cancelled
        self._id = 0
        self._inbox: queue.Queue[dict[str, Any] | None] = queue.Queue()

    def __enter__(self) -> McpSession:
        try:
            self.proc = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1)
        except OSError as exc:
            raise ToolError(f"impossibile avviare il server MCP: {exc}") from exc
        threading.Thread(target=self._read, daemon=True).start()
        try:
            self._request("initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                                         "clientInfo": {"name": "genesis", "version": __version__}})
            self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        except BaseException:
            self.__exit__()
            raise
        return self

    def __exit__(self, *exc: object) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            self.proc.kill()

    def _read(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if isinstance(message, dict):
                self._inbox.put(message)
        self._inbox.put(None)

    def _send(self, message: dict[str, Any]) -> None:
        try:
            assert self.proc.stdin is not None
            self.proc.stdin.write(json.dumps(message) + "\n")
            self.proc.stdin.flush()
        except (OSError, ValueError) as exc:
            raise ToolError("il server MCP non accetta richieste") from exc

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._id += 1
        self._send({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params})
        deadline = time.monotonic() + self.timeout
        while True:
            if self.cancelled():
                raise ToolError("annullato")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ToolError(f"il server MCP non ha risposto entro {self.timeout:g} s")
            try:
                message = self._inbox.get(timeout=min(0.2, remaining))
            except queue.Empty:
                continue
            if message is None:
                raise ToolError("il server MCP si è chiuso")
            if message.get("id") != self._id:
                continue  # notifications or stale responses
            if "error" in message:
                raise ToolError(f"errore MCP: {message['error'].get('message', 'sconosciuto')}")
            result = message.get("result")
            return result if isinstance(result, dict) else {}

    def list_tools(self) -> list[dict[str, Any]]:
        tools = self._request("tools/list", {}).get("tools", [])
        return [{"name": t.get("name"), "description": t.get("description", "")} for t in tools if isinstance(t, dict)]

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = self._request("tools/call", {"name": name, "arguments": arguments})
        texts = [c.get("text", "") for c in result.get("content", []) if isinstance(c, dict) and c.get("type") == "text"]
        text = "\n".join(texts)
        return {"is_error": bool(result.get("isError")), "text": text[:MAX_TEXT], "truncated": len(text) > MAX_TEXT}
