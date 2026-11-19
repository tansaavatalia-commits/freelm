# GAME PORTAL — Architettura (proposta FASE 0, da congelare in FASE 2)

## Principi
1. **Costo zero ai volumi iniziali**, con soglie di costo note in anticipo.
2. **Indipendenza dal fornitore:** standard aperti (HTTP, SQLite, ES modules), nessuna API proprietaria nel dominio applicativo.
3. **Statico prima di tutto:** catalogo e pagine prerenderizzati ⇒ velocità, SEO, consumo minimo dei limiti Workers.
4. **Isolamento forte** tra portale, giochi, annunci e admin.
5. **Privacy by default:** nessun cookie non tecnico, nessun tracker di terzi.

## Scelte e alternative valutate

| Area | Scelta | Alternative gratuite valutate | Motivo |
|---|---|---|---|
| Linguaggio | TypeScript strict | — | Tipi condivisi front/back |
| UI | React + Vite | Preact (più leggero), Astro | React richiesto; si valuta `preact/compat` se il budget JS è sforato |
| SSR/SEO | Prerendering statico in build (Vite SSG) | Astro, Next.js | Niente server di rendering, pagine HTML pronte |
| API | Hono su Cloudflare Workers | Netlify/Vercel Functions, Deno Deploy | Hono è portabile (Node/Bun/Deno), Workers ha piano gratuito ampio |
| DB | Cloudflare D1 (SQLite) | Turso, Supabase Free, Neon Free | SQLite standard ⇒ export ed esecuzione locale facili |
| File/asset giochi | Asset statici dentro Pages | R2 (piano gratuito con soglie) | Zero costi di uscita dati, versionamento via Git |
| Repo/CI | GitHub Free + Actions | GitLab Free, Codeberg | Già disponibile |
| Analytics | Eventi propri aggregati in D1, senza cookie | Cloudflare Web Analytics, Plausible self-hosted | Dati di proprietà, nessun consenso per misure aggregate anonime **(da confermare legalmente)** |
| Errori | Endpoint `/api/v1/telemetry/error` + log Worker | Sentry Free | Nessun terzo che riceve dati utente |

Esclusi: Kubernetes, microservizi, ORM pesanti, CMS headless SaaS, CDN pubblicitarie.

## Struttura del monorepo (da creare in FASE 3)

```
game-portal/
├── frontend/        # portale pubblico (React + Vite, prerender)
├── admin/           # SPA amministrativa separata, deploy su origin distinto
├── backend/         # Worker Hono: API pubblica + API admin + ad serving
│   └── migrations/  # SQL versionato per D1
├── shared/          # tipi, schemi Zod, i18n, costanti
├── games/
│   ├── sdk/         # piccolo SDK postMessage per i giochi
│   └── <slug>/      # un gioco = un bundle statico + manifest.json
├── scripts/         # modello finanziario, backup, controlli licenze, link checker
├── tests/           # E2E Playwright, test di sicurezza
└── docs/
```

## Domini e origin (separazione di sicurezza)

| Origin | Contenuto | Cookie |
|---|---|---|
| `www.<dominio>` | portale pubblico + `/api/v1/*` | solo cookie di sessione tecnico (`HttpOnly; Secure; SameSite=Lax`) |
| `play.<dominio>` (o progetto Pages separato) | soli bundle dei giochi | **nessuno** |
| `admin.<dominio>` | SPA admin + `/admin-api/*` | sessione admin separata, MFA |

Prima dell'acquisto del dominio si usano sottodomini `*.pages.dev` distinti, gratuiti.

## Flusso di una pagina gioco
1. HTML prerenderizzato da Pages (cache CDN).
2. Il player crea `<iframe src="https://play.../<slug>/<version>/" sandbox="allow-scripts allow-pointer-lock" allow="fullscreen; gamepad" referrerpolicy="no-referrer" loading="lazy">`.
   Niente `allow-same-origin` per i giochi di terzi; per i giochi interni che usano `localStorage` per i salvataggi si valuta la combinazione con l'origin separato (l'origin diverso protegge comunque i cookie del portale).
3. Il gioco comunica solo tramite `postMessage` con schema validato (`ready`, `score`, `progress`, `error`); il portale ignora tutto il resto.
4. Il portale invia un evento aggregato `game_session` (slug, versione, durata arrotondata, paese a livello di header CF, nessun ID persistente).

## Modello dati (bozza)
- `games(id, slug, title, status[draft|review|published|suspended], current_version_id, category_id, …)`
- `game_versions(id, game_id, semver, bundle_path, sha256, size_bytes, created_at)`
- `licenses(id, game_id, …)` — campi completi in `LICENSE_MANAGEMENT.md`
- `categories`, `tags`, `game_tags`
- `users(id, email_hash, created_at, premium_until)`, `sessions`, `favorites`, `history`
- `advertisers`, `contracts`, `campaigns`, `creatives`, `placements`, `ad_daily_stats(campaign_id, placement_id, day, impressions, clicks)`
- `sponsorships`, `invoices_manual`
- `events_daily(day, game_id, sessions, total_seconds, errors)` — **solo aggregati**
- `audit_log(id, actor, action, entity, before_json, after_json, at)`

Regola d'integrità: un trigger/controllo applicativo impedisce `status='published'` se la licenza non è `approved` e non è scaduta.

## Ad serving diretto
- Endpoint `GET /api/v1/ads/slot/:placement` → creatività scelta per calendario, priorità e cap di frequenza (contatore per sessione in memoria del client, nessun cookie).
- Impression conteggiata quando la creatività è visibile ≥ 50 % per ≥ 1 s (IntersectionObserver), inviata in batch.
- Clic tramite `GET /r/:creativeId` con redirect 302 e conteggio deduplicato.
- Le creatività sono immagini statiche servite dal nostro origin: **nessuno script o pixel di terzi**.
- Se nessuna campagna è attiva lo slot collassa (`display: none`), senza spazi vuoti.

## Soglie di costo note
- Workers Free: 100.000 richieste/giorno **[TERZI, verificare in FASE 2]** ⇒ oltre si passa a Workers Paid (~5 $/mese).
- D1 Free: limiti giornalieri di letture/scritture applicati dal 1/9/2026 **[UFF]**; storage ~5 GB **[TERZI]**.
- Le pagine statiche non consumano richieste Worker: la maggior parte del traffico resta gratuita.

## Portabilità (piano di uscita)
Hono → Node/Bun su VPS; D1 → file SQLite (`wrangler d1 export`); Pages → qualsiasi hosting statico. Tempo di migrazione stimato: 1–3 giorni **[IPOTESI]**.
