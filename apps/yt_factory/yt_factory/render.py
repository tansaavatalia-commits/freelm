"""Reparto montaggio: inquadrature dinamiche, sottotitoli animati, barra di avanzamento, effetti sonori, ffmpeg.

Tecniche di ritenzione dei canali Shorts migliori:
- un taglio ogni ~2.8 s (`shot_seconds`), alternando immagini AI in movimento (zoom in/out, panoramiche) e clip stock;
- sottotitoli a gruppi corti, parola attiva colorata con effetto "pop";
- testo a schermo per scena in alto, barra di avanzamento in basso;
- "whoosh" sintetico (nessun copyright) a ogni cambio di scena, musica royalty-free opzionale sotto la voce.
"""
from __future__ import annotations

import asyncio
import math
import os
import random
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

from .tts import Word
from .visuals import SIZES, _rgb, generated_background

FPS = 30
FONT_NAME = "DejaVu Sans"  # presente su Ubuntu/GitHub Actions; usata da libass via fontconfig
MOTIONS = ("zoom_in", "pan_right", "zoom_out", "pan_up", "pan_left")
# sottofondi generati con ffmpeg (nessun brano protetto): drone cupo per i misteri, pulsazione morbida per la finanza
AMBIENT = {
    "drone": "aevalsrc='0.05*sin(2*PI*55*t)*(0.8+0.2*sin(2*PI*0.1*t))+0.035*sin(2*PI*82.41*t)"
             "+0.02*sin(2*PI*110.5*t)*(0.5+0.5*sin(2*PI*0.07*t))':s=44100,lowpass=f=900,aecho=0.8:0.7:400:0.3",
    "pulse": "aevalsrc='0.06*sin(2*PI*65.4*t)*exp(-6*mod(t,0.5))+0.025*sin(2*PI*196*t)*(0.5+0.5*sin(2*PI*0.25*t))'"
             ":s=44100,lowpass=f=1500",
}


# --------------------------------------------------------------------------- utilità
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


# --------------------------------------------------------------------------- tempi
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


