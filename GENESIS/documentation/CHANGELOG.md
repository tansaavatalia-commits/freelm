# Changelog di GÉNESIS

(Il `CHANGELOG.md` alla radice del repository riguarda `freelm`.)

## 0.1.0 — 2026-11-23 — Fase 1: Core

- Configurazione TOML con validazione rigorosa e permessi immutabili a runtime.
- Log JSON a rotazione con oscuramento dei segreti.
- Bus di eventi in-process.
- Database SQLite (WAL) con migrazioni versionate, backup verificati con
  rotazione, ripristino con copia di sicurezza, esportazione/importazione JSON.
- Permessi a 5 livelli, approvazioni del proprietario monouso, audit
  append-only a catena di hash.
- Progetti e coda dei compiti persistente: priorità, tentativi, annullamento,
  ripresa dopo un crash.
- Rilevamento hardware senza dipendenze e profili `lite-4gb` / `standard` / `gpu`.
- CLI `python -m genesis` e CI su Linux e Windows.

## 0.0.0 — 2026-11-23 — Fase 0

- Rapporto di audit in sola lettura e piano per fasi (`FASE_0_AUDIT.md`).
