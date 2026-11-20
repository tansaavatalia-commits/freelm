# GENESIS DROP ENGINE

Sistema operativo privato per il dropshipping: scoperta prodotti, confronto fornitori,
calcolo della redditività reale, conformità UE, protezione della liquidità (politica
**Zero-Advance**), pubblicazione e gestione ordini su marketplace autorizzati.

> **Stato attuale: FASE 1 — Architettura e ricerca (in attesa di approvazione).**
> Non esiste ancora codice applicativo. Nessuna integrazione è attiva. Nessun servizio
> a pagamento è stato attivato. Nessun dato in questo repository è un risultato verificato
> di mercato: gli esempi numerici sono illustrativi e marcati come tali.

## Dove si trova questo progetto

Questa cartella vive temporaneamente dentro il repository `tansaavatalia-commits/freelm`
(sul branch `claude/eloquent-newton-uke0z7`), perché è l'unico repository a cui la sessione
di sviluppo ha accesso. `freelm` è un progetto separato (gateway LLM gratuito) e **non è stato
modificato**. Proposta: spostare questa cartella in un repository dedicato e privato
`genesis-drop-engine` (vedi `DECISIONS.md`, D-001 — richiede approvazione dell'operatore).

`freelm` resta utile: è il candidato naturale come gateway LLM gratuito del modulo
Listing Studio (vedi `ARCHITECTURE.md` §7).

## Mappa della documentazione

| File | Contenuto |
|------|-----------|
| `MASTER_SPECIFICATION.md` | Specifica completa: obiettivi, moduli, flussi, criteri di accettazione |
| `BUSINESS_RULES.md` | Regole non negoziabili, formule di profitto, politica Zero-Advance, scoring |
| `ARCHITECTURE.md` | Architettura, scelte tecnologiche, moduli, API interne, connettori |
| `DATABASE.md` | Proposta di schema del database (PostgreSQL) |
| `SUPPLIERS.md` | Ricerca sui fornitori e stato di integrabilità |
| `MARKETPLACES.md` | Ricerca sui canali di vendita e raccomandazione iniziale |
| `SECURITY.md` | Sicurezza, credenziali, permessi, audit, kill switch, backup |
| `TESTING.md` | Strategia e standard di test |
| `COST_CONTROL.md` | Analisi costi attuali e futuri |
| `RISKS.md` | Registro dei rischi |
| `DECISIONS.md` | Registro delle decisioni (tecniche e da approvare) |
| `ROADMAP.md` | Piano di implementazione per fasi e milestone |
| `PROJECT_STATUS.md` | Stato reale del progetto |
| `NEXT_TASK.md` | Prossimo compito esatto |
| `CHANGELOG.md` | Storico modifiche |

## Lingua

Documentazione in italiano; codice, identificatori e convenzioni tecniche in inglese.
