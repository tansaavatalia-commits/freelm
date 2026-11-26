# Rapporto dei test

## 2026-11-25 — Fasi 7–9 (versione 0.9.0)

- Python: **207 passati + 1 saltato** senza freelm (208 con freelm), Python 3.13, Linux.
- Test end-to-end nel browser **passato** su tutte le pagine, compreso il ciclo completo di miglioramento
  dall'interfaccia (rileva → valuta → raccomandazione «promuovere» → approvazione → v2 attiva → ritorno a v1).
- Difetti trovati dai test e corretti: la memoria immediata non ignorava gli accenti; le etichette predefinite
  erano rifiutate; un'aspettativa errata sulla memoria permanente (il modello dei permessi è più restrittivo).
- Risultati misurati: vedi `RESEARCH_LOG.md` R-003 e R-004.

## 2026-11-24 — Fase 6 (versione 0.6.0)

- Python: **170 passati + 1 saltato** senza freelm (171 con freelm installato), Python 3.13, Linux.
- Interfaccia: controllo dei tipi + build; test end-to-end nel browser **passato**, ora con il laboratorio:
  due esperimenti avviati dall'interfaccia e confronto con verdetto «B migliore di A: dimostrato».
- Risultati scientifici verificati dai test: classificatore 27/30 contro baseline 10/30 (p < 0,001);
  motore locale 24/26 su `math-basic@1`; riproduzione identica elemento per elemento.
- Difetti trovati guardando l'interfaccia e corretti: barra dell'accuratezza colorata come «memoria piena»;
  stati in inglese; bordi delle tabelle disallineati nella colonna dei pulsanti (anche Progetti e Compiti).

## 2026-11-24 — Fase 2a (versione 0.2.0)

| Controllo | Dove | Esito |
|---|---|---|
| Lint Python (`ruff check .`) | cloud + CI | passato |
| Test Python (88: core + API + esecutore) | cloud Linux, Python 3.13 | **88 passati** |
| Test Python | CI: Ubuntu 3.11/3.13, Windows 3.11/3.13 (esecuzione 45330785522) | **4 job su 4 passati** |
| Controllo dei tipi TypeScript + build | cloud + CI (job `frontend`) | passati |
| Build nel repository uguale ai sorgenti (`git diff --exit-code`) | CI | passato |
| Test end-to-end nel browser (`desktop/frontend/e2e/smoke.cjs`, Chromium) | cloud | **passato** |

Il test end-to-end avvia `genesis serve` e usa l'interfaccia come un utente:
Dashboard, creazione di un progetto, compito messo in coda ed eseguito
dall'esecutore in background, dettagli e risultato, JSON non valido bloccato dal
modulo, backup dalla Dashboard, Diagnostica (controlli, catena di audit, backup),
Approvazioni, larghezza da telefono senza scorrimento orizzontale, arresto pulito
con Ctrl+C. Fallisce se il browser registra un qualsiasi errore, comprese le
violazioni della Content-Security-Policy.

Nuovi test Python: sicurezza dell'API (token, Host contro il DNS rebinding,
Origin, assenza di CORS, path traversal, limite di 64 KB), tutti gli endpoint,
errori 400/404/405/409/413, esecutore unico (anche dopo un processo ucciso),
ripristino rifiutato con un esecutore attivo, handler di log condiviso, letture
della RAM dal vivo.

Difetti trovati dal test end-to-end e corretti: voci del menu senza nome
accessibile su telefono; riquadri dei compiti che uscivano dalla card; sfondo
della barra laterale interrotto nelle pagine lunghe.

Misura: processo `genesis serve` ≈ **28 MB di RAM** (Linux). Sul PC Windows: PENDENTE.

## 2026-11-23 — Fase 1 (core 0.1.0)

### Eseguiti nel container cloud (Linux x86_64, 4 vCPU, 15 GB RAM)

| Controllo | Comando | Esito |
|---|---|---|
| Lint | `ruff check .` (ruff 0.16.9) | passato |
| Test, Python 3.13.18 | `python3.13 -m pytest` | **72 passati**, 0 falliti |
| Test, Python 3.11 | `uv run --python 3.11 --with pytest python -m pytest` | **72 passati**, 0 falliti |
| Prova end-to-end CLI | `doctor`, `project add`, `task submit/run`, `backup create`, `status` | passata |

Cosa coprono i 72 test:

