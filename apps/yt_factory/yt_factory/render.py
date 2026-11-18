"""Team produzione: sfondi, sottotitoli animati, montaggio ffmpeg, miniature.

Video verticali 1080x1920 (Shorts) o orizzontali 1920x1080 (video lunghi):
- sfondo per scena: clip stock gratuite Pexels (se PEXELS_API_KEY) altrimenti grafica generata con effetto Ken Burns;
- sottotitoli "parola evidenziata" sincronizzati con la voce (stile Shorts virali), testo a schermo per scena;
- musica di sottofondo opzionale da assets/music/*.mp3 (solo brani royalty-free, es. YouTube Audio Library).
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import random
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .tts import Word

SIZES = {"short": (1080, 1920), "long": (1920, 1080)}
FPS = 30
FONT_NAME = "DejaVu Sans"  # presente su Ubuntu/GitHub Actions; usata da libass via fontconfig


# --------------------------------------------------------------------------- utilità
def _rgb(hex_color: str) -> Tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _ass_color(hex_color: str) -> str:
    r, g, b = _rgb(hex_color)
    return f"&H00{b:02X}{g:02X}{r:02X}"


def _ass_inline(hex_color: str) -> str:
    r, g, b = _rgb(hex_color)
    return f"&H{b:02X}{g:02X}{r:02X}&"


def _font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        path = subprocess.run(["fc-match", "-f", "%{file}", "sans:bold"], capture_output=True, text=True).stdout
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default(size)


def _ts(t: float) -> str:
    t = max(t, 0)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _esc(text: str) -> str:
    return text.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", " ")


async def _run(*cmd: str) -> None:
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
    _, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"{cmd[0]} fallito: {err.decode(errors='replace')[-800:]}")


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


# --------------------------------------------------------------------------- tempi delle scene
def scene_times(scenes: Sequence[Dict[str, Any]], words: Sequence[Word], total: float) -> List[Tuple[float, float]]:
    """Divide la timeline fra le scene in proporzione ai caratteri, agganciandosi ai confini delle parole."""
    lengths = [max(len(s.get("text", "")), 1) for s in scenes]
    tot, cum, bounds = sum(lengths), 0, [0.0]
    n = len(words)
    for ln in lengths[:-1]:
        cum += ln
        idx = min(max(round(cum / tot * n), 1), n - 1) if n > 1 else 0
        cut = words[idx].start if n > 1 else total * cum / tot
        bounds.append(max(cut, bounds[-1] + 0.5))
    bounds.append(max(total, bounds[-1] + 0.5))
    return [(bounds[i], bounds[i + 1]) for i in range(len(scenes))]


# --------------------------------------------------------------------------- sottotitoli ASS
def build_ass(words: Sequence[Word], scenes: Sequence[Dict[str, Any]], times: Sequence[Tuple[float, float]],
              fmt: str, palette: Sequence[str], out: Path) -> None:
    w, h = SIZES[fmt]
    accent = _ass_color(palette[-1])
    accent_inline = _ass_inline(palette[-1])
    big = 92 if fmt == "short" else 64
    group = 3 if fmt == "short" else 6
    cap_y = int(h * 0.68) if fmt == "short" else int(h * 0.86)
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {w}", f"PlayResY: {h}", "WrapStyle: 0", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
        f"Style: Cap,{FONT_NAME},{big},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,7,3,5,60,60,0,1",
        f"Style: Top,{FONT_NAME},{int(big * 0.75)},{accent},&H00FFFFFF,&H00000000,&HA0000000,-1,0,0,0,100,100,0,0,3,18,0,8,80,80,{int(h * 0.12)},1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    # testo a schermo per scena (in alto)
    for s, (a, b) in zip(scenes, times):
        txt = _esc(str(s.get("on_screen", "")).upper())
        if txt:
            lines.append(f"Dialogue: 1,{_ts(a)},{_ts(b)},Top,,0,0,0,,{{\\fad(150,150)}}{txt}")
    # sottotitoli a gruppi, parola attiva colorata e leggermente ingrandita
    groups: List[List[Word]] = []
    for i, wd in enumerate(words):  # nuovo gruppo se pieno, a fine frase o dopo una pausa della voce
        prev = words[i - 1] if i else None
        if not groups or len(groups[-1]) >= group or (prev and (prev.text[-1:] in ".?!:" or wd.start - prev.end > 0.3)):
            groups.append([])
        groups[-1].append(wd)
    for gi, grp in enumerate(groups):
        nxt = groups[gi + 1][0].start if gi + 1 < len(groups) else grp[-1].end + 0.4
        for wi, cur in enumerate(grp):
            start = cur.start
            end = grp[wi + 1].start if wi + 1 < len(grp) else nxt
            parts = []
            for wj, ww in enumerate(grp):
                t = _esc(ww.text.upper())
                parts.append(f"{{\\c{accent_inline}\\fscx110\\fscy110}}{t}{{\\c&H00FFFFFF&\\fscx100\\fscy100}}" if wj == wi else t)
            lines.append(f"Dialogue: 2,{_ts(start)},{_ts(end)},Cap,,0,0,0,,{{\\pos({w // 2},{cap_y})}}" + " ".join(parts))
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- sfondi
def generated_background(fmt: str, palette: Sequence[str], seed: str, out: Path) -> Path:
    """Grafica astratta (gradiente + forme sfocate) leggermente più grande del video per il Ken Burns."""
    w, h = SIZES[fmt]
    W, H = int(w * 1.15), int(h * 1.15)
    rnd = random.Random(seed)
    c1, c2, acc = (_rgb(c) for c in (palette[0], palette[1 % len(palette)], palette[-1]))
    img = Image.new("RGB", (W, H), c1)
    d = ImageDraw.Draw(img)
    for y in range(H):  # gradiente verticale
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
    img = Image.alpha_composite(img.convert("RGBA"), blobs).convert("RGB")
    img.save(out, quality=92)
    return out


async def pexels_clip(http: httpx.AsyncClient, query: str, fmt: str, cache: Path) -> Optional[Path]:
    key = os.environ.get("PEXELS_API_KEY")
    if not key or not query:
        return None
    cache.mkdir(parents=True, exist_ok=True)
    tag = hashlib.sha1(f"{fmt}:{query}".encode()).hexdigest()[:12]
    hits = sorted(cache.glob(f"{tag}_*.mp4"))
    if hits:
        return random.choice(hits)
    orient = "portrait" if fmt == "short" else "landscape"
    r = await http.get("https://api.pexels.com/videos/search", headers={"Authorization": key},
                       params={"query": query, "orientation": orient, "size": "medium", "per_page": 6})
    if r.status_code != 200:
        return None
    target = SIZES[fmt][1]
    paths: List[Path] = []
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
        paths.append(p)
    return random.choice(paths) if paths else None


# --------------------------------------------------------------------------- montaggio
async def render(*, scenes: List[Dict[str, Any]], words: List[Word], audio: Path, out: Path, fmt: str,
                 palette: Sequence[str], workdir: Path, http: httpx.AsyncClient, stock_cache: Path,
                 music_dir: Optional[Path] = None) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    w, h = SIZES[fmt]
    total = duration(audio) + 0.3
    times = scene_times(scenes, words, total)
    clips: List[Path] = []
    for i, (scene, (a, b)) in enumerate(zip(scenes, times)):
        d = b - a
        clip = workdir / f"scene_{i:02d}.mp4"
        stock = await pexels_clip(http, str(scene.get("visual", "")), fmt, stock_cache)
        common = ["-r", str(FPS), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"]
        if stock:
            vf = (f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={FPS},"
                  "eq=brightness=-0.10:saturation=1.1,format=yuv420p")
            await _run("ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "-1", "-i", str(stock),
                       "-t", f"{d:.3f}", "-vf", vf, *common, str(clip))
        else:
            img = generated_background(fmt, palette, f"{out.stem}-{i}", workdir / f"bg_{i:02d}.jpg")
            direction = "(iw-ow)*t/{d}" if i % 2 == 0 else "(iw-ow)*(1-t/{d})"
            vf = (f"crop={w}:{h}:x='{direction.format(d=f'{d:.3f}')}':y='(ih-oh)*t/{d:.3f}',fps={FPS},format=yuv420p")
            await _run("ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(img),
                       "-t", f"{d:.3f}", "-vf", vf, *common, str(clip))
        clips.append(clip)

    concat = workdir / "concat.txt"
    concat.write_text("".join(f"file '{c.resolve()}'\n" for c in clips))
    joined = workdir / "joined.mp4"
    await _run("ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(joined))

    ass = workdir / "captions.ass"
    build_ass(words, scenes, times, fmt, palette, ass)
    ass_arg = str(ass.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")

    music = sorted(music_dir.glob("*.mp3")) if music_dir and music_dir.exists() else []
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(joined), "-i", str(audio)]
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(random.choice(music))]
        audio_filter = "[1:a]volume=1.0[v];[2:a]volume=0.08[m];[v][m]amix=inputs=2:duration=first:dropout_transition=0[aout]"
    else:
        audio_filter = "[1:a]anull[aout]"
    cmd += ["-filter_complex", f"[0:v]subtitles='{ass_arg}'[vout];{audio_filter}",
            "-map", "[vout]", "-map", "[aout]", "-t", f"{total:.3f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-movflags", "+faststart", str(out)]
    await _run(*cmd)
    if not os.environ.get("YTF_KEEP_WORK"):
        shutil.rmtree(workdir, ignore_errors=True)
    return out


def thumbnail(text: str, palette: Sequence[str], out: Path, seed: str = "") -> Path:
    """Miniatura 1280x720: sfondo del canale + testo enorme con contorno (usata per i video lunghi)."""
    tmp = out.with_suffix(".bg.jpg")
    bg = Image.open(generated_background("long", palette, seed or text, tmp)).resize((1280, 720))
    tmp.unlink(missing_ok=True)
    d = ImageDraw.Draw(bg)
    words = (text or "").upper().split()
    lines, cur = [], ""
    for wd in words:  # a capo ogni ~12 caratteri
        if len(cur) + len(wd) > 12 and cur:
            lines.append(cur)
            cur = wd
        else:
            cur = f"{cur} {wd}".strip()
    if cur:
        lines.append(cur)
    lines = lines[:3] or [" "]
    size = 150 if len(lines) <= 2 else 118
    font = _font(size)
    y = (720 - len(lines) * (size + 14)) // 2
    acc = _rgb(palette[-1])
    for i, ln in enumerate(lines):
        tw = d.textlength(ln, font=font)
        d.text(((1280 - tw) / 2, y), ln, font=font, fill=acc if i == 0 else (255, 255, 255),
               stroke_width=10, stroke_fill=(0, 0, 0))
        y += size + 14
    bg.save(out, "PNG")
    return out
