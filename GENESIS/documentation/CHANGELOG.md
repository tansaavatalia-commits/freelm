# Changelog di GÉNESIS

(Il `CHANGELOG.md` alla radice del repository riguarda `freelm`.)

## 0.6.0 — 2026-11-24 — Fase 6: Research Lab

- Dataset versionati con hash SHA-256 (`math-basic@1`, `classify-it@1`, `qa-facts@1`) e importazione da JSON;
  modificare un dataset senza cambiarne la versione è rifiutato.
- Esperimenti con i 12 campi del Master Prompt, risultati per elemento, risorse (tempo reale/CPU, RAM, picco).
- Soggetti: classificatore, baseline di maggioranza, motore locale, router, agenti, Consiglio. Senza
  `allow_remote` tutto resta sul PC; con il remoto, al massimo 40 chiamate stimate per esperimento.
- Confronti solo sullo stesso hash: McNemar esatto + IC bootstrap con seed; il verdetto non dichiara
  miglioramenti senza significatività e almeno 20 elementi appaiati.
- Riproduzione con stessa configurazione, seed e ordine; rapporti Markdown in `<home>/reports`.
- `genesis lab …`, API `/api/lab/*`, pagina «Laboratorio»; primo risultato in `RESEARCH_LOG.md`; 171 test.

## 0.5.0 — 2026-11-24 — Fase 5: Strumenti e MCP

- Ogni strumento dichiara nome, descrizione, livello, rischi, costi, parametri, output e annullamento;
  ogni chiamata passa dall'autorizzazione centrale ed entra nell'audit.
- Strumenti locali confinati in `<home>/workspace` (anche contro i symlink): `files.list/read/write`,
  `text.search`; la scrittura è livello 2 e non sovrascrive senza `overwrite`.
- `web.fetch`: spento di default; solo http(s) pubblici, indirizzi locali/privati rifiutati anche nei
  redirect, 1 MB / 15 s, testo estratto e segnato come **non fidato**.
- Client MCP (stdio, JSON-RPC): server dichiarati solo dal proprietario, avviati solo per una richiesta,
  livello 3 (4-5 con approvazione), timeout con chiusura del processo.
- Agenti con elenco di strumenti consentiti; `research`: il Researcher legge una pagina come dati
  non fidati delimitati. `genesis tools list/call`, `GET /api/tools`; 144 test.

## 0.4.0 — 2026-11-24 — Fase 4: Agenti

- Agent Factory: 8 agenti predefiniti versionati (Director, Researcher, Developer, Analyst, Creator,
  Manager, Verifier, Security) a livello 1; agenti del proprietario da `<home>/agents/*.json`, che
  partono senza permessi finché il proprietario non li concede in `genesis.toml`.
- Ogni chiamata passa dai permessi come `agent.<id>` e poi dal router (gratuito/privato).
- Verifier deterministico: risposta non vuota, nessun segreto, lunghezza, calcoli ricontrollati in locale.
- Director: scomposizione a regole e delega; rapporto onesto dei sotto-compiti falliti.
- Consiglio v0: confronta le risposte, segnala contraddizioni numeriche, misura l'accordo
  (i membri differiscono per istruzioni e possono usare lo stesso modello).
- Tabella `agent_runs` (schema v2), `genesis agents …`, API, sezione «Agenti» nell'interfaccia; 130 test.

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
