"""Team pubblicazione + analytics: YouTube Data API v3 e YouTube Analytics API, via httpx (nessuna SDK Google).

Credenziali (variabili d'ambiente, mai nel codice):
  YT_CLIENT_ID / YT_CLIENT_SECRET          client OAuth "Desktop app" del progetto Google Cloud
  YT_REFRESH_TOKEN_<CANALE>                uno per canale, ottenuto con `python -m yt_factory auth --channel <id>`
  (opzionale) YT_CLIENT_ID_<CANALE> / YT_CLIENT_SECRET_<CANALE> per usare un progetto (= quota) diverso per canale.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from .config import Channel

TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
API = "https://www.googleapis.com/youtube/v3"
UPLOAD = "https://www.googleapis.com/upload/youtube/v3/videos"
ANALYTICS = "https://youtubeanalytics.googleapis.com/v2/reports"
SCOPES = " ".join([
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",       # miniature, commenti
    "https://www.googleapis.com/auth/yt-analytics.readonly",   # ore di visualizzazione, views Shorts
])


class YouTubeError(RuntimeError):
    pass


def credentials(ch: Channel) -> Dict[str, str]:
    return {"client_id": ch.env("YT_CLIENT_ID"), "client_secret": ch.env("YT_CLIENT_SECRET"),
            "refresh_token": ch.env("YT_REFRESH_TOKEN")}


def configured(ch: Channel) -> bool:
    return all(credentials(ch).values())


def project_of(ch: Channel) -> str:
    """Identifica il progetto Google (la quota è per progetto, non per canale)."""
    return (ch.env("YT_CLIENT_ID") or "none")[:16]


class YouTube:
    def __init__(self, ch: Channel, http: httpx.AsyncClient):
        self.ch, self.http = ch, http
        self._token: Optional[str] = None

    async def token(self) -> str:
        if self._token:
            return self._token
        c = credentials(self.ch)
        if not all(c.values()):
            raise YouTubeError(f"credenziali YouTube mancanti per il canale {self.ch.id} (vedi README, passo 3)")
        r = await self.http.post(TOKEN_URL, data={**c, "grant_type": "refresh_token"})
        if r.status_code != 200:
            raise YouTubeError(f"refresh token rifiutato ({r.status_code}): {r.text[:200]} — rifai `auth`")
        self._token = r.json()["access_token"]
        return self._token

    async def _h(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {await self.token()}"}

    # ------------------------------------------------------------------ upload
    async def upload(self, path: Path, *, title: str, description: str, tags: List[str], category_id: str,
                     language: str, privacy: str, publish_at: Optional[str]) -> str:
        status: Dict[str, Any] = {
            "privacyStatus": "private" if publish_at else privacy,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,  # dichiarazione contenuti generati/alterati con AI (richiesta da YouTube)
            "embeddable": True,
        }
        if publish_at:
            status["publishAt"] = publish_at
        body = {"snippet": {"title": title[:100], "description": description[:4900], "tags": _tags(tags),
                            "categoryId": category_id, "defaultLanguage": language, "defaultAudioLanguage": language},
                "status": status}
        size = path.stat().st_size
        r = await self.http.post(UPLOAD, params={"uploadType": "resumable", "part": "snippet,status"},
                                 headers={**await self._h(), "X-Upload-Content-Type": "video/mp4",
                                          "X-Upload-Content-Length": str(size), "Content-Type": "application/json"},
                                 content=json.dumps(body))
        if r.status_code != 200:
            raise YouTubeError(f"avvio upload fallito ({r.status_code}): {r.text[:300]}")
        session = r.headers["Location"]
        r = await self.http.put(session, content=path.read_bytes(),
                                headers={"Content-Type": "video/mp4"}, timeout=httpx.Timeout(600.0))
        if r.status_code not in (200, 201):
            raise YouTubeError(f"upload fallito ({r.status_code}): {r.text[:300]}")
        return r.json()["id"]

    async def set_thumbnail(self, video_id: str, png: Path) -> None:
        """Richiede canale verificato col telefono; per gli Shorts YouTube sceglie un fotogramma."""
        r = await self.http.post("https://www.googleapis.com/upload/youtube/v3/thumbnails/set",
                                 params={"videoId": video_id}, headers={**await self._h(), "Content-Type": "image/png"},
                                 content=png.read_bytes())
        if r.status_code != 200:
            raise YouTubeError(f"miniatura rifiutata ({r.status_code}): {r.text[:200]}")

    async def comment(self, video_id: str, text: str) -> None:
        """Primo commento del canale (fissarlo in alto si fa da Studio: l'API non lo permette)."""
        body = {"snippet": {"videoId": video_id, "topLevelComment": {"snippet": {"textOriginal": text[:900]}}}}
        r = await self.http.post(f"{API}/commentThreads", params={"part": "snippet"}, headers=await self._h(), json=body)
        if r.status_code != 200:
            raise YouTubeError(f"commento rifiutato ({r.status_code}): {r.text[:200]}")

    # ------------------------------------------------------------------ statistiche
    async def video_stats(self, ids: List[str]) -> Dict[str, Dict[str, int]]:
        out: Dict[str, Dict[str, int]] = {}
        for i in range(0, len(ids), 50):
            r = await self.http.get(f"{API}/videos", params={"part": "statistics", "id": ",".join(ids[i:i + 50])},
                                    headers=await self._h())
            r.raise_for_status()
            for it in r.json().get("items", []):
                s = it.get("statistics", {})
                out[it["id"]] = {k: int(s.get(k, 0)) for k in ("viewCount", "likeCount", "commentCount")}
        return out

    async def channel_stats(self) -> Dict[str, Any]:
        r = await self.http.get(f"{API}/channels", params={"part": "statistics,snippet", "mine": "true"},
                                headers=await self._h())
        r.raise_for_status()
        items = r.json().get("items", [])
        if not items:
            raise YouTubeError("nessun canale associato a questo account")
        s = items[0]["statistics"]
        stats: Dict[str, Any] = {"title": items[0]["snippet"]["title"], "subscribers": int(s.get("subscriberCount", 0)),
                                 "views": int(s.get("viewCount", 0)), "videos": int(s.get("videoCount", 0))}
        stats.update(await self._analytics())
        return stats

    async def _analytics(self) -> Dict[str, Any]:
        """Ore di visualizzazione (long-form, 365 gg) e views Shorts (90 gg): le due vie per il Programma Partner."""
        today = date.today()
        out: Dict[str, Any] = {}
        try:
            r = await self.http.get(ANALYTICS, headers=await self._h(), params={
                "ids": "channel==MINE", "startDate": str(today - timedelta(days=365)), "endDate": str(today),
                "metrics": "views,estimatedMinutesWatched", "dimensions": "creatorContentType"})
            r.raise_for_status()
            rows = {row[0]: row for row in r.json().get("rows", [])}
            long_minutes = sum(row[2] for k, row in rows.items() if k != "SHORTS")
            out["watch_hours_365d"] = round(long_minutes / 60, 1)
            r = await self.http.get(ANALYTICS, headers=await self._h(), params={
                "ids": "channel==MINE", "startDate": str(today - timedelta(days=90)), "endDate": str(today),
                "metrics": "views", "dimensions": "creatorContentType"})
            r.raise_for_status()
            out["shorts_views_90d"] = sum(int(row[1]) for row in r.json().get("rows", []) if row[0] == "SHORTS")
        except httpx.HTTPError as e:
            out["analytics_error"] = str(e)[:200]
        return out


def _tags(tags: List[str]) -> List[str]:
    """YouTube accetta max ~500 caratteri totali di tag."""
    out, total = [], 0
    for t in tags:
        t = t.strip().lstrip("#")
        if t and total + len(t) + 2 <= 480:
            out.append(t)
            total += len(t) + 2
    return out


def ypp_progress(stats: Dict[str, Any]) -> Dict[str, Any]:
    """Avanzamento verso il Programma Partner YouTube (soglie pubbliche, verificate 2025-11)."""
    subs = stats.get("subscribers", 0)
    hours = stats.get("watch_hours_365d", 0)
    shorts = stats.get("shorts_views_90d", 0)
    full = subs >= 1000 and (hours >= 4000 or shorts >= 10_000_000)
    lite = subs >= 500 and (hours >= 3000 or shorts >= 3_000_000)
    return {
        "subscribers": f"{subs:,}/1.000 (livello base: 500)",
        "watch_hours": f"{hours:,}/4.000 in 365 gg (livello base: 3.000)",
        "shorts_views": f"{shorts:,}/10.000.000 in 90 gg (livello base: 3.000.000)",
        "eligible_ads": full,          # entrate pubblicitarie
        "eligible_fan_funding": lite,  # abbonamenti, Super Thanks, Shopping
    }
