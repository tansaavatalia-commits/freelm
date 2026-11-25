"""Genesis Multimodal Engine: reads image/audio/PDF metadata from file headers (standard library only).
Understanding image content or transcribing audio needs a model: not available on this profile."""

from __future__ import annotations

import re
import struct
import wave
from pathlib import Path
from typing import Any, Callable

from .. import __version__
from .base import Component, EngineOpError, GenesisEngine, Operation


def inspect_bytes(data: bytes, path: Path | None = None) -> dict[str, Any]:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        w, h = struct.unpack(">II", data[16:24])
        return {"format": "PNG", "width": w, "height": h}
    if data[:6] in (b"GIF87a", b"GIF89a"):
        w, h = struct.unpack("<HH", data[6:10])
        return {"format": "GIF", "width": w, "height": h}
    if data.startswith(b"BM") and len(data) >= 26:
        w, h = struct.unpack("<ii", data[18:26])
        return {"format": "BMP", "width": w, "height": abs(h)}
    if data.startswith(b"\xff\xd8"):
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker, length = data[i + 1], struct.unpack(">H", data[i + 2:i + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return {"format": "JPEG", "width": w, "height": h}
            i += 2 + length
        return {"format": "JPEG", "width": None, "height": None}
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return {"format": "WEBP"}
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE" and path is not None:
        with wave.open(str(path), "rb") as w:
            frames, rate = w.getnframes(), w.getframerate()
            return {"format": "WAV", "channels": w.getnchannels(), "sample_rate": rate,
                    "duration_s": round(frames / rate, 3) if rate else None}
    if data.startswith(b"%PDF-"):
        version = data[5:8].decode("ascii", "replace")
        pages = len(re.findall(rb"/Type\s*/Page(?!s)", data))
        return {"format": "PDF", "version": version, "pages_estimate": pages}
    try:
        text = data.decode("utf-8")
        return {"format": "testo", "characters": len(text), "lines": text.count("\n") + 1}
    except UnicodeDecodeError:
        return {"format": "sconosciuto", "bytes": len(data)}


class MultimodalEngine(GenesisEngine):
    id, name, version = "multimodal", "Genesis Multimodal Engine", f"1.0@{__version__}"
    description = "Metadati di immagini (PNG, JPEG, GIF, BMP, WEBP), audio WAV e PDF."
    components = (
        Component("lettore di intestazioni", "algoritmo", "dimensioni e formato dai primi byte del file"),
        Component("audio WAV", "algoritmo", "canali, frequenza, durata (modulo wave)"),
        Component("visione / trascrizione", "modello esterno", "NON disponibile: serve profilo gpu o un motore con visione",
                  available=False),
    )
    operations = (Operation("inspect", 1, "metadati di un file della cartella di lavoro", '{"path": "foto.png"}'),)

    def __init__(self, resolve: Callable[[str], Path] | None = None, max_bytes: int = 20_000_000) -> None:
        self._resolve, self._max = resolve, max_bytes

    def run(self, op: str, payload: dict[str, Any], principal: str = "owner") -> Any:
        if op != "inspect":
            raise EngineOpError(f"operazione sconosciuta: {op}")
        if self._resolve is None or not isinstance(payload.get("path"), str):
            raise EngineOpError("serve 'path' di un file nella cartella di lavoro")
        path = self._resolve(payload["path"])
        if not path.is_file():
            raise EngineOpError("file inesistente")
        if path.stat().st_size > self._max:
            raise EngineOpError("file troppo grande (oltre 20 MB)")
        info = inspect_bytes(path.read_bytes(), path)
        return {"path": payload["path"], "bytes": path.stat().st_size, **info,
                "content_understanding": "non disponibile su questo profilo (nessun modello di visione/audio)"}
