"""Lettura di config/channels.toml + variabili d'ambiente."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

APP_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = APP_DIR / "config" / "channels.toml"


@dataclass
class Channel:
    id: str
    name: str
    language: str
    region: str
    voice: str
    niche: str
    audience: str
    style: str
    keywords: List[str]
    visual_style: str = "cinematic photography, dramatic lighting"
    category_id: str = "22"
    palette: List[str] = field(default_factory=lambda: ["#111827", "#1f2937", "#f59e0b"])
    seed_channel_ids: List[str] = field(default_factory=list)
    affiliate_links: List[str] = field(default_factory=list)

    def env(self, base: str) -> str:
        """Variabile per-canale (es. YT_REFRESH_TOKEN_FATTI) con fallback a quella globale."""
        return os.environ.get(f"{base}_{self.id.upper()}") or os.environ.get(base, "")


@dataclass
class Settings:
    timezone: str = "Europe/Rome"
    videos_per_day: int = 3
    publish_slots: List[str] = field(default_factory=lambda: ["12:30", "18:00", "21:00"])
    weekly_long_video: bool = True
    long_video_weekday: int = 6
    long_video_slot: str = "17:00"
    privacy_mode: str = "schedule"
    llm_model: str = "chat"
    panel_models: List[str] = field(default_factory=lambda: ["chat", "large", "fast"])
    ai_images: bool = True
    shot_seconds: float = 2.8
    max_parallel_videos: int = 3
    max_parallel_renders: int = 2
    min_quality_score: int = 7
    max_rewrites: int = 2
    upload_quota_cost: int = 1600
    daily_quota: int = 10000
    channels: List[Channel] = field(default_factory=list)
    data_dir: Path = APP_DIR / "data"

    def channel(self, cid: str) -> Channel:
        for c in self.channels:
            if c.id == cid:
                return c
        raise SystemExit(f"canale sconosciuto: {cid} (disponibili: {', '.join(c.id for c in self.channels)})")


def load(path: str | os.PathLike | None = None) -> Settings:
    p = Path(path or os.environ.get("YTF_CONFIG") or DEFAULT_CONFIG)
    raw = tomllib.loads(p.read_text(encoding="utf-8"))
    g = raw.get("global", {})
    known = set(Settings.__dataclass_fields__) - {"channels", "data_dir"}
    s = Settings(**{k: v for k, v in g.items() if k in known})
    ch_known = set(Channel.__dataclass_fields__)
    s.channels = [Channel(**{k: v for k, v in c.items() if k in ch_known}) for c in raw.get("channel", [])]
    if os.environ.get("YTF_DATA_DIR"):
        s.data_dir = Path(os.environ["YTF_DATA_DIR"])
    if s.privacy_mode not in ("schedule", "public", "private"):
        raise SystemExit("privacy_mode deve essere schedule | public | private")
    if len(s.publish_slots) < s.videos_per_day:
        raise SystemExit("servono almeno tanti publish_slots quanti videos_per_day")
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s