def plan_shots(times: Sequence[Tuple[float, float]], assets: Sequence[Dict[str, Optional[Path]]],
               shot_seconds: float) -> List[Dict[str, Any]]:
    """Spezza ogni scena in inquadrature brevi alternando immagine AI (movimenti diversi) e clip stock."""
    shots: List[Dict[str, Any]] = []
    m = 0
    for i, (a, b) in enumerate(times):
        n = max(1, math.ceil((b - a) / shot_seconds - 0.15))
        step = (b - a) / n
        asset = assets[i] if i < len(assets) else {}
        # immagine principale (foto reale o AI) sui tagli pari; sui dispari clip stock o seconda immagine
        alts = [x for x in (asset.get("stock"), asset.get("image2")) if x is not None]
        for k in range(n):
            alt = alts[(k // 2) % len(alts)] if alts and (k % 2 == 1 or asset.get("image") is None) else None
            path = alt if alt is not None else asset.get("image")
            is_video = alt is not None and alt == asset.get("stock")
            shots.append({"scene": i, "start": a + k * step, "end": a + (k + 1) * step,
                          "kind": "video" if is_video else "image", "path": path,
                          "motion": MOTIONS[m % len(MOTIONS)]})
            m += 1
    return shots


# --------------------------------------------------------------------------- sottotitoli ASS
def build_ass(words: Sequence[Word], scenes: Sequence[Dict[str, Any]], times: Sequence[Tuple[float, float]],
              fmt: str, palette: Sequence[str], out: Path) -> None:
    w, h = SIZES[fmt]
    accent = _ass_color(palette[-1])
    accent_inline = _ass_inline(palette[-1])
    big = 84 if fmt == "short" else 60
    group = 3 if fmt == "short" else 6
    cap_y = int(h * 0.74) if fmt == "short" else int(h * 0.86)  # sotto il centro: il soggetto resta visibile
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {w}", f"PlayResY: {h}", "WrapStyle: 0", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
        f"Style: Cap,{FONT_NAME},{big},&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,-1,0,0,0,100,100,0,0,1,8,4,5,60,60,0,1",
        f"Style: Top,{FONT_NAME},{int(big * 0.72)},{accent},&H00FFFFFF,&H00000000,&HA0000000,-1,0,0,0,100,100,0,0,3,18,0,8,80,80,{int(h * 0.11)},1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for s, (a, b) in zip(scenes, times):
        txt = _esc(str(s.get("on_screen", "")).upper())
        if txt:
            lines.append(f"Dialogue: 1,{_ts(a)},{_ts(b)},Top,,0,0,0,,"
                         f"{{\\fad(120,120)\\fscx70\\fscy70\\t(0,140,\\fscx100\\fscy100)}}{txt}")
    groups: List[List[Word]] = []
    for i, wd in enumerate(words):  # nuovo gruppo se pieno, a fine frase o dopo una pausa della voce
        prev = words[i - 1] if i else None
        if not groups or len(groups[-1]) >= group or (prev and (prev.text[-1:] in ".?!:" or wd.start - prev.end > 0.3)):
            groups.append([])
        groups[-1].append(wd)
    for gi, grp in enumerate(groups):
        nxt = groups[gi + 1][0].start if gi + 1 < len(groups) else grp[-1].end + 0.4
        for wi, cur in enumerate(grp):
            end = grp[wi + 1].start if wi + 1 < len(grp) else nxt
            pop = "\\fscx80\\fscy80\\t(0,90,\\fscx100\\fscy100)" if wi == 0 else ""
            parts = []
            for wj, ww in enumerate(grp):
                t = _esc(ww.text.upper())
                parts.append(f"{{\\c{accent_inline}\\fscx115\\fscy115}}{t}{{\\c&HFFFFFF&\\fscx100\\fscy100}}"
                             if wj == wi else t)
            lines.append(f"Dialogue: 2,{_ts(cur.start)},{_ts(end)},Cap,,0,0,0,,"
                         f"{{\\pos({w // 2},{cap_y}){pop}}}" + " ".join(parts))
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- inquadrature
def _image_filter(motion: str, d: float, fmt: str) -> str:
    w, h = SIZES[fmt]
    n = max(int(d * FPS), 1)
    if motion in ("zoom_in", "zoom_out"):
        z = f"1+0.16*on/{n}" if motion == "zoom_in" else f"1.16-0.16*on/{n}"
        return (f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
                f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={n}:s={w}x{h}:fps={FPS},format=yuv420p")
    x, y = {"pan_right": ("(iw-ow)*t/{d}", "(ih-oh)/2"), "pan_left": ("(iw-ow)*(1-t/{d})", "(ih-oh)/2"),
            "pan_up": ("(iw-ow)/2", "(ih-oh)*(1-t/{d})")}[motion]
    dd = f"{d:.3f}"
    return (f"scale={int(w * 1.15)}:{int(h * 1.15)}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h}:x='{x.format(d=dd)}':y='{y.format(d=dd)}',fps={FPS},format=yuv420p")


async def shot_clip(shot: Dict[str, Any], fmt: str, palette: Sequence[str], workdir: Path, idx: int) -> Path:
    w, h = SIZES[fmt]
    d = shot["end"] - shot["start"]
    clip = workdir / f"shot_{idx:03d}.mp4"
    enc = ["-t", f"{d:.3f}", "-r", str(FPS), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
           "-pix_fmt", "yuv420p", str(clip)]
    if shot["kind"] == "video" and shot["path"]:
        vf = (f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={FPS},"
              "eq=brightness=-0.08:saturation=1.12,format=yuv420p")
        await _run("ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "-1", "-i", str(shot["path"]), "-vf", vf, *enc)
        return clip
    img = shot["path"] or generated_background(fmt, palette, f"{workdir.name}-{shot['scene']}",
                                               workdir / f"bg_{shot['scene']:02d}.jpg")
    vf = _image_filter(shot["motion"], d, fmt) + ",eq=contrast=1.05:saturation=1.08"
    loop = [] if shot["motion"].startswith("zoom") else ["-loop", "1"]
    await _run("ffmpeg", "-y", "-loglevel", "error", *loop, "-i", str(img), "-vf", vf, *enc)
    return clip


async def render(*, scenes: List[Dict[str, Any]], words: List[Word], audio: Path, out: Path, fmt: str,
                 palette: Sequence[str], workdir: Path, assets: Sequence[Dict[str, Optional[Path]]],
                 shot_seconds: float = 2.8, music_dir: Optional[Path] = None, ambient: str = "none",
                 music_track: Optional[Path] = None) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    w, h = SIZES[fmt]
    total = duration(audio) + 0.35
    times = scene_times(scenes, words, total)
    shots = plan_shots(times, assets, shot_seconds if fmt == "short" else shot_seconds * 2)
    sem = asyncio.Semaphore(3)

    async def one(i: int, s: Dict[str, Any]) -> Path:
        async with sem:
            return await shot_clip(s, fmt, palette, workdir, i)

    clips = await asyncio.gather(*(one(i, s) for i, s in enumerate(shots)))
    concat = workdir / "concat.txt"
    concat.write_text("".join(f"file '{c.resolve()}'\n" for c in clips))
    joined = workdir / "joined.mp4"
    await _run("ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(joined))

    ass = workdir / "captions.ass"
    build_ass(words, scenes, times, fmt, palette, ass)
    ass_arg = str(ass.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    whoosh = workdir / "whoosh.wav"
    await _run("ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
               "anoisesrc=d=0.45:c=pink:a=0.6,highpass=f=500,lowpass=f=7000,"
               "afade=t=in:d=0.15,afade=t=out:st=0.15:d=0.3", "-ar", "44100", "-ac", "2", str(whoosh))

    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(joined), "-i", str(audio), "-i", str(whoosh)]
    cuts = [a for a, _ in times[1:]]
    # voce divisa in due: una va nel mix, l'altra "comanda" il ducking della musica (sidechain)
    a_graph = ["[1:a]aresample=44100,aformat=channel_layouts=stereo,volume=1.0,asplit=2[voice][vkey]"]
    mix = ["[voice]"]
    if cuts:
        a_graph.append(f"[2:a]asplit={len(cuts)}" + "".join(f"[w{i}]" for i in range(len(cuts))))
        for i, t in enumerate(cuts):
            ms = max(int((t - 0.2) * 1000), 0)
            a_graph.append(f"[w{i}]adelay={ms}|{ms},volume=0.22[wd{i}]")
            mix.append(f"[wd{i}]")
    local = sorted(music_dir.glob("*.mp3")) if music_dir and music_dir.exists() else []
    track = music_track or (random.choice(local) if local else None)
    fades = f"afade=t=in:d=1.2,afade=t=out:st={max(total - 1.8, 0):.2f}:d=1.8"
    if track:  # brano vero: si abbassa da solo quando parla la voce
        cmd += ["-stream_loop", "-1", "-i", str(track)]
        a_graph.append(f"[3:a]aresample=44100,aformat=channel_layouts=stereo,atrim=0:{total:.3f},{fades},volume=0.32[mraw]")
        a_graph.append("[mraw][vkey]sidechaincompress=threshold=0.03:ratio=10:attack=15:release=350:makeup=1[music]")
        mix.append("[music]")
    elif ambient in AMBIENT:  # sottofondo sintetico, zero copyright
        cmd += ["-f", "lavfi", "-t", f"{total:.3f}", "-i", AMBIENT[ambient]]
        a_graph.append(f"[3:a]aresample=44100,aformat=channel_layouts=stereo,{fades},volume=0.5[music]")
        a_graph.append("[vkey]anullsink")
        mix.append("[music]")
    else:
        a_graph.append("[vkey]anullsink")
    # loudness standard delle piattaforme (-14 LUFS, picchi sotto -1.5 dB): nessun video troppo basso o distorto
    a_graph.append("".join(mix) + f"amix=inputs={len(mix)}:duration=first:dropout_transition=0:normalize=0,"
                   "loudnorm=I=-14:TP=-1.5:LRA=11[aout]")
    bar_h = 14 if fmt == "short" else 8
    v_graph = (f"[0:v]subtitles='{ass_arg}'[sub];color=c={palette[-1]}:s={w}x{bar_h}:r={FPS}[bar];"
               f"[sub][bar]overlay=x='-w+w*t/{total:.3f}':y=H-h:shortest=1[vout]")
    cmd += ["-filter_complex", v_graph + ";" + ";".join(a_graph), "-map", "[vout]", "-map", "[aout]",
            "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-movflags", "+faststart", str(out)]
    await _run(*cmd)
    if not os.environ.get("YTF_KEEP_WORK"):
        shutil.rmtree(workdir, ignore_errors=True)
    return out


# --------------------------------------------------------------------------- miniatura
def thumbnail(text: str, palette: Sequence[str], out: Path, seed: str = "", background: Optional[Path] = None) -> Path:
    """Miniatura 1280x720: immagine della scena più forte (o sfondo del canale) + testo enorme con contorno."""
    if background and background.exists():
        bg = Image.open(background).convert("RGB")
        scale = max(1280 / bg.width, 720 / bg.height)
        bg = bg.resize((int(bg.width * scale) + 1, int(bg.height * scale) + 1))
        left, top = (bg.width - 1280) // 2, (bg.height - 720) // 2
        bg = bg.crop((left, top, left + 1280, top + 720))
        shade = Image.new("RGBA", bg.size, (0, 0, 0, 90))
        bg = Image.alpha_composite(bg.convert("RGBA"), shade).convert("RGB")
    else:
        tmp = out.with_suffix(".bg.jpg")
        bg = Image.open(generated_background("long", palette, seed or text, tmp)).resize((1280, 720))
        tmp.unlink(missing_ok=True)
    d = ImageDraw.Draw(bg)
    words = (text or "").upper().split()
    lines, cur = [], ""
    for wd in words:
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
