"""Notifiche Telegram: a fine giornata il riepilogo e ogni video (guardabile e scaricabile dal telefono).

Usa gli stessi segreti già presenti nel repository: TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID.
Se mancano, non fa nulla. Un errore di Telegram non blocca mai lo studio.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, List

import httpx

API = "https://api.telegram.org/bot{token}/{method}"
MAX_VIDEO_BYTES = 49 * 1024 * 1024  # limite dei bot Telegram: 50 MB


def enabled() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID")) \
        and not os.environ.get("YTF_OFFLINE")


async def daily_report(http: httpx.AsyncClient, results: List[Any], log: Callable[[str], None] = print) -> None:
    if not enabled():
        return
    token, chat = os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"]
    run_url = ""
    if os.environ.get("GITHUB_RUN_ID"):
        run_url = (f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/"
                   f"{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{os.environ['GITHUB_RUN_ID']}")
    lines = ["🎬 Studio YouTube: produzione di oggi"]
    for r in results:
        lines.append(f"\n{r.channel}: {len(r.produced)} video")
        lines += [f"  • {v['title']}" + (f"  https://youtu.be/{v['youtube_id']}" if v.get("youtube_id") else "")
                  for v in r.produced]
        lines += [f"  ⚠️ {e[:150]}" for e in r.errors[:3]]
    if run_url:
        lines.append(f"\nDettagli e download: {run_url}")
    try:
        await http.post(API.format(token=token, method="sendMessage"),
                        data={"chat_id": chat, "text": "\n".join(lines)[:4000], "disable_web_page_preview": "true"})
        for r in results:
            for v in r.produced:
                await _send_video(http, token, chat, v)
    except httpx.HTTPError as e:
        log(f"telegram non raggiungibile: {e}")


async def _send_video(http: httpx.AsyncClient, token: str, chat: str, v: dict) -> None:
    path = Path(v["file"])
    if not path.exists() or path.stat().st_size > MAX_VIDEO_BYTES:
        return
    meta = {}
    side = path.with_suffix(".json")
    if side.exists():
        meta = json.loads(side.read_text(encoding="utf-8"))
    status = f"✅ programmato: https://youtu.be/{v['youtube_id']}" if v.get("youtube_id") else "📥 pronto per l'upload"
    caption = f"[{v['channel']}] {v['title']}\n{status}\n\n{meta.get('description', '')}"[:1000]
    with open(path, "rb") as fh:
        await http.post(API.format(token=token, method="sendVideo"),
                        data={"chat_id": chat, "caption": caption, "supports_streaming": "true"},
                        files={"video": (path.name, fh, "video/mp4")}, timeout=300)
