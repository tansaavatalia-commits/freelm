# GÉNESIS — Fase 0: audit tecnico (sola lettura)

- **Data:** 2026-11-23
- **Stato del documento:** PARZIALE. La sezione hardware del PC Windows è
  **PENDENTE**: il PC non era raggiungibile da questa sessione.
- **Stato di GÉNESIS:** nessun componente è implementato. Questo documento è
  solo un audit e un piano.

Legenda usata ovunque: **IMPLEMENTATO** · **SIMULATO** · **PENDENTE** ·
**NON VERIFICATO** · **STIMA** (valore calcolato, non misurato).

---

## 0. Perimetro e metodo

| Oggetto | Auditato? | Come |
|---|---|---|
| PC Windows del proprietario (target) | **No — PENDENTE** | Nessuna cartella del PC condivisa con la sessione (Remote Control vuoto). Comandi di sola lettura pronti in Appendice A. |
| Container cloud di questa sessione | Sì | Comandi di sola lettura (Appendice B). È solo un ambiente di sviluppo effimero, **non** il target. |
| Repository `tansaavatalia-commits/freelm` | Sì | Lettura dei file, `git`, `ruff check --no-cache` (non scrive nulla). |

Durante la Fase 0 **non** sono stati eseguiti: installazioni, chiamate a provider
di IA, attivazioni di servizi, creazione di chiavi, modifiche o cancellazioni di
file esistenti. L'unico file creato è questo documento.

---

## 1. Rapporto hardware

### 1a. PC Windows (target di esecuzione) — PENDENTE

| Voce | Valore | Stato |
|---|---|---|
| Sistema operativo | Windows 10 | dichiarato dal proprietario, NON VERIFICATO (build/edizione ignote) |
| RAM | 4 GB | dichiarato dal proprietario, NON VERIFICATO |
| CPU | ? | PENDENTE |
| GPU / VRAM | ? | PENDENTE |
| Disco (tipo HDD/SSD, spazio libero) | ? | PENDENTE |
| File di paging | ? | PENDENTE |
| WebView2 (necessario a Tauri) | ? | PENDENTE |
| Aggiornamenti di sicurezza Windows | ? | PENDENTE — vedi rischio R2 |

### 1b. Container cloud (solo sviluppo, effimero)

| Voce | Valore |
|---|---|
| OS | Ubuntu 24.04.5 LTS, kernel 6.18, x86_64 |
| CPU | 4 vCPU Intel Xeon @ 2.10 GHz |
| RAM | 15 GiB, nessuno swap |
| GPU | nessuna |
| Disco | quota per sessione, ~60 GB disponibili |

Questo ambiente serve a scrivere e testare il codice; viene distrutto a fine
sessione, quindi tutto ciò che conta va committato e pushato.

---

## 2. Rapporto sull'ambiente di sviluppo

### Container cloud (verificato)

| Strumento | Versione |
|---|---|
| Python | 3.13.18 (default), 3.12.3, 3.11.18 — **mancano** 3.9, 3.10, 3.14 |
| pip / uv | pip 24.0 · uv 0.11.32 |
| Node.js / npm | 22.23.5 / 10.9.9 (anche pnpm 10.28, yarn 1.22, bun 1.4.4) |
| Rust / cargo | 1.97.0 / 1.97.0 (rustup 1.28.2) |
| C/C++ | gcc/g++ 13.3, make 4.3, cmake 3.28, pkg-config 1.8 |
| Git | 2.43.0 |
| Docker | 29.9.3 |
| SQLite (libreria Python) | 3.53.1 — CLI `sqlite3` assente (non serve) |
| ruff | 0.16.9 |
| Browser per test UI | Chromium + Playwright preinstallati |

### PC Windows — PENDENTE

Python, Git, Node, Rust, MSVC Build Tools, WebView2, winget: da rilevare con
l'Appendice A.

### Repository

- Fork **pubblico** di `shihabshahrier/freelm`, licenza **MIT**, branch di
  lavoro `claude/genesis-phase-0-audit-zrvq7a`.
- Contenuto: `freelm` 0.5.2, un gateway LLM che mette in pool i livelli
  gratuiti di più provider, in doppia implementazione (Python `src/freelm/`
  ~4.600 righe; TypeScript `js/src/` ~3.800 righe); test Python ~4.000 righe;
  esempio `examples/trading_agents/` (~5.800 righe, bot di trading multi-agente
  *in papel*, con workflow GitHub Actions programmati).
