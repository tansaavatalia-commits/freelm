# Changelog di GÉNESIS

(Il `CHANGELOG.md` alla radice del repository riguarda `freelm`.)

## 0.2.0 — 2026-11-24 — Fase 2a: interfaccia nel browser

- `genesis serve`: API HTTP locale (solo 127.0.0.1) con token per installazione,
  controllo di Host e Origin, Content-Security-Policy rigorosa.
- Interfaccia React + TypeScript (Vite): Dashboard, Progetti, Compiti,
  Approvazioni, Diagnostica; tema scuro/chiaro automatico; adatta al telefono.
- La build compilata è inclusa nel pacchetto: sul PC non serve Node.
- Un solo esecutore di compiti per cartella dati (lock del sistema operativo);
  i compiti interrotti vengono ripresi solo da chi ottiene il lock.
- Misura dal vivo della RAM del processo e della RAM libera.
- Test: 88 in Python + test end-to-end nel browser; CI che verifica la build.

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
