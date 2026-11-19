"""Reparto controllo qualità: ogni video viene ispezionato prima di poter essere pubblicato (idea da OpenMontage).

Controlli con ffmpeg/ffprobe, nessuna dipendenza in più:
- flussi presenti (video verticale/orizzontale giusto, audio) e durata coerente con la voce;
- schermate nere (blackdetect) e buchi di silenzio nella voce (silencedetect);
- audio distorto (picco a 0 dB) e volume fuori standard;
- "rischio presentazione": troppe scene con la grafica di riserva invece di immagini vere.
I problemi "blocking" impediscono la pubblicazione; gli altri finiscono nel report.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from .visuals import SIZES


def _ffprobe(path: Path) -> Dict[str, Any]:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                         capture_output=True, text=True)
    return json.loads(out.stdout or "{}")


def _ffmpeg_filter_log(path: Path, args: List[str]) -> str:
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), *args, "-f", "null", "-"],
                          capture_output=True, text=True).stderr


def inspect(path: Path, fmt: str, expected_seconds: float, fallback_ratio: float = 0.0) -> Dict[str, Any]:
    issues: List[Dict[str, str]] = []

    def add(level: str, msg: str) -> None:
        issues.append({"level": level, "issue": msg})

    if not path.exists() or path.stat().st_size < 10_000:
        add("blocking", "file video mancante o vuoto")
        return {"ok": False, "issues": issues}
    info = _ffprobe(path)
    streams = info.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    dur = float(info.get("format", {}).get("duration", 0) or 0)
    if not video:
        add("blocking", "nessuna traccia video")
    elif (int(video.get("width", 0)), int(video.get("height", 0))) != SIZES[fmt]:
        add("blocking", f"risoluzione {video.get('width')}x{video.get('height')} invece di {SIZES[fmt]}")
    if not audio:
        add("blocking", "nessuna traccia audio")
    if expected_seconds and abs(dur - expected_seconds) > 2.5:
        add("blocking", f"durata {dur:.1f}s, la voce dura {expected_seconds:.1f}s")
    if fmt == "short" and dur > 180:
        add("blocking", f"{dur:.0f}s: oltre il limite di 3 minuti degli Shorts")

    log = _ffmpeg_filter_log(path, ["-vf", "blackdetect=d=0.4:pic_th=0.97", "-af",
                                    "silencedetect=noise=-42dB:d=1.6,volumedetect"])
    black = sum(float(m) for m in re.findall(r"black_duration:([\d.]+)", log))
    if black > 1.5:
        add("blocking", f"{black:.1f}s di schermo nero")
    elif black > 0.4:
        add("warning", f"{black:.1f}s di schermo nero")
    silences = [] if os.environ.get("YTF_OFFLINE_TTS") else \
        [float(m) for m in re.findall(r"silence_duration: ([\d.]+)", log)]  # in prova la voce è muta per scelta
    if silences and max(silences) > 3.0:
        add("blocking", f"silenzio di {max(silences):.1f}s nella voce")
    elif silences:
        add("warning", f"{len(silences)} pause lunghe nella voce")
    peak = re.search(r"max_volume: (-?[\d.]+) dB", log)
    mean = re.search(r"mean_volume: (-?[\d.]+) dB", log)
    if peak and float(peak.group(1)) >= -0.1:
        add("warning", "picchi audio a 0 dB (possibile distorsione)")
    if mean and float(mean.group(1)) < -30:
        add("warning", f"volume medio molto basso ({mean.group(1)} dB)")
    if os.environ.get("YTF_NO_AI_IMAGES"):
        fallback_ratio = 0.0  # in prova le immagini sono disattivate per scelta
    if fallback_ratio > 0.5:
        add("blocking", f"{fallback_ratio:.0%} delle scene senza immagine vera: sembrerebbe una presentazione")
    elif fallback_ratio > 0.2:
        add("warning", f"{fallback_ratio:.0%} delle scene con grafica di riserva")
    return {"ok": not any(i["level"] == "blocking" for i in issues), "duration": round(dur, 2), "issues": issues}