- Lint: `ruff check src tests examples` → **All checks passed** (eseguito).
- Test: **NON ESEGUITI** — richiedono `httpx`/`respx`, assenti; installarli è
  vietato in Fase 0.

---

## 3. Dipendenze disponibili

- **Runtime Python nel container:** `sqlite3` (con libreria 3.53.1),
  `tomllib`, `pytest`, `anyio`, `pydantic`, `numpy`, `pandas`.
- **Dal repository:** `freelm` (dipende solo da `httpx`) — riusabile come
  *Online Engine* di GÉNESIS (vedi §5).
- **Toolchain:** Node 22, Rust 1.97, compilatori C/C++, Docker, Playwright.

## 4. Dipendenze mancanti

| Dove | Manca | Serve per | Necessaria quando |
|---|---|---|---|
| Container | `httpx`, `respx` | eseguire i test di `freelm` | prima della Fase 3 (verifica base) |
| Container | `tauri-cli`, toolchain Windows | build del binario Windows | Fase 2b — meglio via GitHub Actions (runner Windows gratuito su repo pubblico) |
| Container | `psutil` | — | **non** serve: il rilevamento hardware si fa con la libreria standard (`ctypes`, `platform`, `shutil`) |
| PC | Python 3.13 (probabile) | eseguire il Core | Fase 1 |
| PC | Git (probabile) | ottenere/aggiornare il codice | Fase 1 |
| PC | Node.js LTS | sviluppo frontend sul PC | Fase 2a (opzionale: si può sviluppare nel cloud) |
| PC | Rust + MSVC Build Tools | build locale di Tauri | Fase 2b, **sconsigliata** su 4 GB |
| PC | WebView2 Runtime | eseguire l'app Tauri | Fase 2b, solo se l'audit lo dà assente |

Tutto ciò che riguarda il PC è **PENDENTE** finché non arriva l'output
dell'Appendice A.

---

## 5. Compatibilità dell'architettura

| Componente del Master Prompt | Su Win10 / 4 GB | Note |
|---|---|---|
| Core Engine in Python | Compatibile | Python 3.12/3.13 supporta Windows 10 (le release future potrebbero non farlo: NON VERIFICATO). |
| Memoria SQLite (+ FTS5 per la ricerca) | Compatibile | Libreria standard, nessun server. FTS5 nella build Windows di Python: NON VERIFICATO, sarà un test automatico. |
| Desktop Tauri 2 + React + TS (esecuzione) | Compatibile | Richiede WebView2; consumo molto inferiore a Electron. |
| Desktop Tauri 2 (compilazione sul PC) | **Rischiosa** | Rust + MSVC: 9–15 GB di disco e picchi di RAM oltre i 4 GB (STIMA). Alternativa: build sul runner Windows di GitHub Actions. |
| Intelligent Router + Provider Manager | Compatibile | Logica pura, leggera. |
| Online Engine (provider gratuiti) | Compatibile | Tramite `freelm`, dietro un adattatore di GÉNESIS. Disattivato di default. |
| Local Engine con LLM locali | **Non praticabile** | Con 4 GB solo modelli minuscoli (≤0,5B quantizzati) di qualità molto bassa: resta un esperimento opzionale disattivato. Il Local Engine iniziale è deterministico (file, SQLite, calcoli, ricerca). |
| Docker / WSL2 sul PC | Non adatto | Troppo pesante per 4 GB; non usato. |
| Database vettoriale | Non necessario | FTS5 basta finché non c'è un bisogno dimostrato. |
| Multimodale, training di modelli | Fuori portata su questo PC | Solo ricerca e preparazione (Fasi 7–8). |

### Rapporto con `freelm` (già nel repo)

Cosa copre già di ciò che chiede il Master Prompt (IMPLEMENTATO in `freelm`,
non in GÉNESIS): registro provider, un adattatore per provider, rotazione
chiavi, failover tra provider, circuit breaker, routing con quote, scoperta
modelli, guardia "solo gratuito" (`free_only`), eventi, chiavi mascherate,
persistenza opzionale senza chiavi in chiaro.

