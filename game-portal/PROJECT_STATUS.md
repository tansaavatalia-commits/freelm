# Tabluo (GAME PORTAL) — Stato del progetto

**Aggiornato:** 2026-11-19
**Fase attuale:** FASI 4–6 in corso (sviluppo locale). FASI 0–3 completate.
**Niente è pubblicato online. Nessuna spesa. Nessun account creato. Nessun contatto esterno.**

## Attività completate
- FASE 0–1: audit, piano A–J, ricerca di mercato, modello finanziario v2 (ibrido).
- Decisioni: D-001…D-019 (vedi `docs/DECISIONS.md`); nome di lavoro **Tabluo**.
- FASE 2: architettura, schema D1, protocollo `tabluo/1`, design system v0 (chiaro/scuro), ADR.
- FASE 3: monorepo pnpm, TypeScript strict, test, build, CI pronta per il repo dedicato.
- FASE 4 (parziale): portale con home, categorie, ricerca, pagina gioco, correlati, preferiti e cronologia locali, pagine info (bozze legali), mobile-first.
- FASE 5 (parziale): API Hono + D1 — kill switch, eventi anonimi aggregati, ad server diretto, admin API con audit log.
- FASE 6 (parziale): player sandbox su origin separato, SDK giochi, 3 giochi originali (Mines, Sudoku, Nonogram con puzzle del giorno).

## Test (eseguiti davvero, 2026-11-19)
| Suite | Risultato |
|---|---|
| `shared` (manifest, licenze, protocollo) | 12/12 ✅ |
| `games` (logica dei 3 giochi) | 17/17 ✅ |
| `backend` (API su SQLite reale con la migrazione di produzione) | 16/16 ✅ |
| `frontend` (isolamento player, ricerca, storage, pagine, navigazione) | 16/16 ✅ |
| script catalogo (regola bloccante licenze) | 6/6 ✅ |
| **E2E in Chromium** (`pnpm e2e`: API wrangler/D1 locale + giochi + portale) | 12/12 ✅ |
| Controllo tipi tutti i pacchetti + build | ✅ |
| Test falliti | nessuno |

## Errori trovati e corretti
- Crash di navigazione nei Chromium recenti (effetto React che restituiva la Promise di `scrollTo`): corretto, con test di regressione che fallisce sul vecchio codice.
- Riquadro di gioco sovradimensionato su desktop: corretto (proporzioni del gioco).
- Script E2E: server residui e `curl` senza timeout: corretto (gruppi di processi, timeout).
- `games/public` scambiata per un gioco: corretta (la regola bloccante ha fermato la build come previsto).

## Bloccate
- **D-001 repository dedicato:** in attesa che il titolare crei `game-portal` (privato, vuoto). Istruzioni: `docs/MIGRATION.md`.

## Decisioni richieste
- **Dominio `tabluo.com`** (~10–15 €/anno, D-010): libero il 2026-11-19, non acquistato.
- **D-019:** riconferma delle licenze dei giochi interni prima della pubblicazione.

## Limiti noti (non errori, lavoro futuro)
- Admin: token temporaneo (D-017), manca la SPA admin con passkey + MFA (FASE 7).
- SEO: SPA senza prerendering (FASE 4); i18n non ancora attivo; Lighthouse CI da aggiungere (FASE 10).
- Nessun rate limiting sull'API (FASE 5/9); account utente e Premium non iniziati (D-006, D-008).
- Pagine privacy/termini: **bozze**, serve revisione legale (D-009).
- Giochi: 3 su 10 di D-013.

## Prossimo passo
1. Spostamento nel repository dedicato appena esiste (`git subtree split`, storia preservata).
2. Altri giochi (Klondike, FreeCell, Spider, Mahjong, Word, Dama, Scacchi).
3. Prerendering SEO + i18n, SPA admin con passkey.
