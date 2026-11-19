"""Raccolta dati di tendenza (team ricerca).

Fonti, tutte gratuite:
- YouTube Data API (YT_API_KEY): video più popolari della regione + ricerca per parole chiave della nicchia
  negli ultimi 7 giorni ordinata per visualizzazioni; calcola le views/ora (velocità = segnale virale).
- RSS dei canali concorrenti (`seed_channel_ids`, senza chiave): ultimi video con visualizzazioni.
- Google Trends RSS (senza chiave): ricerche in crescita oggi nel paese.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import httpx

from .config import Channel

YT = "https://www.googleapis.com/youtube/v3"
NS = {"a": "http://www.w3.org/2005/Atom", "m": "http://search.yahoo.com/mrss/",
      "yt": "http://www.youtube.com/xml/schemas/2015", "ht": "https://trends.google.com/trending/rss"}


def _velocity(views: int, published: str) -> float:
    try:
        t = datetime.fromisoformat(published.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    hours = max((datetime.now(timezone.utc) - t).total_seconds() / 3600, 1.0)
    return views / hours


async def google_trends(http: httpx.AsyncClient, geo: str) -> List[Dict[str, Any]]:
    r = await http.get("https://trends.google.com/trending/rss", params={"geo": geo})
    r.raise_for_status()
    root = ET.fromstring(r.content)
    out = []
    for item in root.iter("item"):
        title = item.findtext("title") or ""
        traffic = item.findtext("ht:approx_traffic", namespaces=NS) or ""
        out.append({"title": title, "traffic": traffic})
    return out


async def channel_rss(http: httpx.AsyncClient, channel_id: str) -> List[Dict[str, Any]]:
    r = await http.get("https://www.youtube.com/feeds/videos.xml", params={"channel_id": channel_id})
    r.raise_for_status()
    root = ET.fromstring(r.content)
    out = []
    for e in root.findall("a:entry", NS):
        stats = e.find(".//m:statistics", NS)
        views = int(stats.get("views", 0)) if stats is not None else 0
        published = e.findtext("a:published", default="", namespaces=NS)
        out.append({"id": e.findtext("yt:videoId", default="", namespaces=NS) or None,
                    "title": e.findtext("a:title", default="", namespaces=NS), "views": views,
                    "published": published, "views_per_hour": _velocity(views, published), "source": "rss"})
    return out


async def yt_most_popular(http: httpx.AsyncClient, key: str, region: str, category: str) -> List[Dict[str, Any]]:
    params = {"part": "snippet,statistics", "chart": "mostPopular", "regionCode": region,
              "maxResults": 50, "key": key}
    if category:
        params["videoCategoryId"] = category
    r = await http.get(f"{YT}/videos", params=params)
    if r.status_code == 400 and category:  # alcune categorie non hanno classifica: riprova generale
        params.pop("videoCategoryId")
        r = await http.get(f"{YT}/videos", params=params)
    r.raise_for_status()
    return [_video_item(i, "mostPopular") for i in r.json().get("items", [])]


async def yt_search(http: httpx.AsyncClient, key: str, query: str, region: str, lang: str) -> List[Dict[str, Any]]:
    """search.list costa 100 unità: usata con parsimonia (2 parole chiave per run)."""
    after = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = await http.get(f"{YT}/search", params={
        "part": "id", "q": query, "type": "video", "order": "viewCount", "publishedAfter": after,
        "regionCode": region, "relevanceLanguage": lang, "maxResults": 25, "key": key})
    r.raise_for_status()
    ids = [i["id"]["videoId"] for i in r.json().get("items", []) if i.get("id", {}).get("videoId")]
    if not ids:
        return []
    r = await http.get(f"{YT}/videos", params={"part": "snippet,statistics", "id": ",".join(ids), "key": key})
    r.raise_for_status()
    return [_video_item(i, f"search:{query}") for i in r.json().get("items", [])]


def _video_item(i: Dict[str, Any], source: str) -> Dict[str, Any]:
    views = int(i.get("statistics", {}).get("viewCount", 0))
    published = i.get("snippet", {}).get("publishedAt", "")
    return {"id": i.get("id") if isinstance(i.get("id"), str) else None, "title": i["snippet"]["title"],
            "views": views, "published": published, "views_per_hour": _velocity(views, published), "source": source}


async def collect(ch: Channel, http: httpx.AsyncClient, log=lambda *a: None) -> Dict[str, Any]:
    if os.environ.get("YTF_OFFLINE"):
        return {"videos": [], "searches": [], "live_youtube": False, "collected_at": ""}
    key = os.environ.get("YT_API_KEY", "")
    jobs: List[Any] = [google_trends(http, ch.region)]
    jobs += [channel_rss(http, cid) for cid in ch.seed_channel_ids]
    if key:
        jobs.append(yt_most_popular(http, key, ch.region, ch.category_id))
        jobs += [yt_search(http, key, kw, ch.region, ch.language) for kw in ch.keywords[:2]]
    results = await asyncio.gather(*jobs, return_exceptions=True)
    searches: List[Dict[str, Any]] = []
    videos: List[Dict[str, Any]] = []
    for i, res in enumerate(results):
        if isinstance(res, Exception):
            log(f"fonte trend {i} non disponibile: {_short(res)}")
            continue
        (searches if i == 0 else videos).extend(res)
    seen, uniq = set(), []
    for v in sorted(videos, key=lambda v: v["views_per_hour"], reverse=True):
        k = re.sub(r"\W+", "", v["title"].lower())
        if k not in seen:
            seen.add(k)
            uniq.append(v)
    return {"videos": uniq[:40], "searches": searches[:20],
            "live_youtube": bool(key or ch.seed_channel_ids), "collected_at": datetime.now(timezone.utc).isoformat()}


# --------------------------------------------------------------------------- segnali del pubblico
PREFIXES = {"en": ["why", "how", "what if"], "it": ["perché", "come", "cosa succede se"]}


async def youtube_suggest(http: httpx.AsyncClient, query: str, lang: str) -> List[str]:
    """Autocompletamento di ricerca YouTube (senza chiave): cosa la gente cerca davvero."""
    r = await http.get("https://suggestqueries.google.com/complete/search",
                       params={"client": "firefox", "ds": "yt", "hl": lang, "q": query})
    r.raise_for_status()
    data = json.loads(r.content.decode(r.encoding or "utf-8", errors="replace"))
    return [s for s in data[1] if isinstance(s, str)]


async def top_comments(http: httpx.AsyncClient, key: str, video_id: str) -> List[str]:
    r = await http.get(f"{YT}/commentThreads", params={"part": "snippet", "videoId": video_id, "order": "relevance",
                                                         "maxResults": 20, "textFormat": "plainText", "key": key})
    r.raise_for_status()
    out = []
    for it in r.json().get("items", []):
        c = it["snippet"]["topLevelComment"]["snippet"]
        if c.get("likeCount", 0) >= 3:
            out.append(c["textDisplay"][:220].replace("\n", " "))
    return out


async def audience(ch: Channel, http: httpx.AsyncClient, videos: List[Dict[str, Any]], log=lambda *a: None) -> Dict[str, Any]:
    if os.environ.get("YTF_OFFLINE"):
        return {"suggestions": [], "comments": []}
    queries = list(ch.keywords[:4])
    queries += [f"{p} {kw}" for kw in ch.keywords[:2] for p in PREFIXES.get(ch.language, PREFIXES["en"])]
    key = os.environ.get("YT_API_KEY", "")
    jobs: List[Any] = [youtube_suggest(http, q, ch.language) for q in queries]
    top_ids = [v["id"] for v in videos if v.get("id")][:3] if key else []
    jobs += [top_comments(http, key, vid) for vid in top_ids]
    res = await asyncio.gather(*jobs, return_exceptions=True)
    sugg: List[str] = []
    comments: List[str] = []
    for i, r in enumerate(res):
        if isinstance(r, Exception):
            log(f"segnale pubblico {i} non disponibile: {_short(r)}")
            continue
        (sugg if i < len(queries) else comments).extend(r)
    return {"suggestions": list(dict.fromkeys(sugg))[:60], "comments": comments[:45]}


def _short(e: Exception) -> str:
    return f"{type(e).__name__}: {str(e)[:120]}"
