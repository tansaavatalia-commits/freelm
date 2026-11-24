# Rapporto dei test

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

- **PC del proprietario (Windows 10, 4 GB):** non collegato alla sessione.
  PENDENTE: `py -3 -m genesis doctor` sul PC.
- Test di `freelm` (non toccato da questa fase).
