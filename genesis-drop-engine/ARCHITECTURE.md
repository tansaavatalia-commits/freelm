# ARCHITECTURE — Architettura tecnica

## 1. Principi guida

1. **Monolite modulare, non microservizi.** Un'unica applicazione con moduli a confini netti
   (package separati, interfacce esplicite, nessun accesso diretto alle tabelle di un altro modulo).
   Un modulo può essere estratto in servizio separato in futuro senza riscrivere il dominio.
2. **Architettura esagonale (ports & adapters).** Il dominio (regole, calcoli, stati) è puro e non
   conosce HTTP, database o fornitori. Le integrazioni esterne sono *adapter* dietro *port* (interfacce).
3. **Le regole di business stanno nel dominio**, non nell'interfaccia: nessun percorso (API, job,
   script, automazione) può aggirare i gate.
4. **Provenienza su ogni dato**: fonte, timestamp, stato di verifica. Dati mancanti = blocco, mai ottimismo.
5. **Denaro esatto**: importi come interi in centesimi (`int`) + codice valuta; `Decimal` per tassi.
   Mai `float` per denaro.
6. **Azioni esterne via outbox**: ogni scrittura verso l'esterno (ordine fornitore, listing, prezzo)
   passa da una coda persistente con chiave di idempotenza, approvazione e controllo del kill switch.
7. **Costo operativo minimo**: tutto gira in locale con Docker Compose; lo stesso stack si sposta su
   un VPS o cloud senza modifiche al codice.

## 2. Scelte tecnologiche (con alternative valutate)

| Area | Scelta | Alternative valutate | Motivazione |
|------|--------|----------------------|-------------|
| Linguaggio | **Python 3.12** | TypeScript/Node, Go | Ecosistema maturo per dati, calcolo numerico e integrazioni; `freelm` già disponibile in Python; tipizzazione statica con mypy. Go è più performante ma meno produttivo per analisi dati; Node ottimo per I/O ma `Decimal` e data tooling più deboli |
| Framework API | **FastAPI** + Pydantic v2 | Django + DRF, Litestar | Validazione rigorosa degli input, OpenAPI automatico, async nativo. Django più "batterie incluse" ma ORM e admin meno adatti all'esagonale; Litestar valido ma ecosistema più piccolo |
| Database | **PostgreSQL 16** | SQLite, MySQL, MongoDB | Transazioni ACID per il ledger, vincoli `CHECK`, `JSONB` per snapshot, `pg_trgm` per il matching testuale, partizionamento. SQLite solo per test rapidi di unità, mai per dati finanziari multi-processo |
| ORM / migrazioni | **SQLAlchemy 2.0** + **Alembic** | Django ORM, SQLModel, Prisma | Standard de facto, controllo fine delle transazioni e dei lock (`SELECT … FOR UPDATE` per la liquidità) |
| Job in background | **Procrastinate** (coda su PostgreSQL) | Celery+Redis, RQ, Dramatiq, APScheduler | Nessun Redis da gestire: la coda vive nello stesso DB, transazionale con i dati (outbox affidabile). Celery è più potente ma aggiunge infrastruttura non necessaria ora |
| Scheduling | Procrastinate periodic tasks | cron di sistema | Un solo meccanismo, osservabile dal DB |
| Dashboard | **Jinja2 + HTMX + Alpine.js**, grafici **Chart.js** | React/Next.js SPA, Streamlit | Un solo operatore: rendering lato server, zero build JS, costo di manutenzione minimo. L'API resta il contratto, quindi una SPA può essere aggiunta dopo. Streamlit scartato: debole su autenticazione e permessi |
| HTTP client | **httpx** + **tenacity** (retry) | requests, aiohttp | Sync+async, timeout espliciti, già usato in `freelm` |
| LLM (Listing Studio) | **freelm** (gateway gratuito multi-provider, nello stesso repo) | API a pagamento dirette | Costo €0, failover automatico; dietro un port `TextGenerator`, sostituibile |
| Matching prodotti | `rapidfuzz` + `pg_trgm`; embedding opzionali in seguito (`pgvector`) | Elasticsearch/OpenSearch | Evita un motore di ricerca separato finché i volumi non lo richiedono |
| Logging | **structlog** (JSON) | logging standard | Log strutturati, correlazione per `request_id`/`order_id` |
| Metriche | endpoint Prometheus opzionale; tabella `integration_health` | Datadog, Grafana Cloud | Gratuito; Grafana locale solo se necessario |
| Segreti | `.env` (fuori da Git) in sviluppo; **SOPS + age** per file cifrati versionabili; Docker secrets in produzione | HashiCorp Vault, cloud secret manager | Vault è sovradimensionato per un operatore; migrazione semplice in seguito |
| Backup | `pg_dump` cifrato + **restic** verso storage esterno | Servizi gestiti | Gratuito, cifrato, verificabile con restore di prova |
| Container | **Docker Compose** | Kubernetes | K8s inutile su questa scala; Compose gira identico su laptop e VPS |
| Qualità | ruff, mypy (strict sul dominio), pytest, hypothesis, testcontainers, pre-commit, gitleaks | — | Vedi `TESTING.md` |