- configurazione valida/non valida, permessi in sola lettura, `GENESIS_HOME`;
- oscuramento dei segreti nei log, nell'audit e negli errori dei compiti;
- bus di eventi: caratteri jolly, isolamento degli errori, limite di ricorsione;
- database: migrazioni idempotenti e annullate in caso di errore, WAL, dati
  confermati che sopravvivono a un processo ucciso (`os._exit`), backup
  verificati e rotazione, ripristino con copia di sicurezza, rifiuto di file non
  validi, esportazione/importazione e rifiuto di file malevoli;
- sicurezza: catena di audit che rileva una manomissione, trigger append-only,
  permessi entro/oltre il livello, approvazioni monouso legate ad azione,
  principal e livello, solo il proprietario decide, ogni decisione registrata;
- compiti: priorità, nuovi tentativi, annullamento, ripresa dopo un'interruzione,
  permessi revocati, gestore mancante, eventi;
- hardware: rilevamento reale sulla macchina, scelta del profilo, profilo
  richiesto oltre l'hardware rifiutato;
- CLI: tutti i comandi principali, migrazione su un «nuovo PC», codici di uscita,
  nessun file privato dentro `GENESIS/`.

### CI su GitHub Actions (`genesis-core-ci`)

Esecuzione 45287815680 (commit `0c29556`, allora col nome `genesis-ci`):
**4 job su 4 passati**.

| Runner | Python | Lint | Test | `doctor` su hardware reale |
|---|---|---|---|---|
| ubuntu-latest | 3.11 | passato | 72 passati | passato |
| ubuntu-latest | 3.13 | passato | 72 passati | passato |
| windows-latest | 3.11 | passato | 72 passati | passato |
| windows-latest | 3.13 | passato | 72 passati (3,1 s) | passato |

Rilevamento sul runner Windows (Windows Server 2025, build 10.0.26100):
CPU «AMD EPYC 9V74» letta dal registro, RAM 16,0 GB da `GlobalMemoryStatusEx`,
GPU «Microsoft Hyper-V Video» dal registro, SQLite 3.50.4 **con FTS5**, profilo
`standard`. Il percorso Windows del codice è quindi verificato; manca solo il PC
del proprietario (Windows 10, 4 GB → profilo atteso `lite-4gb`).

Difetto trovato e corretto: con l'output rediretto Windows usava la codepage
ANSI («GÉNESIS» mostrato come «G?NESIS» nei log). Ora la CLI scrive sempre UTF-8.

### Non eseguito

- Test di `freelm` (non toccato da questa fase).

## PC del proprietario (2026-11-25)

Eseguito dal PC reale con una sessione Claude Code locale, commit `3d4b123`.
Python 3.15.2 (percorso completo `%LOCALAPPDATA%\Python\pythoncore-3.15-64\python.exe`).

### `genesis doctor`

```
GÉNESIS 0.9.0 - diagnostica
Sistema:    Windows 10 (10.0.19045) AMD64 · Python 3.15.2
CPU:        Intel(R) Celeron(R) CPU  N3060  @ 1.60GHz · 2 thread logici
RAM:        3.4 GB totali · 0.4 GB disponibili ora
Disco:      140.1 GB liberi su 194.0 GB (C:\Users\<proprietario>\AppData\Local\GENESIS)
GPU:        Intel(R) HD Graphics (VRAM 1024 MB)
Profilo:    lite-4gb - automatico: RAM 3468 MB < 7500 MB
            compiti in parallelo 1 · chiamate IA in parallelo 1 · modelli locali no
Controlli:  7/7 [OK] (Python >= 3.11, SQLite 3.53.4 con FTS5, integrità DB,
            catena di audit intatta, cartella dati scrivibile, spazio disco, RAM)
```

Profilo `lite-4gb` come atteso.

### pytest

`python -m pytest -q` dalla cartella `GENESIS` (report JUnit):
**208 test, 206 passati, 0 falliti, 0 errori, 2 saltati**, 98 s (130 s al primo giro).

Saltati:
- `tests/test_intelligence.py:165` — `freelm` non installato (atteso: serve solo per il motore online).
- `tests/test_tools.py:63` — «symlink non consentiti su questo sistema» (Windows senza
  modalità sviluppatore/diritti di amministratore: atteso).

Nota: il riepilogo finale di pytest non compariva nell'output catturato da PowerShell;
i numeri vengono dal report `--junitxml`.

### 2026-11-26 — dopo l'aggiunta di `text.find`

