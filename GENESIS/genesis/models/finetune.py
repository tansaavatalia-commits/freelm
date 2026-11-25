"""Fine-tuning planner: memory estimates for full / LoRA / QLoRA and a written plan. Never trains.

Estimates (indicative, +-50%):
  full   : 16 bytes/parameter (fp16 weights + gradients + fp32 Adam states) + activations
  lora   : 2 bytes/parameter (frozen fp16 base) + adapters (~1% of parameters x 16 bytes) + activations
  qlora  : 0.55 bytes/parameter (4-bit base incl. quantization constants) + adapters + activations
  activations ~ batch x sequence length x parameters(B) x 0.00004 GB (with gradient checkpointing)
"""

from __future__ import annotations

from typing import Any

from ..hardware.detect import HardwareInfo

METHODS = {"full": 16.0, "lora": 2.0, "qlora": 0.55}
ADAPTER_FRACTION = 0.01


def plan(params_b: float, method: str, examples: int, avg_tokens: int, hw: HardwareInfo,
         seq_len: int = 1024, batch: int = 4, epochs: int = 3) -> dict[str, Any]:
    if method not in METHODS:
        raise ValueError(f"metodo sconosciuto (ammessi: {', '.join(METHODS)})")
    if examples < 1 or avg_tokens < 1 or seq_len < 64 or batch < 1 or epochs < 1:
        raise ValueError("valori non validi")
    base = params_b * METHODS[method]
    adapters = 0.0 if method == "full" else params_b * ADAPTER_FRACTION * 16
    activations = batch * seq_len * params_b * 0.00004
    need = round(base + adapters + activations, 2)
    vram = hw.max_vram_mb / 1024
    feasible = vram >= need
    warnings = []
    if examples < 200:
        warnings.append("meno di 200 esempi: rischio di sovra-adattamento, valutare prima prompt e regole")
    if avg_tokens > seq_len:
        warnings.append("esempi più lunghi della sequenza: verranno troncati")
    return {
        "method": method, "params_b": params_b, "examples": examples, "tokens_total": examples * avg_tokens * epochs,
        "estimate_gb": {"base": round(base, 2), "adapters": round(adapters, 2), "activations": round(activations, 2),
                        "total": need},
        "gpu_vram_gb": round(vram, 2), "feasible_here": feasible,
        "verdict": ("fattibile su questa GPU" if feasible else
                    "non fattibile su questo PC (serve una GPU con almeno "
                    f"{need:.1f} GB di VRAM)"),
        "warnings": warnings, "method_note": "stima indicativa ±50%, da confermare con una prova breve",
    }


def plan_markdown(card: dict[str, Any], p: dict[str, Any]) -> str:
    e = p["estimate_gb"]
    return "\n".join([
        f"# Piano di fine-tuning — {card['id']} ({p['method'].upper()})", "",
        f"- Modello: {card['family']}, {card['params_b']} miliardi di parametri, licenza **{card['license']}** "
        f"({card['verification']})",
        f"- Dati: {p['examples']} esempi, {p['tokens_total']:,} token totali per tutte le epoche".replace(",", "."),
        f"- Memoria stimata: {e['total']} GB (base {e['base']}, adattatori {e['adapters']}, attivazioni {e['activations']})",
        f"- Questo PC: {p['verdict']}", "",
        "## Passi", "",
        "1. **Licenze**: verificare che modello e dati permettano l'uso previsto (model card, origine dei dati).",
        "2. **Dati**: formato chat JSONL; dividere in addestramento/validazione/test (80/10/10); il test non si tocca.",
        "3. **Baseline**: misurare il modello di partenza nel Research Lab sullo stesso test (soggetto `router` con il "
        "modello locale configurato), salvando l'id dell'esperimento.",
        f"4. **Addestramento**: {p['method'].upper()} su hardware adeguato (GPU con ≥ {e['total']:.1f} GB). Nessun servizio "
        "a pagamento: eventuali GPU gratuite nel cloud richiedono prima la verifica delle condizioni (COST_POLICY).",
        "5. **Valutazione**: nuovo esperimento sullo stesso dataset; confronto appaiato con la baseline (`genesis lab compare`).",
        "6. **Promozione**: solo tramite il ciclo di miglioramento (Fase 9), con miglioramento dimostrato e approvazione "
        "del proprietario.", "",
        "## Avvertenze", "", *([f"- {w}" for w in p["warnings"]] or ["- nessuna"]),
        f"- {p['method_note']}", "",
    ])
