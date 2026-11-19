"""Reparto grafica animata: card Remotion (numeri che contano, confronti, elenchi, linee del tempo, citazioni).

Il Motion Designer propone le card; qui si VALIDANO in modo deterministico (ogni numero e ogni voce devono comparire
nel testo parlato di quella scena: niente dati inventati nemmeno nelle grafiche) e si rendono con Node + Remotion
(cartella motion/). Se Node o Remotion mancano, il video si fa comunque, senza grafiche.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import APP_DIR

MOTION_DIR = APP_DIR / "motion"
KINDS = {"stat", "compare", "list", "timeline", "quote"}


def available() -> bool:
    if os.environ.get("YTF_NO_MOTION"):
        return False
    return bool(shutil.which("node")) and (MOTION_DIR / "node_modules" / "@remotion" / "renderer").exists()


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w%$€£¢ ]+", " ", str(t).lower())).strip()


def _numbers(t: str) -> List[str]:
    return re.findall(r"\d+(?:[.,]\d+)*", str(t))


def _numbers_ok(values: List[str], scene: str) -> bool:
    """Ogni numero della card deve comparire (cifra per cifra) nel testo parlato della scena."""
    spoken = {n.replace(",", "").replace(".", "") for n in _numbers(scene)}
    return all(n.replace(",", "").replace(".", "") in spoken for v in values for n in _numbers(v))


def _words_ok(text: str, scene: str, need: float = 0.5) -> bool:
    words = [w for w in _norm(text).split() if len(w) > 3]
    if not words:
        return True
    hay = _norm(scene)
    return sum(w in hay for w in words) / len(words) >= need


def validate(card: Dict[str, Any], scene_text: str) -> Optional[Dict[str, Any]]:
    """Card pulita e verificata, oppure None se usa dati che la scena non contiene."""
    kind = str(card.get("kind", ""))
    if kind not in KINDS:
        return None
    c: Dict[str, Any] = {"kind": kind, "title": str(card.get("title") or "")[:40]}
    if kind == "stat":
        value = str(card.get("value") or "")
        if not _numbers(value) or not _numbers_ok([value, str(card.get("sub") or "")], scene_text):
            return None
        c.update(value=value[:24], label=str(card.get("label") or "")[:50], sub=str(card.get("sub") or "")[:60])
    elif kind == "compare":
        a, b = card.get("a") or {}, card.get("b") or {}
        vals = [str(a.get("value") or ""), str(b.get("value") or "")]
        if not all(_numbers(v) for v in vals) or not _numbers_ok(vals, scene_text):
            return None
        c.update(a={"value": vals[0][:20], "label": str(a.get("label") or "")[:30]},
                 b={"value": vals[1][:20], "label": str(b.get("label") or "")[:30]})
    elif kind == "list":
        items = [str(i)[:40] for i in card.get("items") or [] if str(i).strip()][:4]
        if len(items) < 2 or not all(_words_ok(i, scene_text) for i in items) or not _numbers_ok(items, scene_text):
            return None
        c["items"] = items
    elif kind == "timeline":
        pts = [p for p in card.get("points") or [] if isinstance(p, dict) and p.get("year")][:4]
        if len(pts) < 2 or not _numbers_ok([str(p["year"]) for p in pts], scene_text):
            return None
        c["points"] = [{"year": str(p["year"])[:12], "label": str(p.get("label") or "")[:40]} for p in pts]
    elif kind == "quote":
        text = str(card.get("text") or "")
        if not text or not _words_ok(text, scene_text, 0.8):
            return None
        c.update(text=text[:140], author=str(card.get("author") or "")[:50])
    if not _numbers_ok([c["title"]], scene_text):
        c["title"] = ""
    return c


async def render_cards(jobs: List[Dict[str, Any]], public_dir: Path, workdir: Path) -> Dict[str, bool]:
    """Rende tutte le card di un video in un solo processo Node. Ritorna {percorso_mp4: riuscita}."""
    if not jobs or not available():
        return {}
    spec = workdir / "motion_jobs.json"
    spec.write_text(json.dumps({"publicDir": str(public_dir), "jobs": jobs}), encoding="utf-8")
    proc = await asyncio.create_subprocess_exec("node", str(MOTION_DIR / "render.mjs"), str(spec), cwd=str(MOTION_DIR),
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=600)
    except asyncio.TimeoutError:
        proc.kill()
        return {}
    done: Dict[str, bool] = {}
    for line in out.decode(errors="replace").splitlines():
        if line.startswith("{"):
            try:
                r = json.loads(line)
                done[r["out"]] = bool(r.get("ok")) and Path(r["out"]).exists()
            except (ValueError, KeyError):
                continue
    return done
