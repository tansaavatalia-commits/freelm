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

## Per lo sviluppo — passo esatto successivo

**Fase 10 (Release):** validazione integrale sul PC reale (doctor, serve, RAM), test di portabilità
(export → import su un'altra cartella/PC), pacchetto Windows (Tauri compilato in GitHub Actions oppure
avvio con un collegamento `.bat` che lancia `py -3 -m genesis serve`), documentazione d'uso finale.
