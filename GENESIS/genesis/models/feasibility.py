"""Can a model run on this machine? Rough, documented estimates (not measurements).

weights   = parameters x bytes per weight of the quantization (GGUF approximations)
KV cache  ~ 20 KB per token per billion parameters (fp16, models with grouped-query attention)
runtime   = 0.4 GB fixed overhead
available = total RAM - reserve for the operating system (2.5 GB on Windows, 1.5 GB elsewhere)
            - 0.15 GB for GÉNESIS itself
"""

from __future__ import annotations

from typing import Any

from ..hardware.detect import HardwareInfo
from ..hardware.profiles import Profile

BYTES_PER_WEIGHT = {"f16": 2.0, "q8_0": 1.06, "q6_k": 0.82, "q5_k_m": 0.71, "q4_k_m": 0.61, "q3_k_m": 0.49, "q2_k": 0.42}
KV_KB_PER_TOKEN_PER_B = 20.0
RUNTIME_GB = 0.4
GENESIS_GB = 0.15


def os_reserve_gb(hw: HardwareInfo) -> float:
    return 2.5 if hw.os_name == "Windows" else 1.5


def estimate(params_b: float, quant: str = "q4_k_m", context: int = 4096) -> dict[str, float]:
    if quant not in BYTES_PER_WEIGHT:
        raise ValueError(f"quantizzazione sconosciuta (ammesse: {', '.join(BYTES_PER_WEIGHT)})")
    weights = params_b * BYTES_PER_WEIGHT[quant]
    kv = context * params_b * KV_KB_PER_TOKEN_PER_B / 1_000_000
    return {"weights_gb": round(weights, 2), "kv_cache_gb": round(kv, 2), "runtime_gb": RUNTIME_GB,
            "total_gb": round(weights + kv + RUNTIME_GB, 2)}


def assess(params_b: float, hw: HardwareInfo, profile: Profile, quant: str = "q4_k_m",
           context: int = 4096) -> dict[str, Any]:
    need = estimate(params_b, quant, context)
    total_ram = (hw.ram_total_mb or 0) / 1024
    available = round(max(0.0, total_ram - os_reserve_gb(hw) - GENESIS_GB), 2)
    vram = hw.max_vram_mb / 1024
    if vram >= need["total_gb"]:
        verdict, where = "eseguibile", "GPU"
    elif need["total_gb"] <= 0.7 * available:
        verdict, where = "eseguibile", "CPU (lento)"
    elif need["total_gb"] <= available:
        verdict, where = "al limite", "CPU (lento, poca memoria libera per il resto)"
    else:
        verdict, where = "non eseguibile", "—"
    notes = []
    if hw.ram_total_mb is None:
        notes.append("RAM non rilevata: valutazione non affidabile")
    if not profile.local_models:
        notes.append(f"il profilo '{profile.name}' disattiva i modelli locali per prudenza")
    return {"quant": quant, "context": context, "need": need, "available_ram_gb": available,
            "vram_gb": round(vram, 2), "verdict": verdict, "where": where, "notes": notes,
            "method": "stima indicativa (pesi + cache + sovraccarico), non una misura"}


def best_option(params_b: float, hw: HardwareInfo, profile: Profile, context: int = 4096) -> dict[str, Any]:
    """Highest-quality quantization that is 'eseguibile' (q8 -> q2), else the closest one."""
    order = ["q8_0", "q6_k", "q5_k_m", "q4_k_m", "q3_k_m", "q2_k"]
    results = [assess(params_b, hw, profile, q, context) for q in order]
    for r in results:
        if r["verdict"] == "eseguibile":
            return r
    for r in results:
        if r["verdict"] == "al limite":
            return r
    return results[-1]
