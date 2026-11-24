# Roadmap

| Fase | Obiettivo | Criterio di chiusura | Stato |
|---|---|---|---|
| 0 | Audit e piano | rapporto consegnato | completata (hardware PC PENDENTE) |
| 1 | Core: config, SQLite, eventi, compiti, permessi, log, test | test verdi su Linux e Windows; `doctor` eseguito sul PC reale | implementata; manca l'esecuzione sul PC |
| 2a | API locale + interfaccia web (React + TS + Vite): shell, Dashboard, Progetti, Compiti | ogni pulsante fa qualcosa di reale; test end-to-end; RAM misurata sul PC | implementata e testata (~28 MB su Linux); manca la misura sul PC |
| 2b | Tauri 2 compilato in GitHub Actions | l'installer parte sul PC | prossima (dopo la prova sul PC) |
| 3 | Provider Manager, Intelligent Router, Local/Online Engine, adattatore freelm | funziona con zero provider; un provider a pagamento non viene mai scelto | implementata e testata; prova reale online PENDENTE (chiavi) |
| 4 | Agent Factory (8 agenti), Intelligence Council v0 | nessuna auto-escalation; il Council si misura contro una baseline | implementata (v0); misura contro baseline nel Research Lab (Fase 6) |
| 5 | Strumenti, connettori, MCP con autorizzazione centrale | ogni chiamata autorizzata e registrata | implementata e testata |
| 6 | Research Lab: esperimenti e benchmark riproducibili | un esperimento si ripete con lo stesso risultato | implementata e verificata (riproduzione identica) |
| 7 | Motori GÉNESIS (Reasoning, Code, Research, Data, Memory, Multimodal) | ogni motore dichiara cosa è proprio e cosa è esterno | PENDENTE |
| 8 | Model Development Lab | nessun training sul PC da 4 GB | PENDENTE |
| 9 | Self-Improvement controllato | sicurezza, permessi e costi immutabili dal sistema | PENDENTE |
| 10 | Release e test di portabilità | migrazione su un altro PC senza ricostruire | PENDENTE |
