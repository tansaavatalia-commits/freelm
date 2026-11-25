# Passaggio a una nuova sessione di Claude Code sul PC del proprietario

> **Come usare questo file:** apri Claude Code sul PC (app desktop o terminale), avvialo in una cartella di
> lavoro (per esempio `C:\Users\<tu>\Progetti`) e incolla **tutto** questo testo come primo messaggio.
> Sotto questa riga parla a Claude.

---

Sei Claude Code e lavori **direttamente sul PC Windows del proprietario**. Continui il progetto **GÉNESIS**,
sviluppato finora in una sessione cloud che non poteva vedere questo computer. Il tuo compito principale è
fare ciò che da lì era impossibile: **verificare GÉNESIS sull'hardware reale** e preparare la **Fase 10 (Release)**.
Rispondi al proprietario in **italiano**, con frasi semplici: non è uno sviluppatore.

## 1. Regole assolute (dal Master Prompt del proprietario)

- **Budget 0 €.** Niente acquisti, abbonamenti, crediti, prove che chiedano una carta, servizi a pagamento.
  Non presumere che un servizio sia gratuito: verifica e registra in `GENESIS/documentation/COST_POLICY.md`.
- **Mai senza approvazione esplicita del proprietario (chiedi prima, ogni volta):** installazioni (anche
  `winget`/`pip`), modifiche di Windows o del registro, cancellazioni definitive, pubblicazioni, cambi di permessi,
  download o esecuzione di programmi non verificati, push di tag `v*` o `js-v*` (pubblicherebbero `freelm`).
- **Prima sola lettura**, poi modifiche: comincia con comandi che non cambiano nulla.
- **Segreti:** non chiedere mai al proprietario di incollare chiavi in chat; non stamparle; non committarle.
- **Trasparenza:** distingui sempre IMPLEMENTATO / SIMULATO / PENDENTE / NON VERIFICATO. Non dichiarare test
  passati se non li hai eseguiti, né miglioramenti senza un confronto nel Research Lab.
- **Hardware limitato** (Windows 10, 4 GB di RAM dichiarati): niente modelli pesanti, un processo alla volta.

## 2. Il progetto in breve

- Repository: `https://github.com/tansaavatalia-commits/freelm` (fork pubblico di `freelm`, licenza MIT).
- Branch di lavoro: **`claude/genesis-phase-0-audit-zrvq7a`**. Tutto GÉNESIS è nella cartella **`GENESIS/`**.
- `freelm` (cartelle `src/`, `js/`, ecc.) è un'altra libreria: **non modificarla**. GÉNESIS la usa solo come
  adattatore opzionale per il motore online.
- Sul branch `claude/eloquent-newton-uke0z7` c'è un **progetto diverso** ("GENESIS DROP ENGINE"): non toccarlo.
- Documentazione di continuità: `GENESIS/documentation/` — leggi **prima** `PROJECT_STATUS.md`,
  `NEXT_ACTIONS.md`, `ARCHITECTURE.md`, `SECURITY.md`, `COST_POLICY.md`, `DECISIONS.md`, `RESEARCH_LOG.md`.

## 3. Stato attuale (versione 0.9.0)

| Fase | Stato |
|---|---|
| 0 Audit | fatto, **tranne l'hardware reale di questo PC** (lo fai tu) |
| 1 Core (config, SQLite, eventi, compiti, permessi 1–5, audit, backup) | implementato e testato (Linux + Windows in CI) |
| 2a Interfaccia nel browser (`genesis serve`) | implementata, test end-to-end in Chromium |
| 2b Finestra Tauri | PENDENTE |
| 3 Router dei motori (locale + OpenRouter gratuito) | implementato; motore online **mai provato dal vivo** |
| 4 Agenti (8, Verifier, Director, Consiglio) | implementati |
| 5 Strumenti e MCP | implementati |
| 6 Research Lab | implementato |
| 7 Motori GÉNESIS (6) | implementati; v2 sperimentali |
| 8 Model Development Lab | implementato (niente training su questo PC) |
| 9 Auto-miglioramento | implementato; promozione solo con prove + approvazione del proprietario |
| 10 Release | **da fare (con te, su questo PC)** |

Fatti verificati nel cloud: 207 test Python passati (Linux, Python 3.13); CI su GitHub verde anche su
Windows (Python 3.11 e 3.13); `genesis serve` ≈ 32 MB di RAM su Linux. GÉNESIS non ha dipendenze oltre a Python.

## 4. Cosa fare, in ordine (con i criteri per dire «fatto»)

### Passo 1 — Audit hardware in sola lettura
Esegui in PowerShell (non modifica nulla):

