# Changelog di GÉNESIS

(Il `CHANGELOG.md` alla radice del repository riguarda `freelm`.)

## 0.3.1 — 2026-11-24 — Motore online: OpenRouter gratuito

- L'adattatore usa solo OpenRouter con la guardia «solo gratuito» di freelm (Groq, Gemini & co. ignorati).
- `genesis online enable --confirm` / `disable`: accende/spegne il motore online (approvazione registrata).
- Prova reale dal cloud fino a OpenRouter: modello `:free` scelto correttamente; risposta 401 perché la
  chiave dell'ambiente cloud non è disponibile. CI con freelm installato.

## 0.3.0 — 2026-11-24 — Fase 3: Intelligent Router

- Contratto unico per i motori (`intelligence/base.py`); il router non dipende da nessuna API esterna.
- Motore locale deterministico: calcoli (valutatore AST sicuro, mai `eval`) e statistiche del testo.
- Adattatore online `freelm` (livelli gratuiti), **disattivato** finché il proprietario non imposta
  `remote_enabled` e `remote_free_verified`; mai endpoint senza chiave; chiamate esterne nell'audit
  (senza il testo della richiesta).
- Router: classificazione a regole → filtro (mai a pagamento, privato = solo locale) → punteggio
  (qualità, locale prima, affidabilità, latenza) → esecuzione con fallback (max 3) → esito
  «verificato» solo per gli algoritmi.
- `genesis ask`, `genesis providers`, compito `intelligence.ask`, `GET /api/engines`, card nella Dashboard.
- 115 test Python.

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
