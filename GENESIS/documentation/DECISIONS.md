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
| D-12 | CI su Linux e Windows (`genesis-core-ci.yml`), filtrata su `GENESIS/**` | verifica reale su Windows a costo zero (repo pubblico) | adottata |
| D-13 | Lo script di avvio dell'ambiente cloud (pacchetti npm non verificati) è stato rimosso | rischio di supply chain; non serviva | eseguita con approvazione |
| D-14 | `GENESIS/` (questo progetto) e `genesis-drop-engine/` (branch `claude/eloquent-newton-uke0z7`) sono **due progetti diversi**: restano separati | confermato dal proprietario il 2026-11-24; workflow già con nomi diversi. Entrambi usano il nome di pacchetto Python `genesis`: non installarli nello stesso ambiente | adottata |
| D-15 | L'interfaccia compilata (`genesis/api/static`) è nel repository; la CI verifica che corrisponda ai sorgenti | sul PC basta Python, niente Node né build | adottata |
| D-16 | React 19.2.9 + Vite 7.3.8 + TypeScript 6.0.3 (MIT/Apache-2.0), senza il plugin React di Vite | una dipendenza in meno; Vite compila JSX da solo | adottata |
| D-17 | Un solo esecutore di compiti per cartella dati, garantito da un lock del sistema operativo | rilasciato automaticamente se il processo muore; nessun compito eseguito due volte | adottata |
| D-18 | L'API ascolta solo su 127.0.0.1, con token, controllo di Host/Origin e CSP | protezione da altre pagine web e da DNS rebinding | adottata |
| D-19 | Il router usa un motore online solo con `remote_enabled` **e** `remote_free_verified` impostati dal proprietario; mai a pagamento; le richieste private restano locali | budget 0 € e privacy | adottata |
| D-20 | Classificazione delle richieste a regole (non con un modello) | trasparente, deterministica, senza costi; da misurare nel Research Lab | adottata |
| D-21 | Motore online = solo OpenRouter, solo modelli a prezzo zero; verifica della gratuità delegata dal proprietario a Claude e registrata in COST_POLICY | richiesta del proprietario del 2026-11-24 | adottata |
| D-22 | Agenti predefiniti a livello 1; agenti nuovi a livello 0 finché il proprietario non li abilita | nessun agente può ampliare i propri permessi | adottata |
| D-23 | Director e Consiglio v0 basati su regole (scomposizione, confronto, accordo), senza modello coordinatore | trasparenti e misurabili; da confrontare con una baseline nel Research Lab | adottata |
| D-24 | Strumenti in sandbox `<home>/workspace`; internet e MCP spenti finché il proprietario non li attiva | permessi minimi | adottata |
| D-25 | Server MCP avviati per una sola richiesta, non residenti | RAM limitata (4 GB) e nessun processo dimenticato | adottata |
| D-26 | Un miglioramento si dichiara solo con confronto appaiato sullo stesso hash del dataset, McNemar p < 0,05 e almeno 20 elementi | regola «nessun miglioramento senza prove comparabili» del Master Prompt | adottata |
| D-27 | Esperimenti privati di default; con il remoto al massimo 40 chiamate stimate | quota gratuita OpenRouter (~50/giorno) | adottata |
| D-28 | Dataset predefiniti registrati solo al primo uso del laboratorio | i comandi di sola lettura non devono scrivere (importazione su PC nuovo) | adottata |
| D-29 | Dataset di verifica pre-registrati con commit separato prima dei motori v2 | rende verificabile che i dati non sono stati cambiati dopo | adottata |
| D-30 | Errori trovati sui dati di verifica non vengono corretti nella stessa versione | evitare di adattarsi alla prova; vanno in una v3 da valutare su dati nuovi | adottata |
| D-31 | Ogni motore dichiara i componenti come algoritmo / strumento / modello esterno | regola del Master Prompt sulla trasparenza | adottata |
| D-32 | Modelli locali solo su indirizzi locali e spenti nel profilo lite-4gb | privacy e RAM | adottata |
| D-33 | Promozione di un componente: miglioramento dimostrato + nessun peggioramento dimostrato + approvazione del proprietario (livello 4) | ciclo di auto-miglioramento controllato | adottata |
| D-34 | Aree protette non migliorabili: permessi, sicurezza, audit, costi, accessi, configurazione, il ciclo stesso | Master Prompt §9 | adottata |
| D-35 | Le v2 restano sperimentali (attive v1) finché il proprietario non decide | i benchmark sono interni (R-003) | adottata |
| D-37 | Servizi senza chiave (Kilo, OVHcloud) ammessi solo con `keyless_allowed = true`, scelto dal proprietario il 2026-11-26 | Claude non può creare né incollare chiavi; il proprietario ha preferito non registrarsi; privacy dichiarata, chat «private» locali | adottata |
| D-36 | Interfaccia voluta dal proprietario (2026-11-26, sue parole): «un enorme globo formato da milioni di luci che rappresentano gli agenti del sistema, futuristico e molto tecnico». L'interfaccia a pagine della Fase 2a non corrisponde. | richiesta del proprietario, non registrata prima nei documenti | adottata (2026-11-26): pagina iniziale «Núcleo» con globo WebGL senza dipendenze, collegato ai dati veri (`/api/agents`, `/api/agent-runs`); le pagine esistenti restano nel menu. Luci adattive con tetto per profilo (lite-4gb 120.000, standard 1 milione, gpu 2 milioni) e massimo 30 fotogrammi/s: su questo PC il globo senza limiti toglieva CPU a GÉNESIS |
