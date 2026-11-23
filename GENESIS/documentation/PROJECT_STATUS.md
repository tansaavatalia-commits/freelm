# Stato del progetto

Aggiornato: 2026-11-23 · Versione del core: 0.1.0 · Branch: `claude/genesis-phase-0-audit-zrvq7a`

| Fase | Stato |
|---|---|
| 0 — Audit | COMPLETATA, tranne l'hardware reale del PC (PENDENTE: vedi `FASE_0_AUDIT.md`, Appendice A) |
| 1 — Core | IMPLEMENTATA e testata nel cloud (Linux, Python 3.11 e 3.13). Windows: verificato dalla CI `genesis-core-ci` (vedi `TEST_REPORT.md`). Sul PC del proprietario: PENDENTE |
| 2 — Desktop | PENDENTE |
| 3–10 | PENDENTI |

## Cosa funziona oggi (IMPLEMENTATO)

- CLI `python -m genesis` con `status`, `doctor`, progetti, coda dei compiti,
  approvazioni, backup/ripristino, esportazione/importazione, audit.
- Database SQLite in modalità WAL con migrazioni versionate.
- Permessi a 5 livelli, approvazioni del proprietario monouso, audit a catena di hash.
- Rilevamento hardware senza dipendenze (Windows, Linux, macOS parziale) e
  scelta automatica del profilo.

## Cosa NON c'è ancora

- Interfaccia grafica (Fase 2), provider di IA e router (Fase 3), agenti
  (Fase 4), strumenti e MCP (Fase 5), laboratori e motori (Fasi 6–9).
- Nessun provider esterno è configurato o usato dal core.

## Problemi aperti

1. Il PC del proprietario non è collegato alla sessione: il core non è ancora
   stato eseguito sul vero hardware Windows 10 da 4 GB.
2. Le chiavi OpenRouter e Gemini dell'ambiente cloud non funzionano ancora
   (OpenRouter: la chiave non viene inserita nelle richieste; Gemini: 404 su ogni
   endpoint). Non bloccano la Fase 1 né la 2.
3. Licenza di GÉNESIS non ancora scelta (D-06).