```powershell
$os = Get-CimInstance Win32_OperatingSystem
"{0} | build {1} | {2} | RAM {3:N1} GB, libera {4:N1} GB" -f $os.Caption, $os.BuildNumber, $os.OSArchitecture, ($os.TotalVisibleMemorySize/1MB), ($os.FreePhysicalMemory/1MB)
Get-CimInstance Win32_Processor | ForEach-Object { "CPU: {0} | {1} core / {2} thread" -f $_.Name.Trim(), $_.NumberOfCores, $_.NumberOfLogicalProcessors }
Get-CimInstance Win32_VideoController | ForEach-Object { "GPU: {0} | VRAM ~{1:N0} MB" -f $_.Name, ($_.AdapterRAM/1MB) }
Get-PhysicalDisk -ErrorAction SilentlyContinue | ForEach-Object { "Disco: {0} | {1} | {2:N0} GB" -f $_.FriendlyName, $_.MediaType, ($_.Size/1GB) }
Get-PSDrive -PSProvider FileSystem | Where-Object Used -ne $null | ForEach-Object { "{0}: liberi {1:N1} GB" -f $_.Name, ($_.Free/1GB) }
foreach ($c in 'py','git','node') { $x = Get-Command $c -ErrorAction SilentlyContinue; if ($x) { "$c : " + ((& $c --version 2>&1) | Select-Object -First 1) } else { "$c : MANCANTE" } }
$id='{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'; $wv=(Get-ItemProperty "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\$id" -ErrorAction SilentlyContinue).pv; "WebView2: $(if($wv){$wv}else{'non trovato'})"
(Get-HotFix | Sort-Object InstalledOn -Descending | Select-Object -First 1 | ForEach-Object { "Ultimo aggiornamento Windows: $($_.HotFixID) del $($_.InstalledOn)" })
```
**Fatto quando:** i valori reali sono scritti nella sezione 1a di `GENESIS/documentation/FASE_0_AUDIT.md`
(sostituendo «PENDENTE») e in `PROJECT_STATUS.md`. Segnala se Windows non riceve più aggiornamenti (rischio R2).

### Passo 2 — Prerequisiti
- Serve **Python ≥ 3.11** (consigliato 3.13) e **Git**. Se mancano, **chiedi** al proprietario e solo dopo il suo sì:
  `winget install -e --id Python.Python.3.13` / `winget install -e --id Git.Git` (poi riapri il terminale).
- Ottieni il codice: se la cartella `freelm` non esiste
  `git clone -b claude/genesis-phase-0-audit-zrvq7a https://github.com/tansaavatalia-commits/freelm.git`,
  altrimenti `cd freelm; git checkout claude/genesis-phase-0-audit-zrvq7a; git pull`.

**Fatto quando:** `py -3 --version` ≥ 3.11 e `git log -1 --oneline` mostra l'ultimo commit del branch.

### Passo 3 — Diagnosi e test sul PC reale
```powershell
cd freelm\GENESIS
py -3 -m genesis doctor
py -3 -m genesis doctor --json > $env:TEMP\genesis-doctor.json
```
- Il profilo atteso su 4 GB è **`lite-4gb`**. Se è diverso, capisci perché (RAM reale?) e annotalo.
- Test automatici: servono `pytest` (gratuito). **Chiedi** prima di installarlo:
  `py -3 -m pip install --user pytest` e poi `py -3 -m pytest` (atteso: 207 passati, 1 saltato).

**Fatto quando:** l'output di `doctor` e l'esito dei test sono in `TEST_REPORT.md` (sezione «PC del
proprietario»), con eventuali errori riportati onestamente.

### Passo 4 — Interfaccia e consumo di RAM reale
```powershell
py -3 -m genesis serve
```
Si apre il browser su `http://127.0.0.1:8765`. Con il proprietario, apri ogni pagina (Dashboard, Progetti,
Compiti, Agenti, Laboratorio, Motori, Miglioramento, Approvazioni, Diagnostica). In un **secondo** terminale:
```powershell
Get-Process python*, py -ErrorAction SilentlyContinue | Select-Object Name, Id, @{n='RAM_MB';e={[math]::Round($_.WorkingSet64/1MB,1)}}
Get-Process msedge, chrome -ErrorAction SilentlyContinue | Measure-Object WorkingSet64 -Sum | ForEach-Object { "Browser: {0:N0} MB" -f ($_.Sum/1MB) }
```
**Fatto quando:** RAM del processo GÉNESIS, RAM del browser e RAM libera del sistema sono in `TEST_REPORT.md`
e `PROJECT_STATUS.md`, insieme a qualunque problema visto nelle pagine.

### Passo 5 — Prova di portabilità
```powershell
py -3 -m genesis project add "Prova portabilità"
py -3 -m genesis export $env:TEMP\genesis-export.json
py -3 -m genesis --home $env:TEMP\genesis-nuovo-pc import $env:TEMP\genesis-export.json
py -3 -m genesis --home $env:TEMP\genesis-nuovo-pc project list
py -3 -m genesis --home $env:TEMP\genesis-nuovo-pc audit verify
```
**Fatto quando:** il progetto compare nella nuova cartella e la catena di audit è intatta. Annotalo.
(La cartella di prova in `%TEMP%` si può lasciare; non cancellare dati del proprietario.)

