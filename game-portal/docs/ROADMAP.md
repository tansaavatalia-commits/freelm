# GAME PORTAL — Roadmap

Regola: **nessuna fase viene saltata**. Ogni fase si chiude solo con i criteri di
completamento soddisfatti e registrati in `PROJECT_STATUS.md`. Tutte le fasi hanno
costo previsto **0 €**, salvo dove indicato. Le "approvazioni" sono decisioni che
spettano all'utente (vedi `DECISIONS.md`).

---

## FASE 0 — Audit dell'ambiente e pianificazione ✅
- **Obiettivo:** conoscere l'ambiente, definire piano, architettura, costi e rischi.
- **Attività:** audit strumenti, ispezione repository, modello economico, documentazione.
- **Dipendenze:** nessuna.
- **File:** `game-portal/docs/*`, `game-portal/PROJECT_STATUS.md`, `game-portal/scripts/financial_model.py`.
- **Strumenti:** Claude Code, Git, Python. **Costi:** 0 €.
- **Test:** esecuzione dello script del modello (output riportato in FINANCIAL_MODEL.md).
- **Completamento:** rapporto A–J consegnato.
- **Rischi:** repository non dedicato (vedi D-001).
- **Approvazioni:** D-001, D-002 e passaggio alla FASE 1.

## FASE 1 — Ricerca mercato e validazione ✅ (G1: GO condizionato)
- **Obiettivo:** validare (o falsificare) la tesi di nicchia e i parametri del modello.
- **Attività:** dossier su CrazyGames, Poki, Coolmath Games, Y8 e 3–5 portali
  indipendenti; classificazione delle fonti; analisi keyword (Google Trends,
  autocomplete, "People also ask"); ricerca di benchmark CPM diretti e sponsorship;
  ricognizione normativa su fonti ufficiali; scelta dei primi 10 giochi interni.
- **Dipendenze:** FASE 0 approvata.
- **File:** `docs/COMPETITOR_RESEARCH.md` (completo), `docs/BUSINESS_MODEL.md`,
  `docs/FINANCIAL_MODEL.md` (parametri aggiornati), `docs/LEGAL_CHECKLIST.md`.
- **Strumenti:** ricerca web, Google Trends (gratuito, senza account).
- **Costi:** 0 €. **Alternative gratuite:** nessuno strumento SEO a pagamento (Ahrefs/Semrush esclusi).
- **Test:** ogni affermazione numerica ha fonte e classificazione.
- **Completamento:** gate **G1**.
- **Rischi:** dati pubblici scarsi su ricavi dei concorrenti (in gran parte privati).
- **Approvazioni:** scelta della nicchia, lingua iniziale, nome provvisorio del brand.

## FASE 2 — Architettura e documentazione
- **Obiettivo:** congelare architettura, schema dati, API, design system.
- **Attività:** ADR in `DECISIONS.md`, schema D1, contratto API (OpenAPI), protocollo
  `postMessage` dei giochi, identità visiva (palette, tipografia, logo testuale), wireframe.
- **Dipendenze:** FASE 1.
- **File:** `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT.md`, `docs/SECURITY.md`, `shared/schema/*`.
- **Costi:** 0 €. **Alternative gratuite:** font open source (OFL), icone MIT/CC0.
- **Test:** revisione incrociata schema ↔ requisiti del brief.
- **Completamento:** ogni requisito del brief mappato a un componente.
- **Rischi:** sovra-ingegnerizzazione ⇒ si mantiene un MVP minimo.
- **Approvazioni:** identità visiva, nome del brand.

## FASE 3 — Fondamenta software
- **Obiettivo:** monorepo funzionante in locale con CI.
- **Attività:** pnpm workspaces, TypeScript strict, ESLint/Prettier, Vitest, Playwright,
  Wrangler locale, D1 locale con migrazioni, GitHub Actions (lint, test, build),
  Dependabot, secret scanning.