Cosa **non** copre e dovrà fare GÉNESIS: classificazione dei compiti,
capacità per compito, criteri di privacy e di hardware, provider locali, un
modello di costo esplicito in €, l'Intelligence Council, la valutazione dei
risultati.

Decisione proposta: GÉNESIS definisce la **propria** interfaccia Provider;
`freelm` è un adattatore tra gli altri, sostituibile. Così il sistema non si
lega a `freelm` né ad alcuna API.

L'esempio `trading_agents` contiene schemi utili (sciame di agenti, diario
delle decisioni, controlli di sicurezza) ma è specifico del trading: resta
separato da GÉNESIS.

---

## 6. Rischi tecnici

| ID | Rischio | Impatto | Mitigazione |
|---|---|---|---|
| R1 | **4 GB di RAM**: Windows 10 a riposo ne usa già ~1,5–2,5 GB (STIMA) | Alto | Massimo 2 processi (Core + UI), worker sequenziale, niente modelli locali, limiti di cache e log, profilo `lite-4gb` di default. |
| R2 | **Windows 10 fuori supporto**: fine supporto 14/10/2025; l'ESU consumer è terminato il 13/10/2026. Il PC probabilmente non riceve più patch di sicurezza (NON VERIFICATO) | Alto per una piattaforma che naviga ed esegue strumenti | Internet e strumenti disattivati di default, contenuti esterni trattati come non fidati, nessun servizio in ascolto oltre `127.0.0.1`; architettura portabile per migrare a un PC supportato. |
| R3 | Compilare Rust/Tauri con 4 GB | Medio | Build sul runner Windows di GitHub Actions (gratuito su repo pubblico); in locale solo con `-j 1` e file di paging ampio. |
| R4 | Disco sconosciuto (HDD lento o poco spazio) | Medio | PENDENTE l'audit; SQLite in modalità WAL, backup a rotazione, log limitati. |
| R5 | **Repo pubblico**: tutto ciò che viene committato è visibile a chiunque | Alto | Dati, database, memoria, log e chiavi solo fuori dal repo (cartella utente), `.gitignore` dedicato, test che blocca file `.db`/`.env` nel commit. |
| R6 | Livelli gratuiti instabili: limiti e termini cambiano; alcuni piani gratuiti possono usare i prompt per addestramento (NON VERIFICATO per singolo provider) | Medio | Ogni provider resta disattivato finché i termini non sono verificati e registrati in `COST_POLICY.md`; flag di privacy per provider; il router può escluderli per i dati sensibili. |
| R7 | Convivenza con `freelm` nello stesso repo: regola di parità Python/TS, CI esistente, file root con lo stesso nome (`SECURITY.md`, `CHANGELOG.md`) | Medio | Tutto GÉNESIS dentro `GENESIS/`, con CI propria filtrata per percorso; non toccare i file di `freelm`. |
| R8 | Prompt injection da web, documenti e strumenti | Alto | Policy immutabili dagli agenti, output esterni marcati come dati non fidati, autorizzazione centrale, audit. |
| R9 | Ambito enorme (14 schermate, 8 agenti, 6 motori…) | Alto | Fette verticali piccole e verificate; una schermata compare solo quando la sua funzione esiste. |
| R10 | Binari non firmati (SmartScreen, antivirus) | Basso | La firma del codice costa: non si usa. Checksum pubblicati e build riproducibili in CI. |
| R11 | Un push di tag `v*` / `js-v*` in questo fork attiva i workflow di pubblicazione di `freelm` (PyPI, npm, Docker) | Medio | Mai creare tag senza approvazione esplicita (livello 5). |
| R12 | Il container cloud è effimero | Medio | Commit e push a fine di ogni passo. |
| R13 | Sviluppo assistito da Claude | Basso | È uno strumento di sviluppo, non una dipendenza di runtime: GÉNESIS funziona con zero provider esterni. |

---

## 7. Architettura finale adattata all'hardware

