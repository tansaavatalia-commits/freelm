"""Reparto art: procura un'immagine/clip per ogni scena.

Ordine di preferenza per ogni inquadratura:
1. clip video stock Pexels (gratis con PEXELS_API_KEY), alternate alle immagini AI per varietà;
2. immagine AI originale generata dal prompt dell'Art Director (Pollinations, gratis, senza chiave);
3. grafica astratta generata localmente (non fallisce mai).
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import os
import random
import urllib.parse
from pathlib import Path
from typing import Optional, Sequence, Tuple

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
