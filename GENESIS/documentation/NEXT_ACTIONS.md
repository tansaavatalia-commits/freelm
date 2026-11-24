# Prossime azioni

## Per il proprietario

1. **Provare GÉNESIS sul PC** (serve solo Python ≥ 3.11), in PowerShell:
   ```powershell
   git clone -b claude/genesis-phase-0-audit-zrvq7a https://github.com/tansaavatalia-commits/freelm.git
   cd freelm\GENESIS
   py -3 -m genesis doctor
   py -3 -m genesis serve
   ```
   Incollare in chat il testo di `doctor`; dire se la pagina si apre e quanta RAM
   indica la Dashboard («GÉNESIS ora usa … MB»). Se il clone esiste già:
   `cd freelm; git pull` invece di `git clone`.
2. Scegliere la licenza di GÉNESIS (D-06).
3. (Dalla Fase 3) Sistemare le chiavi OpenRouter/Gemini dell'ambiente cloud.

## Per lo sviluppo — passo esatto successivo

**Fase 2b (Tauri)** — da fare solo dopo la prova sul PC, per sapere se WebView2 è
presente e quanta RAM resta: shell Tauri 2 che avvia `genesis serve --no-browser`
come processo figlio e apre la stessa interfaccia in una finestra nativa; build
Windows su GitHub Actions (gratuita, repo pubblico); nessuna build locale.

In alternativa, se il proprietario preferisce l'intelligenza prima della finestra:
**Fase 3** — interfaccia Provider propria, registro, router con filtro «solo
gratuito», Local Engine deterministico, adattatore `freelm` disattivato di default.
