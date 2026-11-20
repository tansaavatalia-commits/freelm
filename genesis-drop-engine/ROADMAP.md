# ROADMAP — Piano di implementazione

Strategia: costruire prima il **nucleo che protegge il denaro e le regole** (profitto, conformità,
liquidità), poi la scoperta e infine le integrazioni esterne. Ogni milestone termina con test reali
e aggiornamento della documentazione. Le stime sono in sessioni di lavoro indicative.

## FASE 1 — Architettura e ricerca ✅ (in attesa di approvazione)

Consegnati: architettura, scelte tecnologiche, schema DB, specifiche moduli, strategia integrazioni,
sicurezza, test, costi, rischi, roadmap.

## FASE 2 — Core engine (dopo approvazione)

| Milestone | Contenuto | Criterio di completamento |
|-----------|-----------|---------------------------|
| **M2.0 Fondamenta** | Scaffolding progetto, Docker Compose (Postgres), pyproject, ruff/mypy/pytest/pre-commit/gitleaks, CI, `core/` (Money, Provenance, Clock), `policy/` con rule_set versionato, audit log a catena di hash, migrazione iniziale | CI verde; test di Money e audit |
| **M2.1 Profit Engine (M5)** | Formula completa, 3 scenari, multipack, tabelle IVA/dazi/fee/FX, snapshot immutabili, API `/profit` | Test BR-001/010/011 + property test; esempio di `BUSINESS_RULES.md` §5 riprodotto |
| **M2.2 Compliance Engine (M6)** | Regole per categoria/paese, evidenze, esiti, blocco | Test di blocco anche con punteggio massimo |
| **M2.3 Ledger + Cashflow Guardian (M7)** | Partita doppia, stati del denaro, riserve, liquidità attuale/proiettata | Property test somma zero; simulazioni payout |
| **M2.4 Zero-Advance Engine (M8)** | Algoritmo §7.3, fornitori alternativi, decisioni idempotenti, lock concorrenti | Tutte le simulazioni finanziarie di `TESTING.md` |
| **M2.5 Catalogo e Product Radar (M2)** | Prodotti canonici, varianti, offerte, matching, macchina a stati, connettore CSV/manuale + fake | Import CSV di test, deduplica, transizioni con gate |
| **M2.6 Supplier Intelligence (M4) + Market Intelligence (M3)** | Confronto fornitori e paesi | Classifiche riproducibili su dataset di test |
| **M2.7 Scoring + Market Radar (M1)** | Opportunity Score trasparente; segnali da fonti autorizzate (o `MISSING`) | Punteggio con dettaglio; filtri rigidi testati |
| **M2.8 Listing Studio (M9)** | Bozze via `freelm`, validazione, approvazione | Bozze multi-lingua validate; nessuna pubblicazione |
| **M2.9 Fulfillment (M10) + Outbox + Automazione** | State machine ordine, outbox, approvazioni, livelli, kill switch | E2E con fake: ordine → riconciliazione |
| **M2.10 Marketplace Command Center (M11) + Control Tower (M12)** | Hub canali (fake), dashboard | Dashboard mostra liquidità reale e blocchi |
| **M2.11 Chiusura Fase 2** | Backup/restore testato, report costi, documentazione | Report di fine fase |

## FASE 3 — Integrazioni e lancio (dopo approvazione)

1. Connettore CJdropshipping (lettura → ordini in sandbox/test con approvazione).
2. Primo marketplace (es. Allegro sandbox) → verifica idoneità reale → account (approvazione operatore).
3. Simulazioni finanziarie con dati reali di fee e payout.
4. E2E completo senza transazioni reali; poi primo ordine reale **solo** con autorizzazione esplicita.
5. Monitoraggio, notifiche errori, health check, checklist di lancio, approvazione finale.

## Dipendenze dalle decisioni dell'operatore

- M2.0 richiede D-001 (repo) e D-003 (stack). M2.1 beneficia di D-005 (paesi) e D-010.
- M2.4 richiede D-007 e D-011. La Fase 3 richiede D-002 e D-004.
