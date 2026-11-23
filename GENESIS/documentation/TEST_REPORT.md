# Rapporto dei test

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

### CI su GitHub Actions (`genesis-ci`)

Esito su Linux e Windows (Python 3.11 e 3.13): vedi la sezione aggiornata qui
sotto dopo l'esecuzione.

### Non eseguito

- **PC del proprietario (Windows 10, 4 GB):** non collegato alla sessione.
  PENDENTE: `py -3 -m genesis doctor` sul PC.
- Test di `freelm` (non toccato da questa fase).
