# Tabluo (GAME PORTAL)

Portale indipendente di giochi HTML5 classici. **Solo sviluppo locale: niente è pubblicato.**
Questa cartella verrà spostata nel repository dedicato `game-portal` (vedi `docs/MIGRATION.md`).

```bash
pnpm install
pnpm check   # tipi + 80 test + build
pnpm e2e     # test end-to-end nel browser (API + giochi + portale)
pnpm dev     # sviluppo: portale :5173, giochi :5174, API :8787
```

- Stato: [`PROJECT_STATUS.md`](PROJECT_STATUS.md) · Piano A–J: [`docs/MASTER_PLAN.md`](docs/MASTER_PLAN.md)
- Architettura: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) · Deploy: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) · Operatività: [`docs/OPERATIONS.md`](docs/OPERATIONS.md)
- Modello economico: `python3 scripts/financial_model.py`
- **Andare online:** [`docs/LAUNCH.md`](docs/LAUNCH.md)

| Cartella | Contenuto |
|---|---|
| `shared/` | tipi, validazione manifest, regola licenze, protocollo `postMessage` |
| `backend/` | API Hono per Cloudflare Workers + migrazioni D1 |
| `frontend/` | portale React + Vite |
| `games/` | giochi (Klondike, Mines, Sudoku, Nonogram) + SDK |
| `scripts/` | catalogo, E2E, modello finanziario |
| `tests/` | test dello script di catalogo + E2E |
