# GÉNESIS — core (Fase 1)

Piattaforma di intelligenza estensibile. Questa cartella contiene il **Core**:
funziona da solo, senza interfaccia grafica, senza provider di IA esterni e
senza dipendenze oltre a Python.

| Componente | Stato |
|---|---|
| Configurazione, log con oscuramento dei segreti, bus di eventi | IMPLEMENTATO e testato |
| Database SQLite: migrazioni, backup verificati, ripristino, esportazione/importazione | IMPLEMENTATO e testato |
| Permessi a 5 livelli, approvazioni del proprietario, audit a catena di hash | IMPLEMENTATO e testato |
| Coda dei compiti persistente con ripresa dopo un crash | IMPLEMENTATO e testato |
| Rilevamento hardware e profili di esecuzione (`lite-4gb`, `standard`, `gpu`) | IMPLEMENTATO e testato (Windows: in CI) |
| Interfaccia desktop, router dei modelli, agenti, strumenti | PENDENTE (Fasi 2–5) |

## Avvio rapido su Windows

Serve solo Python 3.11 o più recente (consigliato 3.13). Non si installa nient'altro.

```powershell
# 1. Scarica il codice (con Git, oppure "Code > Download ZIP" su GitHub, branch claude/genesis-phase-0-audit-zrvq7a)
git clone -b claude/genesis-phase-0-audit-zrvq7a https://github.com/tansaavatalia-commits/freelm.git
cd freelm\GENESIS

# 2. Diagnostica: hardware reale del PC, profilo scelto, controlli
py -3 -m genesis doctor

# 3. Uso di base
py -3 -m genesis status
py -3 -m genesis project add "Il mio progetto"
py -3 -m genesis task submit system.hardware_snapshot --project "Il mio progetto"
py -3 -m genesis task run
py -3 -m genesis backup create
```

I dati stanno in `%LOCALAPPDATA%\GENESIS` (oppure nella cartella indicata da
`--home` o dalla variabile `GENESIS_HOME`), **mai** nel repository.

## Comandi

| Comando | Cosa fa |
|---|---|
| `status [--json]` | stato: profilo, progetti, compiti, approvazioni, audit |
| `doctor [--json]` | hardware, profilo di esecuzione e controlli di salute |
| `project add / list / archive` | gestione dei progetti |
| `task kinds / submit / list / show / run / cancel` | coda dei compiti (eseguiti uno alla volta) |
| `approvals list / approve / deny` | approvazioni per le azioni di livello 4–5 |
| `backup create / list / restore --confirm` | backup verificati e ripristino (con copia di sicurezza automatica) |
| `export [file]` / `import file` | spostare GÉNESIS su un altro PC |
| `audit verify / tail` | verifica e lettura del registro di audit |

Codici di uscita: 0 ok · 1 errore · 2 errore di uso o di configurazione.

## Migrare su un altro PC

```powershell
py -3 -m genesis export C:\percorso\genesis-export.json      # sul PC vecchio
py -3 -m genesis import C:\percorso\genesis-export.json      # sul PC nuovo (cartella dati vuota)
```

## Sviluppo

```bash
cd GENESIS
python -m pytest          # test (serve solo pytest)
ruff check .              # lint
```

Documentazione: [`documentation/`](documentation/) — stato, architettura,
decisioni, sicurezza, politica dei costi, prossimi passi.
