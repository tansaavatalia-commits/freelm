# GAME PORTAL — Changelog

## 2026-11-19 — Decisioni D-014 e D-015
- D-015 approvata: modello pubblicitario ibrido (diretta → sponsor → rete sull'invenduto, solo con consenso).
- Modello finanziario v2: ~183k visitatori/mese nello scenario intermedio per 3.000 € netti (v1 solo diretta: ~246k); opzione `--no-network`.
- D-014: nome di lavoro **Tabluo** (alternativa Mellodeck); .com liberi via RDAP, nessun acquisto.
- ARCHITECTURE, SECURITY, LEGAL_CHECKLIST aggiornati per CMP/TCF e isolamento degli script di rete.

## 2026-11-19 — FASE 1
- Approvazione utente ("Autorizzo tutto"): push eseguito, decisioni D-001…D-008 approvate.
- Dossier concorrenti v1 (Poki, CrazyGames, Coolmath, Y8, siti di solitario indipendenti) con fonti classificate.
- Modello finanziario v1: conversione Premium ridotta di 3–5 volte in base all'evidenza; ~246k visitatori/mese nello scenario intermedio.
- Checklist legale: età del consenso HR (16), linee guida art. 28 DSA, soglia OSS di 10.000 €.
- Nuove decisioni aperte: D-014 (brand), D-015 (reti pubblicitarie).

## 2026-11-19 — FASE 0
- Audit dell'ambiente e del repository (il repository ospite è `freelm`, non correlato).
- Creata la documentazione di pianificazione in `game-portal/docs/`.
- Aggiunto `scripts/financial_model.py` (modello riproducibile, solo stdlib).
- Corretto il modello: gli sponsor ora dipendono dal traffico (prima lo scenario ambizioso risultava in utile con 0 visitatori).
