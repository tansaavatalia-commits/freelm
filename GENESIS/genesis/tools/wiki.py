"""Web sources for the chat: Wikipedia's public API (free, no account, no key; Wikimedia allows API use
with an identifying User-Agent). Results are untrusted data with their address, so answers can cite them.
Network access goes through :func:`web.fetch` (public addresses only, size and time limits)."""

from __future__ import annotations

import json
from typing import Any, Callable
from urllib.parse import quote, urlencode

from ..errors import ToolError
from . import web

MAX_EXTRACT = 1_500
# Words that say *how* to answer, not *what* to look for (Italian + a few English): left out of the search.
STOP = set("""
chi che cosa cos cose come quando dove perche perché quale quali quanto quanta quanti quante era erano sono sei
è e ed o oppure il lo la i gli le un uno una dei degli delle del dello della di a da in con su per tra fra al allo
alla ai agli alle dal dallo dalla dai dagli dalle nel nello nella nei negli nelle sul sullo sulla sui sugli sulle
mi ti ci vi si me te ne non anche ma più piu molto poco questo questa questi queste quello quella
spiegami spiega dimmi raccontami parlami descrivi riassumi rispondi risposta breve brevemente frase frasi parole
una due tre punto punti elenco favore grazie ciao vorrei sapere puoi potresti fammi dammi cerca trova
what who is are was the a an of in on how why when where please tell me explain
""".split())


def keywords(question: str) -> str:
    """The searchable part of a question: names and topic words, without question and instruction words."""
    words = [w for w in "".join(c if c.isalnum() else " " for c in question).split()
             if w.lower() not in STOP and (len(w) > 2 or w.isdigit())]
    return " ".join(words[:10]) or " ".join(question.split()[:10])


def _api(lang: str, params: dict[str, str], opener: Any, cancelled: Callable[[], bool]) -> dict[str, Any]:
    url = f"https://{lang}.wikipedia.org/w/api.php?" + urlencode({**params, "format": "json", "utf8": "1"})
    page = web.fetch({"url": url}, cancelled, opener)
    try:
        return json.loads(page["text"])
    except ValueError as exc:
        raise ToolError("risposta di Wikipedia non leggibile") from exc


def search(query: str, *, lang: str = "it", limit: int = 3, opener: Any = None,
           cancelled: Callable[[], bool] = lambda: False) -> list[dict[str, str]]:
    """Up to ``limit`` articles: title, address and the opening text (plain, max 1500 characters)."""
    query = keywords(" ".join(query.split())[:300])
    if not query:
        return []
    found = _api(lang, {"action": "query", "list": "search", "srsearch": query, "srlimit": str(limit)},
                 opener, cancelled)
    titles = [hit["title"] for hit in found.get("query", {}).get("search", []) if isinstance(hit, dict)][:limit]
    if not titles:
        return []
    data = _api(lang, {"action": "query", "prop": "extracts", "exintro": "1", "explaintext": "1",
                       "redirects": "1", "titles": "|".join(titles)}, opener, cancelled)
    pages = {p.get("title"): p.get("extract", "") for p in data.get("query", {}).get("pages", {}).values()
             if isinstance(p, dict)}
    out = []
    for title in titles:
        text = " ".join((pages.get(title) or "").split())
        if text:
            url = f"https://{lang}.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"
            out.append({"title": title, "url": url, "text": text[:MAX_EXTRACT]})
    return out
