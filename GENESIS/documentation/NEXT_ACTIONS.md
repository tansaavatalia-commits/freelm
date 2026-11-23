# Prossime azioni

## Per il proprietario (sbloccano il lavoro)

1. **Provare il core sul PC** (5 minuti, nessuna installazione oltre a Python):
   segui «Avvio rapido su Windows» in `GENESIS/README.md` e incolla in chat
   l'output di `py -3 -m genesis doctor`. Se Python manca:
   `winget install -e --id Python.Python.3.13` (livello 4: lo decidi tu).
2. Scegliere la licenza di GÉNESIS (D-06), per esempio MIT o Apache-2.0.
3. (Facoltativo, serve dalla Fase 3) Sistemare le chiavi dell'ambiente cloud:
   OpenRouter → Network secrets, valore `sk-or-v1-…` senza «Bearer»;
   Gemini → chiave da aistudio.google.com/apikey su un progetto senza fatturazione.

## Per lo sviluppo — passo esatto successivo

**Fase 2a:** API HTTP locale in `genesis/api/` (libreria standard,
`ThreadingHTTPServer` su 127.0.0.1, token generato nella cartella dati, una sola
connessione SQLite servita da un thread dedicato) con endpoint per status,
doctor, progetti, compiti e approvazioni; poi `desktop/frontend/` (React + TS +
Vite) con shell, Dashboard, Progetti e Compiti, servito dal core.
Criteri: test dell'API, test end-to-end con Playwright, nessun pulsante senza funzione.
