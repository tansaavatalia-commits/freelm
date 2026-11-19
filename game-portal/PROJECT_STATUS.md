# GAME PORTAL — Stato del progetto

**Aggiornato:** 2026-11-19
**Fase attuale:** FASE 1 completata (gate G1: **GO condizionato**). Prossima: FASE 2 — Architettura e documentazione.

## Attività completate
- FASE 0: audit, piano A–J, roadmap, architettura, modello v0.
- Push del branch `claude/game-portal-master-mm5azl` (autorizzato).
- FASE 1: dossier concorrenti v1, modello finanziario v1, checklist legale aggiornata, catalogo iniziale (D-013), lingua (D-012).
- D-014 nome Tabluo, D-015 modello ibrido, modello finanziario v2.

## In corso
- Nessuna.

## Bloccate
- **D-001 (repo dedicato):** approvata ma non eseguibile da questa sessione (non posso creare repository). Serve un repo vuoto creato dall'utente.
- FASE 3 (codice): attende D-001, per non mescolare il portale con freelm.

## Decisioni richieste
- Nessuna decisione bloccante aperta. D-014 (Tabluo) e D-015 (modello ibrido) approvate.
- Da ricordare: il dominio `tabluo.com` è libero ma **non acquistato** (D-010, ~10–15 €/anno) e potrebbe essere registrato da altri.

## Errori
- Nessun errore tecnico. Correzioni di modello documentate in CHANGELOG.

## Test
- Superati: `python3 scripts/financial_model.py` e `--no-network` (output v2/v1 riportati in FINANCIAL_MODEL.md).
- Falliti: nessuno. Non esiste ancora codice applicativo.

## Limiti della ricerca
- Nessun bilancio depositato consultato (KvK e altri registri: consultazione diretta, in parte a pagamento).
- La maggior parte dei dati è [DICH] o [TERZI]; nessun benchmark di sell-through diretto trovato.

## Prossimo passo
FASE 2 (documentazione di architettura, schema dati, design) — può partire qui; il codice (FASE 3) parte appena esiste il repository dedicato.