`python -m pytest -q`: **210 test, 208 passati, 0 falliti, 0 errori, 2 saltati** (gli stessi due), 93 s.
Nuovi test: `test_text_find_indexed` (classifica, accenti, tutte le parole, aggiornamento dopo modifica e
cancellazione, sintassi FTS neutralizzata, indice fuori dalla sandbox) e `test_text_find_falls_back_without_fts5`.
`ruff` NON eseguito (non installato sul PC).

### 2026-11-26 — Passo 4: interfaccia e RAM reale

`python -m genesis serve` avviato in una finestra separata: `http://127.0.0.1:8765` risponde 200.
Tutte le 9 pagine (Dashboard, Progetti, Compiti, Agenti, Laboratorio, Motori, Miglioramento, Approvazioni,
Diagnostica) sono state aperte in automatico nel browser interno dell'app Claude: ogni pagina mostra il suo
contenuto (264–1255 ms fino alla fine del caricamento), **nessun errore nella console**, tutte le 38 chiamate
`/api/…` hanno risposto **200 OK**. La Dashboard mostra il profilo `lite-4gb`, l'esecutore attivo e l'audit integro.

| Misura | Valore |
|---|---|
| Processo `genesis serve` | **43,9 MB** (picco 49,4 MB) |
| Chrome (13 processi) | 221 MB |
| Edge (8 processi) | 364 MB |
| RAM libera del sistema | 647 MB prima dell'avvio → 463 MB con GÉNESIS e le pagine aperte (su 3469 MB) |
| App Claude (per confronto) | ~1240 MB |

Il consumo di GÉNESIS è piccolo; la RAM del PC è occupata soprattutto dai browser e dall'app Claude.
NON VERIFICATO: il controllo visivo delle pagine da parte del proprietario (gli screenshot del browser interno
sono scaduti per lentezza del PC; il controllo è stato fatto sul testo delle pagine e sulle chiamate di rete).

### 2026-11-26 — Passo 5: portabilità

Con `genesis serve` acceso nello stesso momento:

```
genesis project add "Prova portabilità"         → Progetto creato
genesis export %TEMP%\genesis-export.json       → projects 1 · tasks 2 · audit_log 5 · agent_runs 2 · datasets 5 · altro 0
genesis --home %TEMP%\genesis-nuovo-pc import … → Importazione completata (stessi conteggi)
genesis --home %TEMP%\genesis-nuovo-pc project list → Prova portabilità  active
genesis --home %TEMP%\genesis-nuovo-pc audit verify → Catena di audit intatta (6 voci), uscita 0
genesis audit verify (originale)                → Catena di audit intatta (5 voci)
```

La voce in più nella copia è la registrazione dell'importazione stessa. Le cartelle di prova in `%TEMP%`
sono state lasciate. Limite: copia sullo stesso PC, non su un secondo computer.

### 2026-11-26 — Interfaccia «Núcleo» (globo)

- `npm ci` + `npm run build` sul PC (Node 26.13): la ricompilazione senza modifiche produceva gli stessi file
  (stessi hash), quindi la build è riproducibile; poi build con il globo: nessun errore TypeScript.
- Browser interno dell'app, 1280×800, dati veri: 8 etichette degli agenti, pannelli popolati, nessun errore in
  console, nessuno scorrimento orizzontale o verticale. Un'esecuzione reale (`genesis agents run analyst …`)
  porta la barra dell'Analyst al 99% e compare in «Ultime attività» entro 4 s.
- **Misura del carico (importante):** la prima versione senza limiti arrivava a 160.000–180.000 luci a 42–44
  fotogrammi/s, ma toglieva CPU al resto: due test MCP (timeout 2 s) fallivano con il globo aperto e passavano con il
  globo chiuso. Con il tetto `lite-4gb` (120.000 luci) e 30 fotogrammi/s: 120.000 luci a 30 fotogrammi/s e i test
  MCP passano con il globo aperto. `genesis serve` 16 MB.
- Suite completa con il globo aperto **e** il prototipo senza limiti ancora aperto in Chrome: 210 test, 207
  passati, **1 fallito** (`test_mcp_list_call_errors_and_timeout`, timeout di 2 s del server MCP di prova per
  carico del PC), 2 saltati. Lo stesso test passa da solo con il globo aperto. Da ripetere con Chrome chiuso.
- NON eseguito: `e2e/smoke.cjs` (Playwright non installato sul PC); aggiornato per la nuova pagina iniziale.

### Ancora da fare sul PC

- Passi 1–5 fatti. Restano: controllo visivo delle pagine da parte del proprietario, Passo 6 (facoltativo),
  Passo 7 (decisioni), Passo 8 (Release).
