# DATABASE — Proposta di schema (PostgreSQL 16)

Proposta di Fase 1: verrà tradotta in migrazioni Alembic in Fase 2. Convenzioni:

- Chiavi primarie `uuid` (v7, ordinabili nel tempo); `tenant_id uuid not null` su ogni tabella di business.
- Denaro: `*_cents bigint` + `currency char(3)`; tassi e aliquote `numeric(9,6)`.
- Ogni dato esterno: `source text`, `fetched_at timestamptz`, `verification verification_status`.
- Timestamp sempre `timestamptz` (UTC). Nessun `float` per importi.
- Tabelle finanziarie e di audit **append-only** (trigger che vieta `UPDATE`/`DELETE`).

```sql
create type verification_status as enum ('VERIFIED','ESTIMATED','UNVERIFIED','MISSING');
create type integration_status  as enum ('OFFICIAL_API','API_APPROVAL_REQUIRED','AUTHORIZED_FEED',
                                         'MANUAL','PUBLIC_INFO_ONLY','NOT_INTEGRABLE');
```

## 1. Riferimenti e regole

| Tabella | Campi principali | Note |
|---------|------------------|------|
| `rule_sets` | id, version, params jsonb, approved_by, approved_at, active | Parametri BR-xxx versionati (€1, €3, multipack, riserve…) |
| `countries` | code, name, eu_member, currency | |
| `vat_rates` | country, category, rate, valid_from, valid_to, source | Fonte: TEDB Commissione UE |
| `duty_rules` | regime, origin_scope, value_threshold_cents, amount_cents, counting_basis ('PER_ITEM','PER_TARIFF_LINE'), valid_from/to, source | Dazio forfettario €3 dal 2026-07-01 |
| `fx_rates` | base, quote, rate, as_of, source | Fonte: BCE |
| `compliance_rules` | id, category, country_scope, requirement, severity ('BLOCK','REVIEW'), evidence_required, legal_ref | |

## 2. Fornitori e prodotti

| Tabella | Campi principali |
|---------|------------------|
| `suppliers` | id, name, type, country, warehouse_countries[], integration_status, connector_code, payment_terms jsonb (+ verification), returns_policy, active |
| `supplier_performance` | supplier_id, period, orders, on_time_rate, defect_rate, stockout_rate, tracking_rate, source |
| `canonical_products` | id, title_norm, brand, category_code, hs_code, gtin, attributes jsonb, research_only bool, state, rejected_reason_code, rejected_reason_text |
| `canonical_variants` | id, product_id, attributes jsonb, gtin, weight_g, dims_mm |
| `supplier_offers` | id, supplier_id, variant_id, supplier_sku, unit_price_cents, currency, moq, stock_qty, fetched_at, source, verification |
| `shipping_quotes` | id, offer_id, dest_country, qty, cost_cents, currency, min_days, max_days, carrier, tracked bool, fetched_at, verification |
| `product_matches` | id, variant_a, variant_b, method ('GTIN','ATTR','FUZZY','MANUAL'), confidence numeric, confirmed_by |
| `product_state_transitions` | id, product_id, from_state, to_state, actor, gates jsonb, reason, at |
| `raw_payloads` | id, connector, kind, ref, payload jsonb, received_at, expires_at |

## 3. Mercato e analisi

| Tabella | Campi principali |
|---------|------------------|
| `market_signals` | id, subject (niche/product), country, metric, window_days (30/90/365), value numeric, source, fetched_at, verification |
| `destination_assessments` | id, product_id, country, channel, demand_idx, competition_idx, price_range, fees, vat, delivery, import_costs, expected_profit_cents, computed_at |
| `profit_snapshots` | id, product_id, variant_id, supplier_id, country, channel, pack_size, price_cents, scenario ('OPT','CENTRAL','PRUDENT'), lines jsonb, profit_cents, profit_per_unit_cents, status ('COMPLETE','INCOMPLETE'), rule_set_version, formula_version, inputs_hash, created_at |
| `compliance_reports` | id, product_id, country, results jsonb, overall ('PASSED','FAILED','UNRESOLVED'), missing jsonb, created_at |
| `opportunity_scores` | id, product_id, total, components jsonb, rule_set_version, created_at |

## 4. Marketplace e listing