### Passo 6 — Motore online (facoltativo, solo se il proprietario vuole)
1. Il proprietario crea una chiave **gratuita** su https://openrouter.ai/keys (non deve comprare crediti).
2. **Lui** la salva, senza mostrarla a te: `setx OPENROUTER_API_KEY "LA-SUA-CHIAVE"`, poi riapre il terminale.
3. Con il suo consenso all'installazione: `py -3 -m pip install --user ..` (installa `freelm` dal repository).
4. `py -3 -m genesis online enable --confirm` poi `py -3 -m genesis ask "Spiegami in una frase cos'è GÉNESIS"`.
5. Se funziona, un esperimento piccolo (rispetta la quota gratuita):
   `py -3 -m genesis lab run --dataset qa-facts --subject agent:researcher --allow-remote --sample 10`
   e registra il risultato come **R-005** in `RESEARCH_LOG.md`.

**Fatto quando:** la risposta reale (o l'errore reale) è registrata; `COST_POLICY.md` aggiornato con data e limiti visti.

### Passo 7 — Decisioni del proprietario
- **Versioni v2** (classificatore e calcolo): pagina «Miglioramento» → «Rileva, proponi e valuta» → il
  proprietario approva o rifiuta. Spiegagli il limite: i dati di prova sono interni (`RESEARCH_LOG.md`, R-003).
- **Dataset indipendente** (consigliato): aiutalo a scrivere 20–40 domande sue in un JSON
  (`{"name": "...", "version": "1", "description": "...", "items": [{"input": "...", "expected": "math", "scorer": "label"}]}`)
  e importalo con `py -3 -m genesis lab import file.json`.
- **Licenza** di GÉNESIS (decisione D-06, ancora aperta).

### Passo 8 — Fase 10 (Release), solo dopo i passi 1–5
- **Avvio con doppio clic:** crea `GENESIS/Avvia-GENESIS.bat` (nel repository) che fa `cd /d "%~dp0"` e
  `py -3 -m genesis serve`. Un collegamento sul Desktop solo se il proprietario lo chiede.
- **Guida per il proprietario** `GENESIS/GUIDA.md`: avvio, pagine, backup, migrazione, motore online, cosa fare se…
- **Validazione integrale:** ripeti doctor, test, serve e portabilità sulla versione finale.
- **Versione 1.0.0** solo quando tutti i criteri sono verificati: aggiorna `genesis/__init__.py`, `CHANGELOG.md`,
  `ROADMAP.md`. **Non** creare tag (`v*`) senza approvazione esplicita.
- Tauri (finestra nativa) resta facoltativo: valutalo solo se WebView2 è presente e la RAM lo permette;
  compilazione su GitHub Actions, mai sul PC da 4 GB.

## 5. Come lavorare con il repository

- Lavora solo sul branch `claude/genesis-phase-0-audit-zrvq7a`, solo dentro `GENESIS/`.
- Prima di ogni commit: `cd GENESIS; py -3 -m pytest` (se pytest è installato).
- Se modifichi l'interfaccia (`GENESIS/desktop/frontend`), serve Node ≥ 20.19 per ricompilare
  (`npm ci && npm run build`); la CI controlla che `genesis/api/static` corrisponda ai sorgenti.
  **Se Node non c'è, non modificare l'interfaccia**: annota la modifica in `NEXT_ACTIONS.md` per la sessione cloud.
- Commit piccoli e descrittivi. Per il push servono le credenziali GitHub del proprietario: se non sono
  configurate, lascia i commit locali e diglielo (non chiedere token in chat).
- A fine sessione aggiorna `PROJECT_STATUS.md`, `TEST_REPORT.md`, `NEXT_ACTIONS.md`, `CHANGELOG.md`
  con: file modificati, test eseguiti e loro esito, problemi aperti, passo successivo esatto.

## 6. Comandi utili di GÉNESIS

`doctor` · `status` · `serve` · `project add/list` · `task submit/run/list` · `ask "testo"` · `providers` ·
`agents list/run/direct/council` · `tools list/call` · `lab datasets/run/compare/reproduce/report` ·
`engines list/run` · `models list/check/plan` · `improve components/detect/propose/evaluate/approve/rollback` ·
`backup create/restore --confirm` · `export` / `import` · `audit verify`.
Tutti con `py -3 -m genesis <comando>` dalla cartella `freelm\GENESIS`; i dati stanno in `%LOCALAPPDATA%\GENESIS`.

## 7. Prima cosa da dire al proprietario

Presentati in due righe, spiega che farai prima solo controlli che non cambiano nulla (Passo 1), e chiedigli
il permesso prima di qualunque installazione. Poi procedi un passo alla volta, mostrando i risultati in modo semplice.
