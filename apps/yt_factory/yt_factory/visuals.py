"""Reparto art: procura un'immagine/clip per ogni scena.

Ordine di preferenza per ogni inquadratura:
1. FOTO REALE del soggetto citato (luogo, reperto, documento) con licenza libera CC0 / pubblico dominio / CC BY,
   da Openverse (Wikimedia Commons, Flickr...): lo spettatore vede la cosa vera; i crediti CC BY finiscono in descrizione;
2. clip video stock Pexels (gratis con PEXELS_API_KEY), alternate alle immagini per varietà;
3. immagine AI originale dal prompt dell'Art Director (Pollinations, gratis, senza chiave);
4. grafica astratta generata localmente (non fallisce mai).
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import os
import random
import urllib.parse
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

import httpx
from PIL import Image, ImageDraw, ImageFilter

SIZES = {"short": (1080, 1920), "long": (1920, 1080)}
_POLL_SEM: Optional[asyncio.Semaphore] = None  # il tier anonimo accetta una richiesta alla volta


def _rgb(hex_color: str) -> Tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def generated_background(fmt: str, palette: Sequence[str], seed: str, out: Path) -> Path:
    """Grafica astratta (gradiente + forme sfocate), un po' più grande del video per il movimento."""
    w, h = SIZES[fmt]
    W, H = int(w * 1.15), int(h * 1.15)
    rnd = random.Random(seed)
    c1, c2, acc = (_rgb(c) for c in (palette[0], palette[1 % len(palette)], palette[-1]))
    img = Image.new("RGB", (W, H), c1)
    d = ImageDraw.Draw(img)
    for y in range(H):
        k = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(c1[i] * (1 - k) + c2[i] * k) for i in range(3)))
    blobs = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(blobs)
    for _ in range(6):
        r = rnd.randint(W // 8, W // 3)
        x, y = rnd.randint(0, W), rnd.randint(0, H)
        col = acc if rnd.random() < 0.4 else c2
        bd.ellipse([x - r, y - r, x + r, y + r], fill=(*col, rnd.randint(40, 110)))
    blobs = blobs.filter(ImageFilter.GaussianBlur(W // 12))
    Image.alpha_composite(img.convert("RGBA"), blobs).convert("RGB").save(out, quality=92)
    return out


async def ai_image(http: httpx.AsyncClient, prompt: str, style: str, fmt: str, seed: int, cache: Path) -> Optional[Path]:
    """Immagine originale da Pollinations (modello Flux). Ritaglia la filigrana in basso e porta alla risoluzione video."""
    global _POLL_SEM
    if not prompt or os.environ.get("YTF_NO_AI_IMAGES"):
        return None
    cache.mkdir(parents=True, exist_ok=True)
    full = f"{prompt}, {style}, no text, no watermark, vertical composition" if fmt == "short" \
        else f"{prompt}, {style}, no text, no watermark, wide cinematic composition"
    out = cache / f"ai_{hashlib.sha1(f'{fmt}:{seed}:{full}'.encode()).hexdigest()[:16]}.jpg"
    if out.exists():
        return out
    gw, gh = (768, 1408) if fmt == "short" else (1408, 768)
    url = "https://image.pollinations.ai/prompt/" + urllib.parse.quote(full[:600])
    params = {"width": gw, "height": gh + 64, "seed": seed, "model": "flux", "nologo": "true"}
    if os.environ.get("POLLINATIONS_TOKEN"):  # opzionale: token gratuito = limiti più alti, niente filigrana
        params["token"] = os.environ["POLLINATIONS_TOKEN"]
    _POLL_SEM = _POLL_SEM or asyncio.Semaphore(int(os.environ.get("YTF_IMAGE_CONCURRENCY", "1")))
    async with _POLL_SEM:
        for attempt in range(3):
            try:
                r = await http.get(url, params=params, timeout=90)
            except httpx.HTTPError:
                r = None
            if r is not None and r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
                img = Image.open(io.BytesIO(r.content)).convert("RGB")
                img = img.crop((0, 0, img.width, img.height - int(img.height * 0.045)))  # via la filigrana
                w, h = SIZES[fmt]
                scale = max(w * 1.15 / img.width, h * 1.15 / img.height)
                img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
                img.save(out, quality=93)
                return out
            await asyncio.sleep(4 * (attempt + 1))
            if attempt == 1:  # prompt più corto: alcuni prompt lunghi vengono rifiutati
                url = "https://image.pollinations.ai/prompt/" + urllib.parse.quote(f"{prompt[:160]}, {style[:80]}")
    return None


OPENVERSE = "https://api.openverse.org/v1/images/"
# niente CC BY-SA/NC/ND: un video monetizzato non può rispettarle
SAFE_LICENSES = "cc0,pdm,by"


async def real_photo(http: httpx.AsyncClient, query: str, fmt: str, cache: Path, pick: int = 0) -> Optional[Dict[str, str]]:
    """Foto reale con licenza libera. Restituisce {"path", "credit"} (credit vuoto per CC0/pubblico dominio)."""
    if not query or os.environ.get("YTF_OFFLINE"):
        return None
    cache.mkdir(parents=True, exist_ok=True)
    words = query.split()
    results: list = []
    for n in dict.fromkeys([len(words), 4, 3, 2]):  # query troppo specifica = 0 risultati: si accorcia (mai a 1 parola)
        if n > len(words) or n < min(2, len(words)):
            continue
        r = await http.get(OPENVERSE, params={"q": " ".join(words[:n]), "license": SAFE_LICENSES, "page_size": 8,
                                              "mature": "false"}, headers={"User-Agent": "yt-factory/0.3"})
        if r.status_code == 200 and r.json().get("results"):
            results = r.json()["results"]
            break
    w, h = SIZES[fmt]
    key = [x.lower() for x in words if len(x) > 3]
    need = min(2, len(key))

    def relevant(x: Dict[str, Any]) -> bool:
        """La foto deve parlare del soggetto: almeno 2 parole chiave nel TITOLO (i tag sono troppo larghi:
        "Woolpit Steam Rally, Vintage Tractors" ha il tag Suffolk ma non c'entra coi bambini verdi)."""
        text = str(x.get("title", "")).lower()
        return sum(k in text for k in key) >= need

    good = [x for x in results if relevant(x)]
    good = [x for x in good
            if (x.get("width") or 0) >= 1000 and (x.get("height") or 0) >= 650
            and (x.get("width") or 1) / (x.get("height") or 1) < 4]  # niente banner panoramici
    for item in good[pick % max(len(good), 1):] + good[: pick % max(len(good), 1)]:
        out = cache / f"photo_{hashlib.sha1(item['url'].encode()).hexdigest()[:16]}.jpg"
        if not out.exists():
            try:
                img_r = await http.get(item["url"], headers={"User-Agent": "yt-factory/0.3"}, timeout=60)
                if img_r.status_code != 200 or not img_r.headers.get("content-type", "").startswith("image"):
                    continue
                img = Image.open(io.BytesIO(img_r.content)).convert("RGB")
            except (httpx.HTTPError, OSError):
                continue
            scale = max(w * 1.15 / img.width, h * 1.15 / img.height)
            if scale > 1:  # foto piccola: ingrandisci (meglio un po' morbida che la grafica astratta)
                img = img.resize((int(img.width * scale) + 1, int(img.height * scale) + 1), Image.LANCZOS)
            img.save(out, quality=93)
        lic = str(item.get("license", "")).lower()
        credit = "" if lic in ("cc0", "pdm") else (
            f"\"{item.get('title', 'photo')}\" by {item.get('creator') or 'unknown'}, CC BY "
            f"{item.get('license_version', '')} ({item.get('foreign_landing_url') or item['url']})")
        return {"path": str(out), "credit": credit}
    return None


async def pexels_clip(http: httpx.AsyncClient, query: str, fmt: str, cache: Path, pick: int = 0) -> Optional[Path]:
    key = os.environ.get("PEXELS_API_KEY")
    if not key or not query:
        return None
    cache.mkdir(parents=True, exist_ok=True)
    tag = hashlib.sha1(f"{fmt}:{query}".encode()).hexdigest()[:12]
    hits = sorted(cache.glob(f"{tag}_*.mp4"))
    if not hits:
        orient = "portrait" if fmt == "short" else "landscape"
        r = await http.get("https://api.pexels.com/videos/search", headers={"Authorization": key},
                           params={"query": query, "orientation": orient, "size": "medium", "per_page": 6})
        if r.status_code != 200:
            return None
        target = SIZES[fmt][1]
        for i, v in enumerate(r.json().get("videos", [])[:3]):
            files = [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4" and f.get("height")]
            if not files:
                continue
            best = min(files, key=lambda f: abs(f["height"] - target))
            p = cache / f"{tag}_{i}.mp4"
            async with http.stream("GET", best["link"]) as resp:
                if resp.status_code != 200:
                    continue
                with open(p, "wb") as fh:
                    async for chunk in resp.aiter_bytes():
                        fh.write(chunk)
            hits.append(p)
    return hits[pick % len(hits)] if hits else None
