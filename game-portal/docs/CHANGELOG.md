# GAME PORTAL — Changelog

## 2026-11-25 — Klondike Solitaire e guida al lancio
- Nuovo gioco **Klondike Solitaire** (pescata 1 o 3, annulla illimitato, doppio clic verso le fondazioni, completamento automatico); modello carte condiviso `games/sdk/cards.js` per i prossimi solitari.
- 13 test della logica di Klondike, compresa una partita casuale di 2.000 mosse che verifica che non si perdano mai carte.
- E2E: controllo che nessun gioco sbordi dallo schermo del telefono (dentro l'iframe).
- Corretti dopo la revisione visiva: carta del mazzo fuori posizione, settima colonna tagliata su telefono.
- `docs/LAUNCH.md`: i 4 passi (≈ 20 minuti, 0 €) per la beta pubblica; `scripts/screenshots.mjs`.

## 2026-11-19 — FASI 2–6 (parziali), sviluppo locale
- Monorepo pnpm in `game-portal/`: `shared`, `backend` (Hono + D1), `frontend` (React + Vite), `games` (vanilla JS).
- Giochi originali: Mines, Sudoku (soluzione unica), Nonogram (puzzle del giorno).
- Catalogo da Git con regola bloccante delle licenze (D-016); controllo licenze giornaliero in CI.
- API: kill switch, eventi aggregati anonimi, ad server diretto (sponsor → diretta → rete → nessuno), report, audit log.
- Test: 67 unitari + 12 end-to-end in Chromium (`pnpm check`, `pnpm e2e`).
- Bug trovati dai test E2E e corretti: crash di navigazione (effetto React che restituiva la Promise di `scrollTo` nei Chromium recenti) con test di regressione; riquadro di gioco sovradimensionato su desktop; cartella `games/public` scambiata per un gioco.
- Documenti: DEPLOYMENT, OPERATIONS, MIGRATION; screenshot in `docs/screenshots/`.

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