```
┌──────────────────────────────────────────────────────────────┐
│ UI  — Fase 2a: React + TS nel browser (servita dal Core)     │
│       Fase 2b: la stessa UI dentro Tauri 2 (WebView2)        │
└───────────────┬──────────────────────────────────────────────┘
                │ HTTP solo 127.0.0.1 + token locale
┌───────────────▼──────────────────────────────────────────────┐
│ genesis-core (Python ≥ 3.11, solo libreria standard in F1)   │
│  core/        config · event_bus · task_manager · audit       │
│  security/    permessi livelli 1–5 · segreti · approvazioni   │
│  memory/      SQLite (WAL) · migrazioni · FTS5 · backup       │
│  hardware/    rilevamento · profili di esecuzione             │
│  intelligence/ registry · router · adattatori:                │
│     ├─ local   (deterministico: regole, calcoli, file, ricerca)│
│     └─ online  (freelm → provider gratuiti, DISATTIVATO)      │
│  agents/ · tools/ · research_lab/ · engines/  (fasi successive)│
└──────────────────────────────────────────────────────────────┘
       Dati utente fuori dal repo: %LOCALAPPDATA%\GENESIS\
       (database, memoria, log, backup, configurazione locale)
```

**Principi**

1. Il Core funziona da solo (CLI) e con **zero** provider esterni.
2. Massimo due processi; un solo worker di compiti alla volta nel profilo `lite-4gb`.
3. Ogni servizio esterno è disattivato finché non è configurato, verificato e
   autorizzato.
4. Fase 1 senza dipendenze di runtime; `httpx` entra solo in Fase 3 con `freelm`.
5. Dati portabili: una cartella dati + esportazione/importazione → migrazione su
   un altro PC senza ricostruire nulla.

**Profili di esecuzione (proposta)**

| Profilo | Worker | LLM locali | Provider online in parallelo | Note |
|---|---|---|---|---|
| `lite-4gb` (default) | 1 | no | 1 | cache e log ridotti |
| `standard-16gb` | 2–4 | modelli piccoli opzionali | 2–3 | — |
| `gpu` | 4+ | sì (llama.cpp/Ollama, da valutare) | 3+ | Model Development Lab attivo |

**Struttura proposta** (le cartelle del Master Prompt, dentro un pacchetto
Python importabile e testabile; ogni cartella si crea solo quando c'è codice
reale):

```
GENESIS/
  pyproject.toml             # pacchetto "genesis", zero dipendenze runtime in F1
  genesis/
    core/  security/  memory/  hardware/   # Fase 1
    intelligence/                          # Fase 3
    agents/  tools/                        # Fasi 4–5
    research_lab/  engines/  model_development/   # Fasi 6–8
    cli.py                                 # genesis status | doctor | tasks | memory
  config/                    # default.toml, profiles/*.toml (senza segreti)
  tests/
  desktop/                   # Fase 2: frontend/ (React+Vite) e tauri/
  documentation/             # PROJECT_STATUS, ARCHITECTURE, ROADMAP, DECISIONS,
                             # CHANGELOG, TEST_REPORT, SECURITY, COST_POLICY, NEXT_ACTIONS
```

**Segreti:** variabili d'ambiente oppure Windows DPAPI via `ctypes` (nessuna
dipendenza); mai nel repo, mai in chiaro nel database o nei log.

---

## 8. Piano di implementazione per fasi

Ogni fase si chiude solo quando i suoi criteri di accettazione sono verificati.

