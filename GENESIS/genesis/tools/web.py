"""web.fetch: HTTP(S) GET of public pages only (no local/private addresses, re-checked on every
redirect), size and time limits, cancellable. The output is untrusted data, never instructions.
Known limit: the address check and the connection resolve DNS separately (rebinding window)."""

from __future__ import annotations

import ipaddress
import socket
import urllib.error
import urllib.request
from html.parser import HTMLParser
from typing import Any, Callable
from urllib.parse import urlsplit

from .. import __version__
from ..errors import ToolError

MAX_BYTES = 1_000_000
MAX_TEXT = 20_000
TIMEOUT = 15


def check_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ToolError("solo indirizzi http:// o https://")
    if parts.username or parts.password:
        raise ToolError("credenziali nell'indirizzo non ammesse")
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80),
                                   proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError) as exc:
        raise ToolError(f"host non risolvibile: {parts.hostname}") from exc
    for info in infos:
        if not ipaddress.ip_address(info[4][0].split("%")[0]).is_global:
            raise ToolError("indirizzi locali o privati non ammessi")


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Any:
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "template"}
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr", "section", "article"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        self.skip += tag in self.SKIP
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        self.skip -= tag in self.SKIP and self.skip > 0

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _Text()
    parser.feed(html)
    lines = (" ".join(line.split()) for line in "".join(parser.parts).splitlines())
    return "\n".join(line for line in lines if line)


def fetch(params: dict[str, Any], cancelled: Callable[[], bool], opener: Any = None) -> dict[str, Any]:
    url = params["url"]
    check_url(url)
    opener = opener or urllib.request.build_opener(SafeRedirect())
    request = urllib.request.Request(url, headers={"User-Agent": f"GENESIS/{__version__}",
                                                   "Accept": "text/html,text/plain,application/json;q=0.9"})
    try:
        with opener.open(request, timeout=TIMEOUT) as resp:
            content_type = resp.headers.get("Content-Type", "")
            charset = resp.headers.get_content_charset() or "utf-8"
            chunks, total = [], 0
            while chunk := resp.read(65536):
                if cancelled():
                    raise ToolError("annullato")
                total += len(chunk)
                if total > MAX_BYTES:
                    raise ToolError("pagina troppo grande (oltre 1 MB)")
                chunks.append(chunk)
            status, final_url = resp.status, resp.geturl()
    except urllib.error.HTTPError as exc:
        raise ToolError(f"il sito ha risposto HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ToolError(f"errore di rete: {exc}") from exc
    text = b"".join(chunks).decode(charset, errors="replace")
    if "html" in content_type:
        text = html_to_text(text)
    return {"url": final_url, "status": status, "content_type": content_type, "text": text[:MAX_TEXT],
            "truncated": len(text) > MAX_TEXT}
