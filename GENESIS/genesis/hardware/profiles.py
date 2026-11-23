"""Execution profiles: how much GÉNESIS may do on the current machine.

The profile is chosen from the detected hardware. A profile set in the
configuration is honoured only if the hardware supports it: asking for more
than the machine can give falls back to the automatic choice, so heavy engines
stay off on small machines.
"""

from __future__ import annotations

from dataclasses import dataclass

from .detect import HardwareInfo


@dataclass(frozen=True)
class Profile:
    name: str
    description: str
    rank: int
    max_workers: int  # tasks run concurrently (Phase 1 worker is sequential everywhere)
    max_parallel_online: int  # concurrent remote model calls (used by the router, Phase 3)
    local_models: bool  # local model inference allowed (Phase 7–8)
    log_max_bytes: int
    log_backups: int
    backup_keep: int


PROFILES: dict[str, Profile] = {
    p.name: p
    for p in (
        Profile("lite-4gb", "meno di 8 GB di RAM: un compito alla volta, nessun modello locale", 0, 1, 1, False,
                1_000_000, 3, 5),
        Profile("standard", "8 GB di RAM o più, senza GPU adatta ai modelli locali", 1, 2, 2, False,
                5_000_000, 5, 10),
        Profile("gpu", "16 GB di RAM e una GPU con almeno 6 GB di VRAM: modelli locali possibili", 2, 4, 3, True,
                10_000_000, 5, 14),
    )
}
LITE_BELOW_RAM_MB = 7_500  # an "8 GB" machine reports ~7.8 GB usable
GPU_MIN_RAM_MB = 15_000
GPU_MIN_VRAM_MB = 6_000


def auto_profile(hw: HardwareInfo) -> tuple[Profile, str]:
    ram = hw.ram_total_mb
    if ram is None:
        return PROFILES["lite-4gb"], "RAM non rilevata: profilo prudente"
    if ram < LITE_BELOW_RAM_MB:
        return PROFILES["lite-4gb"], f"RAM {ram} MB < {LITE_BELOW_RAM_MB} MB"
    vram = hw.max_vram_mb
    if ram >= GPU_MIN_RAM_MB and vram >= GPU_MIN_VRAM_MB:
        return PROFILES["gpu"], f"RAM {ram} MB e VRAM {vram} MB"
    return PROFILES["standard"], f"RAM {ram} MB, VRAM {vram} MB (sotto {GPU_MIN_VRAM_MB} MB per i modelli locali)"


def select_profile(hw: HardwareInfo, requested: str = "auto") -> tuple[Profile, str]:
    auto, reason = auto_profile(hw)
    if requested == "auto":
        return auto, f"automatico: {reason}"
    wanted = PROFILES[requested]
    if wanted.rank > auto.rank:
        return auto, f"richiesto '{requested}' ma l'hardware non lo supporta ({reason})"
    return wanted, f"impostato in configurazione: {requested}"