## 3. Vista d'insieme

```
                ┌───────────────────────────── Interfacce ─────────────────────────────┐
                │  Control Tower (HTMX)     REST API /api/v1     CLI amministrativa      │
                └──────────────┬───────────────────┬────────────────────┬────────────────┘
                               │ comandi/query      │                    │
┌──────────────────────────────┴───────────────────┴────────────────────┴─────────────────┐
│                               APPLICATION LAYER (use case)                               │
│  approve_product · evaluate_opportunity · authorize_supplier_order · publish_listing ... │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│                                   DOMINIO (puro)                                         │
│ market_radar  product_radar  market_intel  supplier_intel  profit  compliance            │
│ cashflow  zero_advance  listing_studio  fulfillment  marketplace_hub  scoring            │
│ ── policy (gate BR-xxx, rule_set versionato) ── state machines ── money/units ──         │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│                                PLATFORM / INFRASTRUTTURA                                 │
│ db (SQLAlchemy) · outbox+jobs (Procrastinate) · audit (hash chain) · approvals            │
│ automation_level + kill switch · secrets · idempotency · rate limiter · health           │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│                                     CONNETTORI (adapter)                                 │
│ suppliers/: cj, bigbuy, aliexpress, syncee, csv_feed, manual                             │
│ marketplaces/: allegro, kaufland, amazon_sp, woocommerce, cdiscount_octopia               │
│ data/: fx_rates (BCE), vat_rates (TEDB/VIES), trend sources autorizzate, carriers         │
│ ai/: freelm                                                                              │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

## 4. Struttura del codice (proposta)

```
genesis-drop-engine/
├── pyproject.toml
├── docker-compose.yml
├── alembic/                     # migrazioni
├── src/genesis/
│   ├── core/                    # Money, Currency, Quantity, Provenance, Clock, IDs, errori
│   ├── policy/                  # rule_set versionato, gate BR-xxx, GateResult
│   ├── modules/
│   │   ├── market_radar/        # domain.py, service.py, ports.py, repository.py, api.py
│   │   ├── product_radar/
│   │   ├── market_intel/
│   │   ├── supplier_intel/
│   │   ├── profit/
│   │   ├── compliance/
│   │   ├── cashflow/
│   │   ├── zero_advance/
│   │   ├── listing_studio/
│   │   ├── fulfillment/
│   │   ├── marketplace_hub/
│   │   ├── scoring/
│   │   └── control_tower/       # solo query/aggregazioni + template
│   ├── platform/                # db, outbox, jobs, audit, approvals, automation, secrets, health
│   ├── connectors/
│   │   ├── base.py              # SupplierConnector, MarketplaceConnector, DataSource (Protocol)
│   │   ├── suppliers/  marketplaces/  data/  ai/
│   │   └── fakes/               # implementazioni finte deterministiche per test e simulazioni
│   └── web/                     # app FastAPI, router, template, statici
└── tests/
    ├── unit/  property/  integration/  contract/  e2e/  fixtures/