- **Dipendenze:** FASE 2; D-001 (repo dedicato).
- **File:** `package.json`, `pnpm-workspace.yaml`, `frontend/`, `backend/`, `admin/`,
  `shared/`, `games/`, `tests/`, `.github/workflows/*`.
- **Costi:** 0 € (GitHub Actions nel limite gratuito).
- **Test:** `pnpm test`, `pnpm typecheck`, `pnpm build` verdi in CI.
- **Completamento:** "hello world" end-to-end in locale (pagina → API → D1).
- **Rischi:** versioni instabili ⇒ dipendenze bloccate e versioni LTS.
- **Approvazioni:** push sul repo remoto.

## FASE 4 — Frontend
- **Obiettivo:** portale pubblico veloce, accessibile, mobile-first.
- **Attività:** home, catalogo, categorie, ricerca, pagina gioco, correlati,
  preferiti/cronologia locali, pagine informative, i18n, prerendering, sitemap, JSON-LD.
- **Dipendenze:** FASE 3.
- **File:** `frontend/src/**`, `shared/i18n/*`.
- **Costi:** 0 €.
- **Test:** Playwright E2E, axe (accessibilità), Lighthouse CI con budget (LCP < 2,5 s su 4G lento simulato, JS iniziale < 100 KB gzip).
- **Completamento:** Lighthouse mobile ≥ 90 in tutte le categorie, WCAG 2.2 AA senza errori automatici.
- **Rischi:** peso del bundle ⇒ code splitting, nessuna libreria UI pesante.
- **Approvazioni:** design definitivo.

## FASE 5 — Backend e database
- **Obiettivo:** API sicura e dati persistenti.
- **Attività:** API Hono versionata, schema e migrazioni D1, autenticazione (sessioni
  con cookie HttpOnly, magic link/passkey), catalogo, preferiti, eventi aggregati,
  rate limiting, audit log.
- **Dipendenze:** FASE 3 (in parallelo alla 4).
- **File:** `backend/src/**`, `backend/migrations/*.sql`, `shared/schema/*`.
- **Costi:** 0 € (piano Free). **Nota:** l'invio di email per i magic link richiede un
  provider; alternativa gratuita: solo passkey (WebAuthn) oppure piani gratuiti da verificare (D-008).
- **Test:** unit e integrazione con D1 locale; test di sicurezza su input (Zod).
- **Completamento:** copertura ≥ 80 % sul backend, 0 query SQL non parametrizzate.
- **Rischi:** limiti giornalieri D1 ⇒ cache e scritture aggregate.
- **Approvazioni:** provider email (se necessario).

## FASE 6 — Motore giochi
- **Obiettivo:** caricamento, isolamento, versioning, telemetria tecnica dei giochi + primi giochi interni.
- **Attività:** manifest per gioco, build statica per gioco, player iframe sandbox su
  origin separato, SDK `postMessage` minimo (ready/score/error/pause), kill switch,
  misurazione dei tempi di caricamento ed errori; sviluppo di 6–10 giochi originali.
