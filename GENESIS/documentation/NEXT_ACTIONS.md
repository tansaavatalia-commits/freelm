# Prossime azioni

## Per il proprietario

1. **Provare GÉNESIS sul PC** (serve solo Python ≥ 3.11), in PowerShell:
   ```powershell
   git clone -b claude/genesis-phase-0-audit-zrvq7a https://github.com/tansaavatalia-commits/freelm.git
   cd freelm\GENESIS
   py -3 -m genesis doctor
   py -3 -m genesis serve
   ```
   (Se la cartella esiste già: `cd freelm; git pull; cd GENESIS`.) Incollare in chat il testo di `doctor`.
2. **Motore online** (facoltativo): chiave gratuita OpenRouter, poi `README.md` → «Motore online».
3. **Decidere sulle v2**: pagina «Miglioramento» → «Rileva, proponi e valuta» → approvare o rifiutare.
4. **Dataset indipendente** (consigliato): 20–40 richieste scritte da te, importate con `genesis lab import`.
5. Scegliere la licenza (D-06).

## Per lo sviluppo — note dalla sessione sul PC (2026-11-26)

- `ruff` non è installato sul PC: la CI controllerà `genesis/tools/index.py` e le modifiche a `registry.py`.
- L'interfaccia (pagina strumenti) non è stata toccata: `text.find` compare già nell'elenco perché viene dal registro.
- Sul PC usare Python con il percorso completo `%LOCALAPPDATA%\Python\pythoncore-3.15-64\python.exe`
  (il comando `py` riavvia l'installazione automatica di Python).
- Passo 4 fatto (43,9 MB, 9/9 pagine senza errori). Passo 5 fatto (portabilità riuscita).
- Prossimo passo sul PC: Passo 8 (Release: `Avvia-GENESIS.bat`, `GUIDA.md`, validazione finale);
  Passo 6 (motore online) e Passo 7 (decisioni) dipendono dal proprietario.
- L'esperimento del motore online (Passo 6) prenderà il numero R-006.
- Interfaccia «Núcleo» (globo, D-36) fatta sul PC con Node. Da fare nel cloud: eseguire `e2e/smoke.cjs` con
  Playwright (non eseguito sul PC). Console sul globo fatta. Possibile sviluppo: luci per compiti e motori,
  non solo agenti.
- Chat nel Núcleo fatta (tappa 1 di RICERCA_CONCORRENTI.md). Prossimo: Passo 6 (chiave OpenRouter del
  proprietario + `pip install --user ..` con il suo permesso + `genesis online enable --confirm`), poi provare lo
  streaming dal vivo; poi tappe 4–6 (documenti, ricerca con fonti, consiglio multi-modello sul globo).
- Il test `test_mcp_list_call_errors_and_timeout` usa un timeout di 2 s: sul PC carico (globo + browser) è
  fallito una volta. Valutare un timeout più largo solo nel test.

## Per lo sviluppo — passo esatto successivo

**Fase 10 (Release):** validazione integrale sul PC reale (doctor, serve, RAM), test di portabilità
(export → import su un'altra cartella/PC), pacchetto Windows (Tauri compilato in GitHub Actions oppure
avvio con un collegamento `.bat` che lancia `py -3 -m genesis serve`), documentazione d'uso finale.