| Tabella | Campi principali |
|---------|------------------|
| `marketplaces` | code, name, countries[], api_available, eligibility_notes, status ('CANDIDATE','APPROVED','ACTIVE','DISABLED') — `code <> 'ebay'` vincolo CHECK |
| `marketplace_accounts` | id, marketplace_code, country, credentials_ref (riferimento al segreto, mai il segreto), status |
| `fee_schedules` | id, marketplace_code, category, pct, fixed_cents, base ('GROSS','NET'), valid_from, source, verification |
| `listings` | id, product_id, account_id, external_ref, pack_size, price_cents, state, approved_by, unique(account_id, product_id, pack_size) |
| `listing_contents` | id, listing_id, language, title, description, attributes jsonb, keywords[], generated_by, approved_by |

## 5. Ordini e fulfillment

| Tabella | Campi principali |
|---------|------------------|
| `orders` | id, account_id, external_ref, state, buyer_country, totals jsonb, unique(account_id, external_ref) |
| `order_lines` | id, order_id, listing_id, variant_id, qty, unit_price_cents |
| `order_events` | id, order_id, from_state, to_state, actor, payload jsonb, at — append-only |
| `supplier_orders` | id, order_id, supplier_id, external_ref, amount_cents, due_at, paid_at, state, idem_key unique |
| `funding_decisions` | id, order_id, outcome, liquidity_before jsonb, checks jsonb, alternative_supplier_id, decided_at, rule_set_version |
| `shipments` | id, supplier_order_id, carrier, tracking_no, status, events jsonb |
| `returns` | id, order_id, reason, state, refund_cents |

## 6. Finanza

| Tabella | Campi principali |
|---------|------------------|
| `ledger_accounts` | id, code, type ('ASSET','LIABILITY','EXPENSE','REVENUE','RESERVE'), currency |
| `ledger_transactions` | id, kind, ref_type, ref_id, idem_key unique, at |
| `ledger_entries` | id, transaction_id, account_id, amount_cents (±), currency — vincolo: somma per transazione = 0 (trigger deferred) |
| `payment_events` | id, order_id, stage ('AUTHORIZED','CAPTURED','MARKETPLACE_HELD','PAYOUT_SCHEDULED','PAYOUT_IN_TRANSIT','AVAILABLE'), amount_cents, expected_at, confirmed_at, source |
| `payouts` | id, marketplace_code, external_ref, amount_cents, scheduled_at, arrived_at, fees_cents |
| `reserve_policies` | id, kind, method, params jsonb, rule_set_version |
| `liquidity_snapshots` | id, available_cents, reserves jsonb, committed_cents, usable_cents, projection jsonb, at |

## 7. Piattaforma e governance

| Tabella | Campi principali |
|---------|------------------|
| `users` / `roles` / `user_roles` | ruoli: `owner`, `operator`, `viewer`, `system` |
| `approvals` | id, type, subject_type, subject_id, requested_by, payload_hash, decided_by, decision, decided_at, expires_at |
| `outbox_actions` | id, connector, action, payload jsonb, idem_key unique, requires_approval, approval_id, status, attempts, last_error, next_attempt_at |
| `idempotency_keys` | key, scope, response jsonb, created_at |
| `automation_settings` | level (0–4), limits jsonb, kill_switch bool, changed_by, changed_at |
| `audit_log` | id, at, actor, action, subject, before jsonb, after jsonb, prev_hash, hash — catena di hash, append-only |
| `integration_health` | connector, last_ok_at, last_error_at, error_rate, circuit_state |
| `cost_ledger` | id, service, period, amount_cents, approved_by — costi operativi reali (vedi `COST_CONTROL.md`) |

## 8. Vincoli critici a livello database

- `UNIQUE (account_id, external_ref)` su `orders` → nessun ordine importato due volte.
- `UNIQUE (account_id, product_id, pack_size)` su `listings` → nessun listing duplicato.
- `UNIQUE idem_key` su `supplier_orders`, `outbox_actions`, `ledger_transactions` → nessun doppio pagamento.
- Trigger su `ledger_entries`: somma zero per transazione; append-only.
- `CHECK (code <> 'ebay')` su `marketplaces`.
- Indici: `pg_trgm` su `canonical_products.title_norm`; `(state, tenant_id)` sulle tabelle con macchina a stati.