| Fase | Contenuto | Criteri di accettazione |
|---|---|---|
| **1 — Core** | Pacchetto, config TOML + profili, log con oscuramento dei segreti, event bus, SQLite con migrazioni, backup/esportazione/importazione, gestore compiti persistente (stati, retry, annullamento, ripresa dopo crash), permessi livelli 1–5 + audit, rilevamento hardware, CLI, documenti di continuità, CI Linux + Windows | Test verdi su Linux **e** su Windows (CI); ruff pulito; zero dipendenze runtime; `genesis doctor` mostra l'hardware reale sul PC; test di ripresa dopo kill; test di backup/ripristino; un tentativo di auto-escalation dei permessi viene negato |
| **2a — UI web** | API locale (stdlib), frontend React + TS + Vite: shell, Dashboard con stato reale, navigazione, Progetti, Compiti | Ogni pulsante fa qualcosa di reale; test end-to-end con Playwright; RAM misurata sul PC |
| **2b — Tauri** | Shell Tauri 2 che avvia il Core; build Windows in GitHub Actions; checksum | L'installer si avvia sul PC; consumo misurato; nessuna build locale obbligatoria |
| **3 — Intelligence** | Interfaccia Provider (id, nome, versione, locale/remoto, capacità, requisiti, costo, stato, limiti, permessi, config), registry, router (classificazione → requisiti → filtro → selezione → esecuzione → fallback → log → valutazione), Local Engine, adattatore `freelm` | Funziona con zero provider; un provider a pagamento non può mai essere scelto (test); fallback testato con HTTP simulato; smoke test reale solo dopo che il proprietario abilita un provider con la propria chiave |
| **4 — Agenti** | Schema di configurazione versionato, 8 agenti iniziali, limiti (passi, tempo, token), storia in SQLite, Director sequenziale, Council v0 con misura rispetto a un singolo modello | Nessun agente può ampliare i propri permessi (test); il Council riporta se migliora o no rispetto alla baseline |
| **5 — Strumenti** | Manifest per strumento (permessi, rischi, costi, parametri, output, annullamento), autorizzazione centrale, strumenti locali in sandbox, fetch internet (disattivato), client MCP | Ogni chiamata passa dall'autorizzazione ed è nell'audit; i dati esterni sono marcati come non fidati |
| **6 — Research Lab** | Registro esperimenti con tutti i campi richiesti, runner di benchmark, riproducibilità (seed, hash della config, versioni), report | Un esperimento si ripete con lo stesso risultato |
| **7 — Motori propri** | Reasoning, Code, Research, Data, Memory, Multimodal (quest'ultimo spento in `lite-4gb`) | Ogni motore dichiara cosa è algoritmo proprio e cosa è modello esterno; ha test propri |
| **8 — Model Development** | Catalogo modelli aperti + licenze, harness di valutazione, piani LoRA/QLoRA per hardware futuro | Nessun training su questo PC |
| **9 — Self-Improvement** | Proposta → versione sperimentale isolata → test → confronto con la versione stabile → approvazione del proprietario | Sicurezza, permessi, costi e controlli di accesso sono immutabili dal sistema (test) |
| **10 — Release** | Validazione completa, documentazione, installer via CI, test di portabilità (esportazione → importazione su un'altra macchina) | Migrazione riuscita senza ricostruire |

---

## 9. Stima del consumo di risorse (STIMA, da misurare)

| Voce | RAM | Disco |
|---|---|---|
| Windows 10 a riposo | 1,5–2,5 GB | — |
| genesis-core (Python + SQLite) | 40–90 MB | < 50 MB di codice |
| UI nel browser / in Tauri | 100–250 MB / 80–200 MB | Tauri installato: 10–20 MB |
| **Totale GÉNESIS in esecuzione** | **~150–350 MB** | — |
| Database e memoria (primo anno, uso testuale) | — | < 100 MB |
| Log (rotazione con tetto) | — | ≤ 50 MB |
| Python 3.13 + Git | — | ~0,5 GB |
| Node LTS + dipendenze frontend | — | ~0,3–0,6 GB |
| Rust + MSVC Build Tools + cartella di build Tauri | picchi di compilazione 1,5–4 GB | **9–15 GB** → motivo per compilare in CI |
| Rete per chiamata LLM | — | pochi KB – ~100 KB |

---

## 10. Costi potenziali (devono essere 0 € per ogni azione autorizzata)

| Voce | Costo con l'uso previsto | Trappola da evitare | Verifica |
|---|---|---|---|
| Python, Git, Node, React, Vite, Tauri, Rust, SQLite | 0 € (open source) | — | licenze da registrare in `DECISIONS.md` |
| MSVC Build Tools | 0 € | termini di licenza da leggere prima dell'installazione | NON VERIFICATO |
| GitHub Actions (CI, build Windows) | 0 € su repo **pubblico** | se il repo diventa privato i minuti sono limitati | da mantenere pubblico o con limite di spesa a 0 € |
| OpenRouter (modelli `:free`) | 0 € | comprare crediti (≥ 10 $ alza il limite da 50 a 1000 richieste/giorno) | limiti datati in `freelm`, NON VERIFICATO oggi |
| Google AI Studio | 0 € (livello gratuito) | attivare la fatturazione sul progetto Google Cloud | privacy del livello gratuito NON VERIFICATA |
| Groq, Cerebras, Mistral (Experiment), Cohere (trial), Z.ai (Flash) | 0 € | passare a un piano a pagamento; Cohere trial non commerciale; Mistral Experiment: possibile uso dei dati | NON VERIFICATO |
| NVIDIA NIM | 0 € finché durano i crediti gratuiti | ricaricare i crediti | NON VERIFICATO |
| Cloudflare Workers AI | 0 € entro la quota gratuita giornaliera | passare al piano Workers a pagamento | NON VERIFICATO |
| Kilo / OVHcloud senza chiave | 0 € | le rotte gratuite possono registrare i prompt | disattivati in GÉNESIS |
| Firma del codice per Windows | a pagamento | — | **non usata** |
| Hosting, VPS, domini | a pagamento o con carta | — | **non usati** (tutto locale) |
| Credenziali proxy di questa sessione cloud (Gemini, OpenRouter) | — | appartengono all'ambiente di sviluppo, non a GÉNESIS | **non usate** |

---

## 11. Primo set di compiti di sviluppo (Fase 1)

| ID | Compito | Fatto quando |
|---|---|---|
| T1 | Decisioni D-01…D-05 (§13) | registrate in `DECISIONS.md` |
| T2 | Scheletro `GENESIS/` + `pyproject.toml` + `.gitignore` dati + CI Linux/Windows filtrata su `GENESIS/**` | CI verde con un test vuoto su entrambi gli OS |
| T3 | Config: default + profilo + override utente, validazione | test su valori errati |
| T4 | Log JSON a rotazione con oscuramento dei segreti | test: una chiave finta non compare mai nei log |
| T5 | Event bus in-process, errori isolati per sottoscrittore | test |
| T6 | SQLite: connessione WAL, migrazioni versionate | test: migrazione da zero e incrementale |
| T7 | Backup (API di backup SQLite), esportazione/importazione JSON | test di andata e ritorno |
| T8 | Gestore compiti persistente + worker sequenziale | test di ripresa dopo interruzione |
| T9 | Permessi livelli 1–5, richieste di approvazione, audit append-only | test di escalation negata |
| T10 | Rilevamento hardware senza dipendenze + scelta del profilo | test su Linux e Windows (CI); esecuzione reale sul PC |
| T11 | CLI `genesis status` / `doctor` | output verificato |
| T12 | Documenti di continuità (§19 del Master Prompt) dentro `GENESIS/documentation/` | presenti e aggiornati |

---

## 12. Comandi che richiedono autorizzazione

**A. In questa sessione cloud (livelli 2–3)**

```bash
# Verificare la base di freelm (installa solo in .venv, già ignorata da git)
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]" && .venv/bin/pytest -q
# Fase 1: creare file nuovi sotto GENESIS/ e testarli
python3.13 -m pytest -q GENESIS/tests
# Salvare il lavoro sul branch di sviluppo
git add GENESIS && git commit && git push -u origin claude/genesis-phase-0-audit-zrvq7a
```

**B. Sul PC — sola lettura, nessuna modifica**

- Il blocco PowerShell dell'Appendice A.
- `winget show --id Python.Python.3.13` (e così per ogni ID qui sotto), per
  verificare gli ID prima di qualunque installazione.

**C. Sul PC — installazioni (livello 4, solo con approvazione)**

```powershell
winget install -e --id Python.Python.3.13
winget install -e --id Git.Git
# Fase 2a, solo se si sviluppa il frontend sul PC
winget install -e --id OpenJS.NodeJS.LTS
# Fase 2b, solo se si sceglie la build locale di Tauri (sconsigliata con 4 GB)
winget install -e --id Rustlang.Rustup
winget install -e --id Microsoft.VisualStudio.2022.BuildTools --override "--passive --wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
# Solo se l'audit riporta "WebView2: non trovato"
winget install -e --id Microsoft.EdgeWebView2Runtime
```

**D. Mai senza approvazione esplicita (livello 5)**

- Push di tag `v*` o `js-v*` (pubblicano `freelm` su PyPI, npm, Docker).
- Attivare fatturazione, comprare crediti, attivare prove che richiedono una carta.
- Cambiare la visibilità del repo o fare merge su `main`.

---

## 13. Decisioni richieste al proprietario

| ID | Decisione | Proposta |
|---|---|---|
| D-01 | Dove vive GÉNESIS | Cartella `GENESIS/` in questo fork, isolata da `freelm` (è l'unico repo accessibile a questa sessione). Alternativa: un repo separato. |
| D-02 | Struttura del codice | Le cartelle del Master Prompt dentro il pacchetto `genesis/`, come in §7. |
| D-03 | Lingua | Codice e identificatori in inglese, documentazione in italiano. |
| D-04 | Versione di Python sul PC | 3.13 (supporta Windows 10; minimo supportato dal codice: 3.11). |
| D-05 | Interfaccia | Prima la UI web servita dal Core (2a), poi Tauri compilato in CI (2b). |

---

## Appendice A — Audit del PC (PowerShell, sola lettura)

Incollare in una finestra di PowerShell. Legge solo informazioni di sistema e
una chiave di registro; copia il risultato negli appunti.

```powershell
$r = & {
  "== WINDOWS =="
  $os = Get-CimInstance Win32_OperatingSystem
  "{0} | build {1} | {2}" -f $os.Caption, $os.BuildNumber, $os.OSArchitecture
  "RAM totale: {0:N1} GB | libera ora: {1:N1} GB" -f ($os.TotalVisibleMemorySize/1MB), ($os.FreePhysicalMemory/1MB)
  "PowerShell: $($PSVersionTable.PSVersion)"
  "== CPU =="
  Get-CimInstance Win32_Processor | ForEach-Object { "{0} | {1} core / {2} thread | {3} MHz" -f $_.Name.Trim(), $_.NumberOfCores, $_.NumberOfLogicalProcessors, $_.MaxClockSpeed }
  "== GPU =="
  Get-CimInstance Win32_VideoController | ForEach-Object { "{0} | driver {1} | VRAM ~{2:N0} MB" -f $_.Name, $_.DriverVersion, ($_.AdapterRAM/1MB) }
  "== DISCHI =="
  Get-PhysicalDisk -ErrorAction SilentlyContinue | ForEach-Object { "{0} | {1} | {2:N0} GB" -f $_.FriendlyName, $_.MediaType, ($_.Size/1GB) }
  Get-PSDrive -PSProvider FileSystem | Where-Object Used -ne $null | ForEach-Object { "{0}: usati {1:N1} GB | liberi {2:N1} GB" -f $_.Name, ($_.Used/1GB), ($_.Free/1GB) }
  "== PAGEFILE =="
  Get-CimInstance Win32_PageFileUsage | ForEach-Object { "{0} | {1} MB" -f $_.Name, $_.AllocatedBaseSize }
  "== STRUMENTI =="
  foreach ($c in 'python','py','node','npm.cmd','git','rustc','cargo','code','winget') {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $cmd) { "$c : MANCANTE" }
    elseif ($c -eq 'python' -and $cmd.Source -like '*WindowsApps*') { "python : solo alias WindowsApps (da verificare)" }
    else { "$c : " + ((& $c --version 2>&1) | Select-Object -First 1) }
  }
  "== WEBVIEW2 (serve a Tauri) =="
  $id = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
  $wv = (Get-ItemProperty "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\$id" -ErrorAction SilentlyContinue).pv
  if (-not $wv) { $wv = (Get-ItemProperty "HKCU:\Software\Microsoft\EdgeUpdate\Clients\$id" -ErrorAction SilentlyContinue).pv }
  if ($wv) { "WebView2: $wv" } else { "WebView2: non trovato" }
  "== VISUAL C++ BUILD TOOLS (serve a Rust/Tauri) =="
  $vsw = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
  if (Test-Path $vsw) { & $vsw -products * -property displayName } else { "non trovati" }
} | Out-String -Width 200
$r; $r | Set-Clipboard; "(Risultato copiato negli appunti: incollalo in chat)"
```

## Appendice B — Comandi eseguiti in questa sessione (tutti di sola lettura)

- `uname`, `/etc/os-release`, `nproc`, `lscpu`, `free`, `df`, `lspci`,
  `nvidia-smi`: hardware del container.
- `<strumento> --version` per Python, pip, uv, Node, npm, pnpm, yarn, bun, Rust,
  cargo, git, docker, gcc, make, cmake e altri.
- `git status`, `git branch -a`, `git log`, `git remote -v`, `git shortlog`.
- `find`, `du`, `wc -l`, `cat`, `sed -n`, `grep` sui file del repo.
- `python3 -c "importlib.util.find_spec(...)"` per i moduli disponibili.
- `ruff check --no-cache src tests examples` → nessun errore.
- `gh api -X GET search/repositories` → repo pubblico, è un fork.
- `list_computer_folders` (tre volte) → nessuna cartella del PC disponibile.