- **Dipendenze:** FASI 4–5.
- **File:** `games/<slug>/**`, `games/sdk/*`, `frontend/src/player/*`, `backend/src/games/*`.
- **Costi:** 0 €. Asset solo originali o CC0 verificati.
- **Test:** test di sandbox (il gioco non può leggere cookie né chiamare l'API admin), E2E per ogni gioco, budget di peso per gioco.
- **Completamento:** gate **G2**.
- **Rischi:** qualità dei giochi ⇒ playtest e checklist.
- **Approvazioni:** lista definitiva dei giochi.

## FASE 7 — Amministrazione
- **Obiettivo:** gestire tutto senza toccare il codice.
- **Attività:** dashboard, giochi/versioni, registro licenze con blocco di pubblicazione,
  utenti, audit log, ruoli (owner/editor/viewer), MFA obbligatoria.
- **Dipendenze:** FASE 5.
- **File:** `admin/src/**`, `backend/src/admin/*`.
- **Costi:** 0 €. **Alternativa gratuita** per proteggere l'admin: Cloudflare Access (piano gratuito fino a 50 utenti **[TERZI, da verificare]**) oppure autenticazione propria con passkey.
- **Test:** test di autorizzazione per ogni endpoint (accesso negato di default).
- **Completamento:** nessuna operazione di catalogo richiede deploy.
- **Approvazioni:** uso di Cloudflare Access (account).

## FASE 8 — Monetizzazione
- **Obiettivo:** ad server diretto, sponsor e predisposizione Premium.
- **Attività:** inserzionisti, campagne, creatività (solo immagini statiche
  validate, nessun JS di terzi), spazi, calendario, frequency cap senza cookie
  (in memoria/sessione), conteggio impression e clic deduplicato, report CSV,
  stato pagamenti manuale, storico contratti; media kit; Premium in modalità "lista d'attesa".
- **Dipendenze:** FASI 5 e 7.
- **File:** `backend/src/ads/*`, `admin/src/ads/*`, `frontend/src/ads/*`.
- **Costi:** 0 €. Nessun processore di pagamento (D-006).
- **Test:** il layout resta corretto con 0 annunci; test anti-frode di base.
- **Completamento:** campagna di test servita e rendicontata in locale.
- **Rischi:** frode, inserzionisti assenti ⇒ R2/R9.
- **Approvazioni:** listino prezzi, contratto tipo per inserzionisti (revisione legale).

## FASE 9 — Sicurezza e conformità
- **Obiettivo:** ridurre i rischi tecnici e legali prima del lancio.
- **Attività:** threat model, header di sicurezza, CSP, revisione OWASP ASVS L1,
  privacy policy, cookie policy, termini, registro dei trattamenti, procedura DSA
  (notice and action, punto di contatto), processo per le richieste GDPR.
- **Dipendenze:** FASI 4–8.
- **File:** `docs/SECURITY.md`, `docs/LEGAL_CHECKLIST.md`, `frontend/src/pages/legal/*`.
- **Costi:** 0 € interni; **revisione professionale consigliata (a pagamento, D-009)**.
- **Test:** scansione dipendenze, OWASP ZAP baseline (gratuito), test degli header.
- **Completamento:** gate **G3**.
- **Approvazioni:** revisione legale.

## FASE 10 — QA e test
- **Obiettivo:** qualità verificata su dispositivi reali ed emulati.
- **Attività:** regressione E2E, test su browser (Chromium/Firefox/WebKit via Playwright),
  dispositivi di fascia bassa emulati, test di carico leggero, piano di rollback.
- **Dipendenze:** FASE 9.
- **Costi:** 0 €.
- **Completamento:** tutti i test verdi, nessun bug critico o alto aperto.

## FASE 11 — Lancio controllato
- **Obiettivo:** messa online graduale e misurata.
- **Attività:** deploy su `*.pages.dev` non indicizzato (beta privata), poi dominio,
  Search Console, sitemap, monitoraggio, primi contenuti SEO.
- **Dipendenze:** gate G3 + **G4** (autorizzazione esplicita).
- **Costi:** **dominio ~10–15 €/anno**; soggetto fiscale prima di qualunque incasso.
- **Approvazioni:** account Cloudflare, acquisto dominio, pubblicazione, apertura obrt.

## FASE 12 — Crescita e ottimizzazione
- **Obiettivo:** raggiungere le soglie dei gate G5/G6.
- **Attività:** nuovi giochi, daily challenge, SEO contenutistico, ottimizzazione della
  retention, media kit e (con autorizzazione) contatto con i primi inserzionisti.
- **Costi:** possibile Workers Paid (~5 $/mese) oltre le soglie; licenze (se approvate).
- **Approvazioni:** ogni contatto commerciale, ogni contratto, attivazione di Premium a pagamento.

## FASE 13 — Operatività completa
- **Obiettivo:** gestione ricorrente con automazioni e reportistica economica reale.
- **Ingresso:** gate **G7**.
- **Attività:** runbook, automazioni complete, revisione trimestrale del modello,
  valutazione passaggio a d.o.o. o fuori dal regime paušalni.
