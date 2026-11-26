# Changelog di GÉNESIS

(Il `CHANGELOG.md` alla radice del repository riguarda `freelm`.)

## Non rilasciato — 2026-11-26

- Nuovo strumento `text.find` (livello 1): ricerca per parole nella cartella di lavoro con indice SQLite FTS5
  (classifica BM25, accenti e maiuscole ignorati, tutte le parole richieste). L'indice è una cache eliminabile in
  `<home>/cache/workspace-index.sqlite` (mai esportata né nel backup) e si aggiorna da solo: rilegge solo i file
  nuovi o cambiati (dimensione + data). Collegamenti simbolici e junction vengono ignorati. Senza FTS5 ripiega
  sulla ricerca lineare. Disponibile per Researcher, Developer e Analyst; `text.search` resta invariato.
- Misurato sul PC del proprietario (R-005): parole rare 75–100 ms invece di 2,3–2,7 s su 1000 file.
- Audit dell'hardware reale del PC; 210 test.
- **Interfaccia «Núcleo»** (richiesta del proprietario, D-36): nuova pagina iniziale con un globo di luci in WebGL
  (nessuna libreria aggiunta). Ogni agente ha una regione colorata; la regione si accende con le esecuzioni reali
  degli agenti (in corso = piena, poi si spegne in 15 minuti), archi luminosi dal Director agli altri agenti,
  pannelli tecnici (luci, fotogrammi/s, profilo, RAM, compiti, audit, attività per agente, ultime richieste).
  Clic su un agente → pagina Agenti. Trascina per ruotare, rotella per lo zoom; si ferma quando la scheda non è
  visibile e libera la memoria della scheda grafica quando si cambia pagina. Senza WebGL mostra una spiegazione e il
  collegamento al pannello classico. Le altre pagine restano nel menu (la Dashboard è a `#/dashboard`).
- **Console sul globo:** casella in basso per scrivere una richiesta al Director (scompone e delega) o a un agente
  scelto dal menu, dal pannello o cliccando il suo nome sul globo; opzione «privata». La risposta compare sopra la
  casella appena l'agente ha finito. Ogni richiesta (anche dalla pagina Agenti o dalla CLI) fa partire un'onda
  d'urto sulla regione dell'agente e un impulso lungo l'arco dal Director.

## 0.9.0 — 2026-11-25 — Fase 9: Auto-miglioramento controllato

- Componenti migliorabili con versioni (classificatore v1/v2, calcolo v1/v2) e benchmark associati.
- Ciclo: rilevamento (misura ed errori) → proposta (problema, prove, causa) → prove isolate (stabile contro
  candidata su ogni benchmark) → raccomandazione → approvazione del proprietario (livello 4) → promozione;
  rifiuto e ritorno alla versione precedente. Aree protette (permessi, sicurezza, audit, costi, accessi, il ciclo stesso)
  non modificabili.
- Promozione solo con miglioramento dimostrato e nessun peggioramento dimostrato; avvertenza se i benchmark sono interni.
- Router, motore locale e agenti leggono la versione attiva a ogni chiamata (vale subito anche per l'esecutore).
- Pagine «Motori» (motori, componenti, prova dal vivo, catalogo modelli) e «Miglioramento»; schema v5; 207 test.

## 0.8.0 — 2026-11-25 — Fase 8: Model Development Lab

- Catalogo di 12 modelli aperti (dati segnati come non verificati, licenze evidenziate) + aggiunte del proprietario.
- Stime di fattibilità (pesi per quantizzazione, cache, riserva del sistema) e piani di fine-tuning (full/LoRA/QLoRA).
- Fornitore per un modello locale compatibile OpenAI, solo su indirizzi locali, spento nel profilo lite-4gb.

## 0.7.0 — 2026-11-25 — Fase 7: Motori GÉNESIS

- Dataset pre-registrati `classify-holdout@1` e `math-words@1` (commit separato, prima dei motori).
- Reasoning (classificatore v2, calcolo in parole, problemi a parole), Code (analisi statica), Research (riassunto
  estrattivo, parole chiave, fonti), Data (CSV), Memory (4 livelli, FTS5), Multimodal (metadati). Ogni motore dichiara
  la natura dei componenti. Risultati R-003/R-004 con il limite metodologico dichiarato.

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
