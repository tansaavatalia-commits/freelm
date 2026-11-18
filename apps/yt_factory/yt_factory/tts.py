"""Voce fuori campo gratuita (Microsoft Edge TTS, voci neurali) con tempi parola-per-parola per i sottotitoli."""
from __future__ import annotations

import os
import ssl
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class Word:
    text: str
    start: float  # secondi
    end: float


def _ssl_fix() -> None:
    """edge-tts usa il bundle certifi; dietro un proxy aziendale serve la CA indicata in SSL_CERT_FILE."""
    ca = os.environ.get("SSL_CERT_FILE")
    if ca and Path(ca).exists():
        import edge_tts.communicate as c

        c._SSL_CTX = ssl.create_default_context(cafile=ca)


async def synthesize(text: str, voice: str, out_mp3: Path, rate: str = "+8%") -> List[Word]:
    """Genera l'mp3 e restituisce i tempi di ogni parola. rate leggermente accelerato = ritmo da Shorts."""
    if os.environ.get("YTF_OFFLINE_TTS"):
        return silent(text, out_mp3)
    import edge_tts

    _ssl_fix()
    com = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    words: List[Word] = []
    with open(out_mp3, "wb") as f:
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                s = chunk["offset"] / 1e7
                words.append(Word(chunk["text"], s, s + chunk["duration"] / 1e7))
    if not words:
        raise RuntimeError("TTS senza tempi parola")
    return words


def silent(text: str, out_mp3: Path, wps: float = 2.6) -> List[Word]:
    """Modalità offline/test: audio muto con tempi stimati (2.6 parole/secondo)."""
    words, t = [], 0.2
    for w in text.split():
        d = max(0.18, len(w) / (wps * 5))
        words.append(Word(w, t, t + d))
        t += d + 0.05
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                    "-t", f"{t + 0.5:.2f}", "-q:a", "9", str(out_mp3)], check=True)
    return words
