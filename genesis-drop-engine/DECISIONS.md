# DECISIONS — Registro delle decisioni

Formato: ID · data · stato (`PRESA` = decisione tecnica presa dall'architetto, `DA APPROVARE` =
richiede l'operatore) · contesto · decisione · conseguenze.

## Decisioni tecniche (prese, soggette a revisione con l'approvazione della Fase 1)

| ID | Data | Decisione | Motivo |
|----|------|-----------|--------|
| T-001 | 2026-11-20 | Monolite modulare con architettura esagonale | Semplicità operativa oggi, estraibilità domani; no microservizi prematuri |
| T-002 | 2026-11-20 | Python 3.12 + FastAPI + Pydantic v2 | Ecosistema dati/integrazioni, validazione rigorosa, riuso di `freelm` |
| T-003 | 2026-11-20 | PostgreSQL 16 come unico datastore | ACID per il ledger, vincoli, JSONB, pg_trgm; niente Redis/Elasticsearch iniziali |
| T-004 | 2026-11-20 | SQLAlchemy 2.0 + Alembic | Controllo di transazioni e lock |
| T-005 | 2026-11-20 | Procrastinate (coda su PostgreSQL) per job e outbox | Transazionalità con i dati, zero infrastruttura extra |
| T-006 | 2026-11-20 | Dashboard server-side Jinja2 + HTMX | Un operatore, manutenzione minima; API-first per una SPA futura |
| T-007 | 2026-11-20 | Denaro in centesimi interi + valuta; mai float | Esattezza finanziaria |
| T-008 | 2026-11-20 | Ledger interno a partita doppia, append-only | Liquidità reale verificabile |
| T-009 | 2026-11-20 | Outbox con idempotenza, approvazioni, livelli di automazione e kill switch per ogni azione esterna | Nessuna azione esterna non autorizzata o duplicata |
| T-010 | 2026-11-20 | Provenienza e stato di verifica su ogni dato esterno | Nessuna stima presentata come fatto |
| T-011 | 2026-11-20 | Gate di profitto sullo scenario prudenziale | Evitare ottimismo nascosto |
| T-012 | 2026-11-20 | `tenant_id` su tutte le tabelle di business | Multi-negozio/multi-operatore senza migrazioni distruttive |
| T-013 | 2026-11-20 | `freelm` come gateway LLM del Listing Studio, dietro un port sostituibile | Costo €0 |
| T-014 | 2026-11-20 | Primo connettore fornitore: CSV/manuale, poi CJdropshipping API 2.0 | Costo zero, API ufficiale con account gratuito |
| T-015 | 2026-11-20 | Documentazione in una sottocartella `genesis-drop-engine/` del repo `freelm`, senza modificare `freelm` | Unico repository accessibile; nessuna distruzione di lavoro esistente |

## Decisioni che richiedono l'operatore

| ID | Questione | Raccomandazione dell'architetto |
|----|-----------|---------------------------------|
| **D-001** | Spostare il progetto in un repository GitHub **privato** dedicato `genesis-drop-engine`? (la sessione attuale non può creare repository) | Sì: l'operatore crea il repo vuoto privato e lo aggiunge alla sessione; la cronologia di questa cartella viene trasferita |
| **D-002** | Paese di registrazione dell'impresa e forma giuridica | Decisione legale/fiscale con un commercialista; il sistema resta parametrico. Un soggetto UE con OSS/IOSS semplifica IVA e idoneità ai marketplace |
| **D-003** | Approvazione dello stack tecnologico (T-001…T-013) | Approvare |
| **D-004** | Primo canale di vendita | Allegro (sandbox gratuita), poi Kaufland — dopo verifica ufficiale |
| **D-005** | Paesi di destinazione iniziali | 2–3 paesi a domanda alta e IVA moderata (da selezionare con dati in Fase 2) |
| **D-006** | Livello di automazione iniziale | LEVEL 1 (ricerca e raccomandazioni) |
| **D-007** | Parametri riserve (rimborsi 10%, chargeback 1%, IVA 100%) e margine di cambio 3% | Approvare come default prudenziali |
| **D-008** | Destinazione dei backup esterni | Da scegliere (disco esterno o cloud già posseduto) |
| **D-009** | Pacchetti multipack da valutare (default 1, 2, 3, 5, 10) | Approvare |
| **D-010** | **Fattibilità economica**: con dazio UE €3 e costi realistici, la singola unità a €6–7 con €3 netti è quasi irrealizzabile da Cina (vedi `BUSINESS_RULES.md` §5). Confermare che il sistema privilegi multipack e fornitori con magazzino UE, e che un prezzo per unità superiore a €6–7 (es. ~€8,50 nei multipack) sia accettabile | Confermare: le regole €1 e €3 restano invariate, cambia la strategia di configurazione |
| **D-011** | **Capitale zero vs fornitori prepagati**: i primi ordini saranno bloccati finché non esiste un saldo disponibile. Accettare questo comportamento, oppure autorizzare esplicitamente un fondo operativo iniziale con importo massimo? | Il sistema funziona in entrambi i casi; un eventuale fondo va registrato come approvazione con tetto e tracciato nel ledger |
| **D-012** | Approvazione di eventuali servizi a pagamento futuri (BigBuy, canoni marketplace, VPS) | Nessuno necessario per la Fase 2 |
