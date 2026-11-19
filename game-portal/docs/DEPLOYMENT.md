# Tabluo — Deployment

> **Nessun deploy è stato eseguito.** Tutto gira solo in locale. La pubblicazione richiede
> l'autorizzazione esplicita del titolare (gate G4, FASE 11): account Cloudflare, dominio,
> soggetto fiscale.

## Sviluppo locale (gratuito, senza account)

Requisiti: Node ≥ 22.18, pnpm 10.

```bash
pnpm install
cp backend/.dev.vars.example backend/.dev.vars    # poi metti un ADMIN_TOKEN casuale di 32+ caratteri
(cd backend && npx wrangler d1 migrations apply tabluo --local)
pnpm dev          # portale :5173 · giochi :5174 · API :8787 (D1 locale in backend/.wrangler)
```

| Comando | Cosa fa |
|---|---|
| `pnpm check` | controllo tipi + tutti i test unitari + build di tutti i pacchetti |
| `pnpm e2e` | avvia API, giochi e portale ed esegue il test nel browser (Chromium + Playwright) |
| `pnpm catalog` | rigenera il catalogo; **fallisce** se un gioco non ha una licenza valida |
| `python3 scripts/financial_model.py [--no-network]` | modello economico |

## Topologia di produzione prevista (piani gratuiti)

| Componente | Servizio | Origin | Build |
|---|---|---|---|
| Portale | Cloudflare Pages (progetto `tabluo-web`) | `www.<dominio>` | `frontend/dist` (`_headers`, `_redirects` inclusi) |
| Giochi | Cloudflare Pages (progetto `tabluo-play`) | `play.<dominio>` | `games/dist` (`_headers` incluso) |
| API | Cloudflare Worker `tabluo-api` + D1 `tabluo` | `www.<dominio>/api/*` e `/r/*` (route) | `backend` |

Variabili di build del portale: `VITE_GAMES_ORIGIN=https://play.<dominio>`.

## Checklist del primo deploy (solo dopo l'autorizzazione)
1. Creare l'account Cloudflare (gratuito) **a nome del titolare**.
2. `wrangler d1 create tabluo` e sostituire `database_id` in `backend/wrangler.toml`.
3. `wrangler d1 migrations apply tabluo --remote`.
4. `wrangler secret put ADMIN_TOKEN` (valore casuale ≥ 32 caratteri, conservato in un password manager).
5. Sostituire `tabluo.example` in `frontend/public/_headers` e `games/public/_headers` con il dominio reale.
6. Collegare i due progetti Pages al repository (build automatica su push).
7. Route del Worker per `/api/*` e `/r/*` sul dominio del portale.
8. Prima beta su `*.pages.dev` **non indicizzata** (`X-Robots-Tag: noindex`), poi il dominio.

## Rollback
Pages conserva ogni deploy: rollback dalla dashboard in un clic. Worker: `wrangler rollback`.
Database: export giornaliero (vedi OPERATIONS.md) e migrazioni solo additive.