```

Ogni modulo espone solo `service.py` (use case) e `ports.py` (interfacce). Un test architetturale
(`import-linter`) impedisce import incrociati non consentiti (es. `profit` non può importare `connectors`).

## 5. Specifiche dei moduli (sintesi; dettaglio funzionale in `MASTER_SPECIFICATION.md`)

| Modulo | Responsabilità | Input | Output | Dipende da |
|--------|----------------|-------|--------|------------|
| M1 Market Radar | Nicchie, trend, stagionalità, saturazione | DataSource autorizzati | `MarketSignal` con finestra e provenienza | connettori data |
| M2 Product Radar | Scoperta, normalizzazione, deduplica, matching varianti | SupplierConnector | `CanonicalProduct`, `SupplierOffer`, `ProductMatch` | supplier_intel |
| M3 Global Market Intelligence | Confronto per paese di destinazione | prodotti, fee, IVA, dazi | `DestinationAssessment` | profit, compliance |
| M4 Supplier Intelligence | Confronto e sostituzione fornitori | offerte, storico | `SupplierRanking` | profit, zero_advance |
| M5 Profit Engine | Calcolo trasparente a 3 scenari, multipack | `ProfitInput` | `ProfitSnapshot` immutabile | puro |
| M6 Compliance Engine | Regole per categoria/paese, blocco | prodotto, destinazione | `ComplianceReport` | puro + tabelle regole |
| M7 Cashflow Guardian | Liquidità attuale e proiettata | ledger, payout | `LiquidityView`, avvisi | ledger |
| M8 Zero-Advance Engine | Autorizzazione finanziaria ordini fornitore | ordine, liquidità, termini | `FundingDecision` | cashflow, profit, supplier_intel |
| M9 Listing Studio | Titoli, descrizioni, traduzioni, prezzi proposti | prodotto approvato | `ListingDraft` (richiede approvazione) | ai/freelm, compliance |
| M10 Fulfillment Engine | Ciclo di vita ordine con audit | ordini marketplace | `Order` state machine, outbox | zero_advance, connettori |
| M11 Marketplace Command Center | Sync listing/prezzi/stock/ordini/tracking, salute canali | listing approvati | stato canali | connettori marketplace |
| M12 Control Tower | Dashboard | viste read-only | HTML/JSON | tutti (solo lettura) |
| Scoring | Opportunity Score 0–100 | profit, segnali, fornitore | `OpportunityScore` con dettaglio | puro |

### 5.1 Macchina a stati del prodotto

```
DISCOVERED → ENRICHED → SUPPLIER_VERIFIED → MARKET_ANALYZED → PROFIT_VERIFIED
  → COMPLIANCE_REVIEW → READY_FOR_APPROVAL → APPROVED → LISTED → MONITORING
           (qualsiasi stato) → REJECTED  [motivo obbligatorio, codice BR + testo]
           MONITORING → SUSPENDED → (MONITORING | REJECTED)
```

Ogni transizione è registrata in `product_state_transitions` (chi, quando, perché, gate valutati).
Le transizioni sono definite in una tabella di dominio; quelle non elencate sono impossibili.
`PROFIT_VERIFIED` richiede BR-001 e BR-010; `READY_FOR_APPROVAL` richiede compliance `PASSED`;
`APPROVED` richiede un'approvazione umana registrata.

### 5.2 Macchina a stati dell'ordine

```
RECEIVED → VALIDATED → SUPPLIER_SELECTED → PROFIT_RECHECKED → FUNDING_CHECK
  → (FUNDING_BLOCKED | AWAITING_APPROVAL) → APPROVED → SUPPLIER_ORDER_QUEUED
  → SUPPLIER_ORDERED → SUPPLIER_PAID → SHIPPED → TRACKING_SYNCED → DELIVERED → CLOSED
Rami: CANCELLED, FULFILLMENT_FAILED, RETURN_REQUESTED → RETURNED → REFUNDED, CHARGEBACK
```

## 6. API interne

REST JSON versionata `/api/v1`, autenticata (sessione per la dashboard, token per CLI/script).
Esempi di contratto:

| Metodo | Percorso | Scopo |
|--------|----------|-------|
| GET | `/products?state=&score_min=` | Lista prodotti con stato e punteggio |
| GET | `/products/{id}` | Dettaglio con provenienza dei dati |
| POST | `/products/{id}/transitions` | Richiede una transizione (il server valuta i gate) |
| POST | `/profit/calculate` | Calcolo profitto (non persistito se `dry_run=true`) |
| GET | `/profit/snapshots/{id}` | Snapshot immutabile con tutte le voci |
| GET | `/compliance/reports/{product_id}?country=` | Esito controlli |
| GET | `/cashflow/liquidity` | Liquidità attuale, riserve, proiezione |
| POST | `/orders/{id}/funding-decision` | Valuta Zero-Advance (idempotente) |
| POST | `/approvals/{id}/decide` | Approva/rifiuta un'azione in attesa |
| GET/PUT | `/automation/level` | Livello di automazione (PUT solo ruolo owner + conferma) |
| POST | `/automation/kill-switch` | Arresto di emergenza |
| GET | `/integrations/health` | Stato dei connettori |

Gli errori seguono RFC 9457 (`application/problem+json`) con codice regola (`BR-010`) quando un gate blocca.

## 7. Interfacce dei connettori esterni

```python
class SupplierConnector(Protocol):
    code: str                                # "cj", "bigbuy", ...
    integration_status: IntegrationStatus     # OFFICIAL_API | API_APPROVAL_REQUIRED | AUTHORIZED_FEED
                                              # | MANUAL | PUBLIC_INFO_ONLY | NOT_INTEGRABLE
    def search_products(self, query: ProductQuery) -> Page[RawSupplierProduct]: ...
    def get_product(self, ref: str) -> RawSupplierProduct: ...
    def get_stock(self, variant_refs: list[str]) -> list[StockLevel]: ...
    def quote_shipping(self, variant_ref: str, qty: int, dest: CountryCode) -> list[ShippingQuote]: ...
    def payment_terms(self) -> PaymentTerms: ...                     # sempre con provenienza
    def place_order(self, order: SupplierOrderRequest, idem_key: str) -> SupplierOrderResult: ...
    def get_tracking(self, supplier_order_ref: str) -> TrackingInfo: ...

