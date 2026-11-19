"""Reparto qualità: verifica dei fatti su Wikipedia (gratuita, senza chiave) prima che uno script vada in onda."""
from __future__ import annotations

import asyncio
import os
import re
from typing import Any, Dict, List

import httpx

UA = {"User-Agent": "yt-factory/0.2 (fact-checking bot; https://github.com/shihabshahrier/freelm)"}


async def lookup(http: httpx.AsyncClient, query: str, lang: str = "en") -> str:
    """Estratto delle 2 pagine Wikipedia più pertinenti."""
    r = await http.get(f"https://{lang}.wikipedia.org/w/rest.php/v1/search/page", params={"q": query, "limit": 2},
                       headers=UA)
    r.raise_for_status()
    texts = []
    for page in r.json().get("pages", []):
        s = await http.get(f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{page['key']}", headers=UA)
        if s.status_code == 200:
            texts.append(f"[{page['title']}] {s.json().get('extract', '')[:900]}")
        else:
            texts.append(f"[{page['title']}] " + re.sub(r"<[^>]+>", "", page.get("excerpt", "")))
    return "\n".join(texts)


async def gather_sources(http: httpx.AsyncClient, claims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if os.environ.get("YTF_OFFLINE"):
        return []

    async def one(c: Dict[str, Any]) -> Dict[str, Any]:
        try:
            src = await lookup(http, str(c.get("query") or c.get("claim", ""))[:120])
        except (httpx.HTTPError, ValueError, KeyError):
            src = ""
        return {"claim": c.get("claim", ""), "sources": src or "(no source found)"}

    return list(await asyncio.gather(*(one(c) for c in claims[:6])))
