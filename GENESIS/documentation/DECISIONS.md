# Registro delle decisioni

| ID | Decisione | Motivo | Stato |
|---|---|---|---|
| D-01 | GÉNESIS vive in `GENESIS/` dentro questo fork, separato da `freelm` | unico repo accessibile alla sessione; isolamento dalla CI e dalla regola di parità di freelm | adottata (il proprietario ha detto «procedi») |
| D-02 | Le cartelle del Master Prompt stanno dentro il pacchetto Python `genesis/` e si creano solo quando c'è codice reale | importabile e testabile; niente cartelle vuote | adottata |
| D-03 | Codice e identificatori in inglese; documentazione e messaggi all'utente in italiano | leggibilità per il proprietario | adottata |
| D-04 | Python ≥ 3.11 (consigliato 3.13 sul PC) | `tomllib` nella libreria standard; supporto di Windows 10 | adottata |
| D-05 | Prima l'interfaccia web servita dal core, poi Tauri compilato in CI | la build di Rust/Tauri su 4 GB è rischiosa | adottata |
| D-06 | Licenza di GÉNESIS | spetta al proprietario | **PENDENTE** |
| D-07 | Fase 1 senza dipendenze di runtime | niente da installare sul PC; meno superficie d'attacco | adottata |
| D-08 | Chi usa la CLI è il proprietario; per il livello 4 serve `--confirm`, registrato come approvazione monouso | il proprietario è fisicamente alla tastiera | adottata |
| D-09 | Audit a catena di hash con trigger append-only | manomissioni rilevabili senza servizi esterni | adottata |
| D-10 | L'importazione funziona solo in un database vuoto | impossibile sovrascrivere dati per errore | adottata |
| D-11 | Un profilo richiesto oltre le capacità dell'hardware viene ignorato | i motori pesanti restano spenti sui PC piccoli | adottata |
| D-12 | CI su Linux e Windows (`genesis-ci.yml`), filtrata su `GENESIS/**` | verifica reale su Windows a costo zero (repo pubblico) | adottata |
| D-13 | Lo script di avvio dell'ambiente cloud (pacchetti npm non verificati) è stato rimosso | rischio di supply chain; non serviva | eseguita con approvazione |
