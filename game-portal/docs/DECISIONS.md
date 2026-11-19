# GAME PORTAL — Registro decisioni

Stato: `PROPOSTA` (attende l'utente) · `APPROVATA` · `RESPINTA` · `ADR` (decisione tecnica interna)

| ID | Decisione | Stato | Costo | Note |
|---|---|---|---|---|
| D-001 | Spostare il progetto in un **repository GitHub privato dedicato** (`game-portal`) invece che dentro `freelm` | APPROVATA 2026-11-19 — **bloccata**: da questa sessione non posso creare repository; l'utente deve creare un repo vuoto | 0 € | `freelm` è un progetto non correlato |
| D-002 | Autorizzare il **push** del lavoro sul remoto (branch dedicato) | APPROVATA 2026-11-19 (eseguito) | 0 € | Il container è effimero: senza push il lavoro può andare perso |
| D-003 | Tesi di nicchia: giochi classici/rompicapo per **adulti**, daily challenge | APPROVATA 2026-11-19; validata in FASE 1 (lato domanda) | 0 € | Vedi COMPETITOR_RESEARCH §4 |
| D-004 | Stack: React + Vite + TS, Hono su Workers, D1, Pages, pnpm monorepo | APPROVATA 2026-11-19 | 0 € | Vedi ARCHITECTURE |
| D-005 | Analytics proprietari aggregati senza cookie, nessun tracker di terzi | APPROVATA 2026-11-19 | 0 € | Conferma legale in FASE 9 |
| D-006 | Nessun processore di pagamento fino a verifica di costi/fiscalità; Premium = lista d'attesa | APPROVATA 2026-11-19 | 0 € | Blocca i ricavi Premium |
| D-007 | Rete pubblicitaria come fallback | ASSORBITA in D-015 | 0 € | |
| D-008 | Autenticazione utenti senza email (passkey) in MVP per evitare un provider email | APPROVATA 2026-11-19 | 0 € | |
| D-009 | Revisione legale professionale prima del lancio | PROPOSTA | 300–1.500 € stimati | Fuori budget attuale: va autorizzata più avanti |
| D-010 | Acquisto del dominio al lancio controllato | PROPOSTA (FASE 11) | ~10–15 €/anno | Primo costo inevitabile |
| D-011 | Apertura del soggetto fiscale prima del primo incasso | PROPOSTA (FASE 11–12) | ~291–299 €/mese di contributi | Da decidere col commercialista |
| D-012 | Lingua iniziale: **inglese**; i18n predisposto per IT/HR/DE/ES in seguito | APPROVATA (inclusa in "Autorizzo tutto") | 0 € | Mercato mondiale/UE/USA |
| D-013 | Primi 10 giochi interni: Klondike, Spider, FreeCell, Sudoku, Mahjong a tessere, "Mines" (campo minato), Nonogram, word game del giorno (nome e grafica originali), Dama, Scacchi contro CPU | APPROVATA | 0 € | Nomi generici, nessun marchio di terzi ("Minesweeper", "Wordle", "Tetris" esclusi) |
| D-014 | Nome del brand: **Tabluo** (nome di lavoro; alternativa: **Mellodeck**) | APPROVATA 2026-11-19 (delegata: "ispirati ai colossi") | 0 € ora; dominio ~10–15 €/anno solo con autorizzazione | Stile dei leader (nome breve e inventato, come Poki o Y8) senza imitarne nessuno. `tabluo.com` e `mellodeck.com` risultavano liberi via RDAP il 2026-11-19 (nessun acquisto: possono essere registrati da altri in ogni momento). Ricerca web senza omonimi; somiglianza fonetica lontana con "Tableau" (software dati, altra classe) ⇒ verifica TMview/EUIPO classi 9/41/42 prima del lancio. Scartati: Joviplay (troppo simile all'app JoiPlay), nomi simili a Poki/CrazyGames |
| D-015 | Ammettere le reti pubblicitarie | APPROVATA 2026-11-19 ("se conviene, fallo": conviene, vedi FINANCIAL_MODEL v2) | 0 € | Modello **ibrido**: vendita diretta e sponsor prioritari; rete solo sull'inventario invenduto, solo dopo il consenso tramite CMP certificata TCF, mai sui giochi e mai annunci personalizzati ai minori. L'apertura dell'account presso la rete (accettazione dei termini, dati fiscali) resta un'autorizzazione separata in FASE 11 |

> "Autorizzo tutto" (2026-11-19) è stato interpretato come approvazione delle decisioni
> **proposte fino a quel momento** e del passaggio alla FASE 1. **Non** copre acquisti,
> account commerciali, pubblicazione del portale, contatti esterni o spese (D-009, D-010,
> D-011): per quelle chiederò di nuovo nel momento in cui servono, come da vincoli.
| D-016 | Catalogo e licenze in Git; build bloccata senza licenza valida; DB solo per lo stato dinamico | ADR APPROVATA 2026-11-19 | 0 € | Vedi ARCHITECTURE |
| D-017 | Autenticazione admin temporanea con Bearer token ≥ 32 caratteri (confronto a tempo costante), solo finché non esiste la SPA admin con passkey + MFA | ADR APPROVATA (temporanea) | 0 € | Da sostituire prima del lancio (G3) |
| D-018 | Telemetria Wrangler disattivata (`send_metrics = false`) | ADR APPROVATA | 0 € | Coerenza con la linea privacy |
| D-019 | Licenze dei 3 giochi interni registrate come `approved` in base all'autorizzazione generale del 2026-11-19 | APPROVATA, **da riconfermare a G4** | 0 € | Il titolare deve confermarle prima della pubblicazione pubblica |

