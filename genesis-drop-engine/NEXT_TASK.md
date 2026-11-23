# NEXT_TASK — Prossimo compito

## Completare M2.0 Fondamenta

1. Modelli SQLAlchemy + prima migrazione Alembic: `rule_sets`, `audit_log` (append-only, catena di hash),
   `profit_snapshots`.
2. `platform/audit.py` (catena di hash + verifica) con test di integrazione su PostgreSQL locale.
3. Persistenza degli snapshot del Profit Engine.
4. Portare la copertura di `modules/profit` e `core` al 95% (oggi 87%); test per `Clock`.

## Poi

M2.2 Compliance Engine → M2.3 Ledger + Cashflow Guardian → M2.4 Zero-Advance (con fondo €100).

## Opzionale, se l'operatore lo approva

Collegare il connettore CJ Dropshipping (AnythingMCP) in sola lettura per validare il Profit Engine con
prezzi e spedizioni reali (vedi `DECISIONS.md`, D-013).
