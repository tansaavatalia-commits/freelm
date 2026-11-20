# NEXT_TASK — Prossimo compito

## In attesa

Approvazione dell'operatore sulla Fase 1 e risposta alle decisioni in `DECISIONS.md`, in particolare:
D-001 (repository dedicato), D-003 (stack), D-010 (fattibilità economica), D-011 (capitale zero).

## Dopo l'approvazione: M2.0 Fondamenta

1. (Se D-001 approvata) trasferire questa cartella nel repository privato `genesis-drop-engine`.
2. Creare `pyproject.toml`, struttura `src/genesis/` e `tests/` come da `ARCHITECTURE.md` §4.
3. `docker-compose.yml` con PostgreSQL 16; `.env.example` senza segreti.
4. Strumenti: ruff, mypy, pytest, hypothesis, testcontainers, import-linter, pre-commit, gitleaks; CI GitHub Actions.
5. `core/money.py` (centesimi + valuta, arrotondamento esplicito) con test completi.
6. `policy/rule_set.py` con parametri BR-001/010/011 versionati.
7. `platform/audit.py` con catena di hash + prima migrazione Alembic.
8. Aggiornare `PROJECT_STATUS.md`, `TESTING.md` (risultati reali), `CHANGELOG.md`.
