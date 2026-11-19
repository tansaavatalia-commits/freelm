#!/usr/bin/env python3
"""GAME PORTAL - modello finanziario (FASE 0). Solo stdlib.

Tutti i parametri sono IPOTESI da validare in FASE 1 (vedi docs/FINANCIAL_MODEL.md).
Nessun dato qui e' un risultato reale: il portale non ha traffico ne' ricavi.

Formule (mensili):
  impression        = visitatori * sessioni * pagine * slot_per_pagina
  ricavi_ads        = impression * sell_through / 1000 * cpm
  ricavi_premium    = visitatori * conversione * prezzo_netto_iva * (1 - fee_pagamento)
  ricavi_sponsor    = min(max_sponsor, visitatori // visitatori_per_sponsor) * valore_medio
  utile_netto       = ricavi - costi_fissi - costi_variabili - imposte
Uso: python3 financial_model.py [--target 3000]
"""
from __future__ import annotations

import argparse

EUR_PER_USD = 0.92  # ipotesi di cambio, aggiornare

# --- costi fissi mensili (obrt paušalni in Croazia; DA VERIFICARE con commercialista) ---
FIXED = {
    "contributi_obrt": 295.0,      # fonti secondarie 2026: 290,98-298,98 EUR/mese
    "commercialista": 80.0,        # ipotesi 50-150 EUR/mese
    "dominio": 15.0 / 12,          # ipotesi .com ~12-15 EUR/anno
    "email_backup_monitor": 0.0,   # soluzioni gratuite (Email Routing, GitHub Actions)
}
WORKERS_PAID_USD = 5.0             # Cloudflare Workers Paid, base mensile
API_REQ_PER_VISITOR = 12           # ipotesi: chiamate API per visitatore/mese
FREE_REQ_PER_MONTH = 100_000 * 30  # Workers Free: 100k req/giorno (verificare)

SCENARIOS = {
    # cpm: EUR per 1000 impression vendute direttamente; st: sell-through (quota venduta)
    # ns_max: max sponsor attivi; vps: visitatori/mese necessari per ogni sponsor (nessuno
    #   sponsor paga un sito senza pubblico); vs: valore medio mensile sponsor
    # conv: quota visitatori che paga Premium; price: prezzo lordo IVA; lic: licenze/mese
    # tax: aliquota effettiva imposte sul ricavo (paušalni: bassa; DA VERIFICARE)
    "prudente":   dict(cpm=1.5, st=0.15, ns_max=2,  vps=200_000, vs=200, conv=0.0010, price=3.99, lic=0,   tax=0.06),
    "intermedio": dict(cpm=3.0, st=0.35, ns_max=4,  vps=75_000,  vs=400, conv=0.0030, price=3.99, lic=100, tax=0.05),
    "ambizioso":  dict(cpm=6.0, st=0.60, ns_max=8,  vps=40_000,  vs=800, conv=0.0060, price=4.99, lic=300, tax=0.04),
    "stress":     dict(cpm=1.0, st=0.05, ns_max=0,  vps=1,       vs=0,   conv=0.0005, price=2.99, lic=200, tax=0.08),
}
USAGE = dict(sessions=1.6, pages=3.0, slots=1.5)   # per visitatore unico mensile
VAT_PREMIUM = 0.25     # IVA HR 25% (B2C UE: aliquota del paese cliente oltre 10k EUR/anno OSS)
PAY_FEE = 0.04         # ipotesi fee di incasso premium (carte/bonifici), 0 se solo bonifico


def month(visitors: float, s: dict) -> dict:
    imp = visitors * USAGE["sessions"] * USAGE["pages"] * USAGE["slots"]
    ads = imp * s["st"] / 1000 * s["cpm"]
    premium = visitors * s["conv"] * s["price"] / (1 + VAT_PREMIUM) * (1 - PAY_FEE)
    n_sponsor = min(s["ns_max"], int(visitors // s["vps"]))
    sponsor = n_sponsor * s["vs"]
    revenue = ads + premium + sponsor
    infra = WORKERS_PAID_USD * EUR_PER_USD if visitors * API_REQ_PER_VISITOR > FREE_REQ_PER_MONTH else 0.0
    costs = sum(FIXED.values()) + infra + s["lic"]
    tax = revenue * s["tax"]
    return dict(visitors=visitors, impressions=imp, ads=ads, premium=premium, sponsor=sponsor,
                revenue=revenue, costs=costs, tax=tax, net=revenue - costs - tax)


def visitors_for(target: float, s: dict) -> float | None:
    lo, hi = 0.0, 1e9
    if month(hi, s)["net"] < target:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if month(mid, s)["net"] < target else (lo, mid)
    return hi


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=float, default=3000.0, help="utile netto mensile EUR")
    a = ap.parse_args()
    print(f"Obiettivo utile netto mensile: {a.target:,.0f} EUR\n")
    hdr = f"{'scenario':<11}{'visitatori/mese':>16}{'impression':>13}{'ads':>9}{'premium':>9}{'sponsor':>9}{'ricavi':>9}{'costi':>8}{'imposte':>9}{'utile':>8}"
    print(hdr)
    print("-" * len(hdr))
    for name, s in SCENARIOS.items():
        v = visitors_for(a.target, s)
        if v is None:
            print(f"{name:<11}{'irraggiungibile':>16}")
            continue
        m = month(v, s)
        print(f"{name:<11}{m['visitors']:>16,.0f}{m['impressions']:>13,.0f}{m['ads']:>9,.0f}{m['premium']:>9,.0f}"
              f"{m['sponsor']:>9,.0f}{m['revenue']:>9,.0f}{m['costs']:>8,.0f}{m['tax']:>9,.0f}{m['net']:>8,.0f}")
    print("\nPareggio (utile = 0):")
    for name, s in SCENARIOS.items():
        v = visitors_for(0.0, s)
        print(f"  {name:<11} {'irraggiungibile' if v is None else f'{v:,.0f} visitatori/mese'}")
    print("\nSensibilita' (scenario intermedio, utile a diversi volumi):")
    for v in (10_000, 50_000, 100_000, 250_000, 500_000, 1_000_000):
        m = month(v, SCENARIOS["intermedio"])
        print(f"  {v:>9,} visitatori -> ricavi {m['revenue']:>8,.0f}  utile {m['net']:>8,.0f} EUR")


if __name__ == "__main__":
    main()