class MarketplaceConnector(Protocol):
    code: str
    def fetch_orders(self, since: datetime) -> Page[RawMarketplaceOrder]: ...
    def publish_listing(self, listing: ListingPayload, idem_key: str) -> ListingResult: ...
    def update_price_stock(self, updates: list[PriceStockUpdate], idem_key: str) -> BatchResult: ...
    def push_tracking(self, order_ref: str, tracking: TrackingInfo, idem_key: str) -> None: ...
    def fetch_payouts(self, since: datetime) -> list[PayoutEvent]: ...
    def fetch_fee_schedule(self) -> FeeSchedule | None: ...
    def suspend_listing(self, listing_ref: str, idem_key: str) -> None: ...
```

Regole per tutti i connettori:
- Metodi di **scrittura** invocabili solo dal dispatcher dell'outbox (che verifica approvazione,
  livello di automazione e kill switch). Il dominio non chiama mai direttamente un metodo di scrittura.
- Rate limiter per connettore (token bucket), retry con backoff esponenziale e jitter solo su errori
  transitori, circuit breaker: il guasto di un canale non blocca gli altri.
- Ogni risposta grezza viene archiviata (`raw_payloads`, con scadenza) per audit e ri-elaborazione.
- Ogni connettore ha un **fake** deterministico e una suite di **contract test** comune.
- eBay non ha connettore e il registro lo rifiuta esplicitamente (BR-050).

## 8. Outbox, approvazioni e livelli di automazione

```
use case → scrive OutboxAction(status=PENDING_APPROVAL | READY, idem_key) nella STESSA transazione
dispatcher → if kill_switch: stop
           → if action.requires_approval(level) and not approved: wait
           → verifica limiti (importo per ordine, importo giornaliero, n. azioni/ora)
           → chiama il connettore con idem_key → registra esito → audit
```

| Livello | Consentito senza approvazione umana |
|---------|-------------------------------------|
| 0 | Solo ricerca (nessuna scrittura esterna, nemmeno bozze) |
| 1 | Ricerca + raccomandazioni (**default iniziale**) |
| 2 | Niente: listing e ordini preparati automaticamente, ciascuno approvato dall'operatore |
| 3 | Aggiornamenti prezzo/stock e ordini fornitore entro limiti rigidi (es. ≤ €X per ordine, ≤ €Y al giorno) |
| 4 | Automazione avanzata con monitoraggio, limiti e kill switch; mai senza approvazione esplicita |

## 9. Ledger finanziario

Contabilità a **partita doppia** interna (non sostituisce la contabilità fiscale): ogni movimento è
una coppia di scritture bilanciate su conti come `customer_receivable`, `marketplace_held`,
`payout_in_transit`, `bank_available`, `supplier_payable`, `reserve_refunds`, `reserve_chargebacks`,
`vat_payable`, `fees_expense`. Le scritture sono **append-only** (correzioni = storni).
La liquidità utilizzabile (vedi `BUSINESS_RULES.md` §7.2) è calcolata dal ledger, con lock di riga
sul conto `bank_available` durante l'autorizzazione di un ordine per evitare doppie spese concorrenti.

## 10. Portabilità e scalabilità

- Stato solo in PostgreSQL (+ file di backup): l'app è stateless, si può replicare.
- Configurazione tramite variabili d'ambiente (12-factor).
- Percorso di crescita: laptop → VPS singolo (Compose) → DB gestito + più worker → estrazione
  di un modulo (es. Product Radar) se il carico lo giustifica.
- Multi-store / multi-operatore: tutte le tabelle di business includono `tenant_id` fin dall'inizio
  (un solo tenant oggi), così l'espansione non richiede migrazioni distruttive.
