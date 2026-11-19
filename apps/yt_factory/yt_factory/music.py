"""Reparto audio: musica di sottofondo vera, gratuita e senza rischi di copyright.

Cerca brani CC0 / pubblico dominio (niente crediti obbligatori, niente reclami Content ID) su Openverse, limitandosi
alle fonti che permettono il download diretto (Wikimedia Commons: compositori CC0 come Rafael Krux o John Bartmann,
registrazioni classiche libere). Freesound è escluso: il suo CDN rifiuta i download fuori dal sito (403).
Solo CC0/PD: le licenze CC BY dei brani musicali si portano dietro a volte registrazioni Content ID degli autori,
che su un canale monetizzato si traducono in reclami.
Ordine: brani tuoi in assets/music/ -> CC0 da Openverse per l'umore del canale -> sottofondo sintetico.
"""
from __future__ import annotations

import hashlib
import os
import random
from pathlib import Path
from typing import List, Optional

import httpx

OPENVERSE_AUDIO = "https://api.openverse.org/v1/audio/"
UA = {"User-Agent": "yt-factory/0.3 (https://github.com/shihabshahrier/freelm)"}
SOURCES = "wikimedia_audio,ccmixter"
NOT_MUSIC = ("vocal", "voice", "speech", "talk", "test", "kitchen", "sounds", "recording of", "interview", "lecture")


async def pick_track(http: httpx.AsyncClient, queries: List[str], min_seconds: float, cache: Path,
                     seed: int = 0, local_dir: Optional[Path] = None) -> Optional[Path]:
    local = sorted(local_dir.glob("*.mp3")) if local_dir and local_dir.exists() else []
    if local:
        return random.Random(seed).choice(local)
    if not queries or os.environ.get("YTF_OFFLINE"):
        return None
    cache.mkdir(parents=True, exist_ok=True)
    rnd = random.Random(seed)
    for q in rnd.sample(queries, len(queries)):
        try:
            r = await http.get(OPENVERSE_AUDIO, params={"q": q, "license": "cc0,pdm",
                                                         "source": SOURCES, "page_size": 20}, headers=UA)
            if r.status_code != 200:
                continue
            tracks = [t for t in r.json().get("results", [])
                      if (t.get("duration") or 0) / 1000 >= min_seconds and t.get("url")
                      and not any(w in str(t.get("title", "")).lower() for w in NOT_MUSIC)]
        except (httpx.HTTPError, ValueError):
            continue
        rnd.shuffle(tracks)
        for t in tracks[:4]:
            out = cache / f"music_{hashlib.sha1(t['url'].encode()).hexdigest()[:14]}.mp3"
            if out.exists() and out.stat().st_size > 50_000:
                return out
            try:
                a = await http.get(t["url"], headers=UA, timeout=90)
            except httpx.HTTPError:
                continue
            if a.status_code == 200 and len(a.content) > 50_000:
                out.write_bytes(a.content)
                return out
    return None
