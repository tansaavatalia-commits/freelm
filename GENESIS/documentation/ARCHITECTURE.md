# Architettura

## Principi

1. Il core funziona da solo (CLI) e con **zero** provider esterni.
2. Fase 1 solo con la libreria standard di Python (≥ 3.11): nessuna dipendenza da installare.
3. Massimo due processi a regime (core + interfaccia); nel profilo `lite-4gb` un compito alla volta.
4. Tutti i dati dell'utente fuori dal repository, in una sola cartella portabile.
5. Ogni azione passa dal livello dei permessi e lascia traccia nell'audit.

## Moduli (Fase 1)

```
genesis/
  app.py              Genesis: crea e collega tutti i servizi; status() e doctor()
  cli.py              interfaccia a riga di comando (l'utente della CLI è il proprietario)
  errors.py           gerarchia delle eccezioni
  core/
    config.py         default < <home>/genesis.toml < override; validazione rigorosa
    logs.py           log JSON a rotazione; segreti oscurati prima della scrittura
    events.py         bus di eventi in-process con caratteri jolly e isolamento degli errori
    projects.py       progetti
    tasks.py          coda persistente, priorità, tentativi, annullamento cooperativo, ripresa dopo crash
    clock.py          orario UTC iniettabile nei test
  memory/
    migrations.py     schema versionato (PRAGMA user_version)
    db.py             connessione WAL, transazioni, backup verificati, ripristino, export/import JSON
  security/
    redact.py         oscuramento dei segreti (formati noti dei provider + chiave=valore)
    audit.py          registro append-only a catena di hash SHA-256
    permissions.py    livelli 1–5, permessi immutabili a runtime, approvazioni monouso
  hardware/
    detect.py         rilevamento in sola lettura (ctypes/winreg su Windows, /proc e /sys su Linux)
    profiles.py       lite-4gb · standard · gpu; un profilo oltre l'hardware viene rifiutato
```

## Cartella dati

```
<home>/                 %LOCALAPPDATA%\GENESIS su Windows (o --home / GENESIS_HOME)
  genesis.toml          configurazione facoltativa (esempio: config/genesis.example.toml)
  data/genesis.db       database SQLite (+ -wal, -shm)
  logs/genesis.log      log JSON a rotazione
  backups/              backup verificati genesis-<timestamp>-NNN.db
  exports/              esportazioni JSON per la migrazione
```

## Schema del database (v1)

- `projects` — nome unico (senza distinzione maiuscole/minuscole), stato attivo/archiviato.
- `tasks` — tipo, payload JSON, principal, livello, stato, priorità, tentativi, risultato, errore.
- `approvals` — richieste di livello 4–5: in attesa / approvata / negata / usata.
- `audit_log` — voci append-only (trigger che bloccano UPDATE/DELETE) con `prev_hash` e `hash`.

## Flusso di un compito

`submit` → controllo dei permessi (livello dettato dal gestore; per i livelli 4–5
si consuma un'approvazione) → riga `pending` → `run_next` la prende in una
transazione `BEGIN IMMEDIATE` → controllo che il permesso sia ancora valido →
esecuzione → `succeeded` / nuovo tentativo / `failed` / `cancelled`. All'avvio,
`recover()` rimette in coda i compiti rimasti `running` dopo un crash.

## Prossime estensioni previste

- Fase 2: API HTTP locale (solo 127.0.0.1, con token) davanti a `Genesis`, poi la UI.
- Fase 3: interfaccia Provider propria; `freelm` sarà un adattatore tra gli altri.

## Fase 2a — `genesis serve`

```
browser (127.0.0.1:8765)
   │  pagina + /api/* con X-Genesis-Token
   ▼
genesis/api/server.py   ThreadingHTTPServer (solo 127.0.0.1)
   ├─ thread "core"     unica istanza Genesis per l'API (una connessione SQLite)
   └─ thread "worker"   seconda istanza Genesis + TaskWorker (lock data/worker.lock)
genesis/api/static/     interfaccia compilata (React + TS), sorgenti in desktop/frontend/
```

- **Endpoint:** `GET /api/status`, `/api/doctor`, `/api/projects`, `/api/tasks`,
  `/api/tasks/{id}`, `/api/task-kinds`, `/api/approvals`, `/api/audit`, `/api/backups`;
  `POST /api/projects`, `/api/projects/{ref}/archive`, `/api/tasks`,
  `/api/tasks/{id}/cancel`, `/api/approvals/{id}/approve|deny`.
- **Errori:** 400 dati non validi · 401 token · 403 permesso/host/origine ·
  404 · 405 · 409 serve un'approvazione (`approval_id`) · 413 richiesta troppo grande.
- **Esecutore unico:** `core/worker.py` prende un lock esclusivo del sistema
  operativo; `task run` da CLI e `serve` non possono eseguire compiti insieme, e il
  ripristino di un backup è rifiutato mentre un esecutore è attivo.

## Fasi 3–9 in breve

```
genesis/
  intelligence/  router (classificazione, filtro gratuito/privato, fallback), motore locale, modello locale, freelm
  agents/        catalogo versionato, runtime con Verifier, Director, Consiglio
  tools/         registro con manifest, sandbox file, web.fetch, client MCP
  research/      dataset con hash, soggetti, esperimenti, statistica (McNemar, bootstrap), rapporti
  engines/       Reasoning, Code, Research, Data, Memory (FTS5), Multimodal + registro con permessi
  models/        catalogo modelli aperti, fattibilità, piani di fine-tuning
  improvement/   componenti con versioni, ciclo di miglioramento, aree protette
```

Schema del database: v1 (core) · v2 agent_runs · v3 datasets/experiments · v4 memories (+ FTS5 creato all'avvio)
· v5 improvements/component_versions. Esportazione/importazione includono tutte le tabelle.
