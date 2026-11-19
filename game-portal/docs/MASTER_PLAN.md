# GAME PORTAL — Master Plan (FASE 0: audit e pianificazione)

> Stato: **FASE 0 e FASE 1 completate.** Approvazione utente del 2026-11-19 ("Autorizzo tutto").
> Data: 2026-11-19. Nessun acquisto, nessuna pubblicazione, nessun contatto esterno.
> Legenda fonti: **[UFF]** fonte ufficiale · **[DICH]** dichiarato dall'azienda ·
> **[TERZI]** stima/fonte secondaria · **[IPOTESI]** assunzione da validare · **[NV]** non verificabile.

---

## A. Rapporto di audit

### A.1 Ambiente di esecuzione

| Elemento | Rilevato | Note |
|---|---|---|
| Ambiente | Container cloud Claude Code (Linux x86_64, 4 vCPU, 15 GiB RAM) | Effimero: ciò che non è committato e pushato si perde |
| Claude Code | 2.1.328 | Disponibile |
| Node.js / npm | v22.23.5 / 10.9.9 | Sufficiente per Vite, React, Wrangler |
| pnpm / bun | 10.28.0 / 1.4.4 | Alternative installate |
| Python | 3.13.18 | Usato per script di modello e automazioni |
| Git | 2.43.0 | Repo configurato, remote GitHub |
| Docker | 29.10.0 | Disponibile (non necessario per il progetto) |
| Wrangler (CLI Cloudflare) | **non installato** | Installabile gratis via npm (v8.3.8 disponibile); `wrangler dev` funziona in locale **senza account** |
| sqlite3 CLI | non installato | Non indispensabile: D1 locale gira dentro Wrangler/Miniflare |
| Browser headless | Chromium + Playwright preinstallati | Usabili per test E2E, accessibilità e performance |
| Rete | Registry npm/PyPI raggiungibili; web pubblico raggiungibile via proxy | OK per ricerca e dipendenze |

Versioni npm correnti rilevate: `vite` 8.x, `react` 19.3.1, `hono` 4.13.19, `wrangler` 8.3.8.

### A.2 Directory di lavoro — risultato critico

La directory `/home/user/freelm` **non è un progetto di portale giochi**: è **freelm**,
una libreria Python/TypeScript (gateway LLM). Non esiste alcun lavoro preesistente sul
portale. Il branch di lavoro assegnato è `claude/game-portal-master-mm5azl`, creato da
`05438a2` (codice freelm).

Conseguenze:
- Non ho modificato nessun file di freelm.
- Tutta la documentazione di FASE 0 è isolata in `game-portal/` su questo branch.
- **Decisione richiesta D-001:** il portale deve vivere in un **repository dedicato**
  (es. `game-portal`, privato, GitHub Free). Mescolarlo con freelm vìola indipendenza,
  trasferibilità e pulizia della storia Git. Creare il repo è gratuito ma è
  un'azione sul tuo account: serve la tua autorizzazione.
- Commit locale eseguito; **nessun push** finché non lo autorizzi (regola 14 del brief).
  Attenzione: il container è effimero, quindi senza push il lavoro può andare perso.

### A.3 Strumenti e connettori disponibili (rilevanti)

- Utilizzabili gratuitamente ora: Git/GitHub (repo esistente), npm, Playwright, ricerca web.
- Connettori presenti nell'ambiente (Canva, Fiverr, Upwork, Shopify, QuickBooks, Supabase,
  Gmail, ecc.) **non verranno usati**: comportano account, contatti esterni o servizi
  commerciali vietati dai vincoli 2.6–2.12 senza autorizzazione.

---

## B. Piano operativo completo

Il dettaglio fase per fase (obiettivo, attività, dipendenze, file, strumenti, costi,
alternative gratuite, test, criteri di completamento, rischi, approvazioni) è in
[`ROADMAP.md`](ROADMAP.md). Sintesi strategica:

**Tesi di posizionamento (da validare in FASE 1).** Un nuovo entrante a budget zero non
può competere con Poki/CrazyGames sul volume del catalogo (centinaia di partner, migliaia di
giochi). La strategia consigliata è un **portale di nicchia curato**:

1. **Giochi classici e "evergreen" realizzati internamente**: solitario, sudoku, mahjong
   a tessere, campo minato, dama, scacchi, puzzle logici, word game. Le *meccaniche* di
   questi giochi non sono proteggibili (le implementazioni, grafica e nomi commerciali sì:
   tutto va scritto da zero, senza copiare). Alto volume di ricerca organica.
2. **Pubblico adulto (18+)**: valore pubblicitario più alto, meno obblighi di protezione
   dei minori. I minori non vanno esclusi tecnicamente, ma il sito non va progettato
   per loro (vedi LEGAL_CHECKLIST).
3. **Retention con "daily challenge"**: puzzle del giorno, classifiche e serie di giorni
   consecutivi (streak). È la leva che giustifica Premium e sponsor.
4. **Catalogo esterno** solo tramite licenze dirette o open source verificato, come
   fase successiva.

Questo approccio rende il catalogo un **asset proprietario** (nessun revenue share,
nessun aggregatore) e sfrutta Claude Code come capacità produttiva per i giochi.

---

## C. Architettura consigliata

Dettaglio in [`ARCHITECTURE.md`](ARCHITECTURE.md). In sintesi:

- **Monorepo TypeScript** (pnpm workspaces): `frontend/` (React + Vite, prerendering
  statico per SEO), `backend/` (Cloudflare Worker con Hono), `admin/` (SPA React separata,
  protetta), `shared/` (tipi e schemi Zod), `games/` (ogni gioco come bundle statico isolato).
- **Hosting:** Cloudflare Pages (statico) + Workers (API) + D1 (SQLite) + R2 opzionale.
  Tutti nel piano gratuito ai volumi iniziali.
- **Isolamento giochi:** iframe `sandbox="allow-scripts"` servito da un **origin separato**
  (`games.<dominio>` o `*.pages.dev`), CSP restrittiva, `postMessage` con schema validato.
- **Portabilità:** Hono gira anche su Node/Bun/Deno; D1 è SQLite standard ⇒ migrazione
  possibile verso VPS o altro provider senza riscrivere.

---

## D. Modello economico (sintesi)

Dettaglio, formule e parametri in [`FINANCIAL_MODEL.md`](FINANCIAL_MODEL.md); calcolo
riproducibile con `python3 game-portal/scripts/financial_model.py`.

Visitatori unici mensili necessari per **3.000 € di utile netto mensile** (tutti i
parametri sono **[IPOTESI]**):

| Scenario | Visitatori/mese per 3.000 € netti | Pareggio |
|---|---:|---:|
| Prudente | ~1.430.000 | ~179.000 |
| Intermedio | ~246.000 | ~50.000 |
| Ambizioso | ~80.000 | ~21.000 |
| Stress test | ~6,6 milioni | ~1,07 milioni |

*(Aggiornato con il modello v1 dopo la FASE 1: Premium ridotto in base all'evidenza raccolta.)*

**Lettura onesta:**
- Il costo fisso dominante **non è l'infrastruttura** (≈0 €), ma i **contributi
  obbligatori** se si apre un obrt (~291–299 €/mese, fonti secondarie) e il commercialista.
  Finché non esiste un soggetto fiscale non si possono incassare ricavi in modo lecito.
- Il vincolo "niente reti pubblicitarie" significa che **i ricavi pubblicitari saranno
  ~0 finché il traffico non permette la vendita diretta**, cioè probabilmente per
  molti mesi. Gli inserzionisti diretti raramente comprano siti con meno di decine di
  migliaia di visitatori al mese **[IPOTESI]**.
- Premium richiede un sistema di incasso; senza un processore di pagamento (vietato per
  ora) Premium è di fatto **0 €** nelle prime fasi.
- Il raggiungimento dei 3.000 € **non è garantito** e, per un sito nuovo basato su SEO,
  richiede tipicamente **12–36 mesi** di crescita organica **[IPOTESI]**, se avviene.

---

## E. Stima dei tempi per fase

Ipotesi: un titolare part-time (10–20 h/settimana di revisione e decisioni) + Claude Code
per lo sviluppo. Gli intervalli includono revisione umana; non includono i tempi di
professionisti esterni (legali/fiscali).

| Fase | Durata stimata |
|---|---|
| 0 — Audit e pianificazione | completata (1 giorno) |
| 1 — Ricerca mercato e validazione | 1–2 settimane |
| 2 — Architettura e documentazione | 1 settimana |
| 3 — Fondamenta software | 1–2 settimane |
| 4 — Frontend | 2–4 settimane |
| 5 — Backend e database | 2–3 settimane |
| 6 — Motore giochi (+ primi 6–10 giochi interni) | 3–6 settimane |
| 7 — Amministrazione | 2–3 settimane |
| 8 — Monetizzazione (ad server diretto, sponsor) | 2–4 settimane |
| 9 — Sicurezza e conformità | 1–2 settimane + revisione professionale |
| 10 — QA e test | 1–2 settimane |
| 11 — Lancio controllato | 4–8 settimane |
| 12 — Crescita e ottimizzazione | 6–24 mesi |
| 13 — Operatività completa | solo dopo il superamento dei criteri GO |

**Totale fino al lancio controllato: ~4–7 mesi.** Le fasi 4–8 possono sovrapporsi in parte.

---

## F. Elenco delle funzionalità

**Pubblico (MVP = fase 11):** home, catalogo, categorie, tag, ricerca (lato client,
indice statico), pagina gioco con player sandboxed, giochi correlati, preferiti e
cronologia (prima in `localStorage`, senza account), puzzle del giorno, pagine
informative (chi siamo, privacy, cookie, termini, contatti, pubblicizza con noi),
pagine pronte per più lingue (i18n), sitemap e dati strutturati.

**Account (post-MVP):** registrazione con email e passkey/magic link, profilo,
sincronizzazione preferiti e cronologia, classifiche, streak, Premium (niente
pubblicità, temi, statistiche, archivio puzzle).

**Backend:** API REST versionata, autenticazione, catalogo, versioni dei giochi,
eventi di sessione aggregati e anonimi, ad serving, report, rate limiting, audit log.

**Admin:** dashboard, giochi e versioni, registro licenze con blocco di pubblicazione,
utenti, inserzionisti, campagne, creatività, spazi, sponsor, Premium, analisi
economica, report CSV, log di audit, sospensione immediata di un gioco.

**Automazioni:** uptime, errori, backup D1 su GitHub, link checker, licenze in
scadenza, report settimanali, controllo performance (Lighthouse CI), aggiornamenti
delle dipendenze (Dependabot/Renovate gratuiti).

---

## G. Costi presenti e futuri

| Voce | Ora (FASE 0–10) | Al lancio (FASE 11) | In crescita | Alternativa gratuita / note |
|---|---|---|---|---|
| Sviluppo (Claude Code) | Abbonamento già esistente dell'utente | idem | idem | Nessun costo aggiuntivo previsto |
| Repository (GitHub Free) | 0 € | 0 € | 0 € | Repo privati illimitati, Actions 2.000 min/mese sui privati |
| Hosting statico (Cloudflare Pages) | 0 € | 0 € | 0 € | Richiesta statica gratuita e illimitata **[TERZI, da verificare]** |
| API (Workers) | 0 € | 0 € | **~5 $/mese** oltre 100k richieste/giorno | Cache aggressiva, logica statica, batching |
| Database (D1) | 0 € | 0 € | Incluso nel piano Workers Paid oltre limiti | Dal 1/9/2026 le query falliscono oltre i limiti giornalieri del piano Free **[UFF]** |
| **Dominio** | 0 € (`*.pages.dev`) | **~10–15 €/anno** | idem | **Primo costo inevitabile**: un brand senza dominio proprio non è credibile per gli inserzionisti |
| Email di contatto | 0 € | 0 € | 0 € | Cloudflare Email Routing (inoltro) |
| Monitoraggio/backup | 0 € | 0 € | 0 € | GitHub Actions + cron Worker |
| **Soggetto fiscale (obrt paušalni)** | 0 € | **~291–299 €/mese** contributi **[TERZI]** | + imposta paušalna annua | **Inevitabile prima di incassare**. Alternative (attività occasionale, d.o.o.) da valutare col commercialista |
| Commercialista | 0 € | 50–150 €/mese **[IPOTESI]** | idem | Possibile fai-da-te per paušalni, sconsigliato con vendite UE |
| Consulenza legale (privacy/termini) | 0 € | 300–1.500 € una tantum **[IPOTESI]** | — | Modelli ufficiali (EDPB, AZOP) + revisione minima |
| Licenze giochi di terzi | 0 € | 0 € (solo giochi interni/OSS) | variabile | Giochi interni |
| Incasso pagamenti Premium | — | — | ~1,5–3 % + fisso per transazione **[TERZI]** | Bonifico SEPA manuale (non scalabile) |
| IVA / OSS | — | — | Obblighi oltre 10.000 €/anno B2C UE e oltre 60.000 € HR | Vedi LEGAL_CHECKLIST |
| Marchio (EUIPO/DZIV) | — | opzionale | ~850 € UE (1 classe) **[TERZI]** | Registrazione nazionale più economica; rimandabile |

**Costi nascosti da dichiarare:** il tempo del titolare (non monetizzato nel modello),
il passaggio a Workers Paid oltre le soglie, la possibile necessità di un d.o.o. oltre i
60.000 € di ricavi annui, e la revisione legale obbligatoria prima del lancio.

---

## H. Rischi e contromisure

| # | Rischio | Tipo | Prob. | Impatto | Contromisura |
|---|---|---|---|---|---|
| R1 | Traffico insufficiente (SEO lento, concorrenza enorme) | Economico | Alta | Alto | Nicchia evergreen adulta, daily challenge, SEO tecnico, criteri NO-GO a 6/12 mesi |
| R2 | Assenza di inserzionisti diretti a basso traffico | Economico | Alta | Alto | Sito valido anche a 0 annunci; media kit solo oltre una soglia di traffico; decisione D-007 su fallback |
| R3 | Catalogo povero rispetto ai concorrenti | Prodotto | Alta | Medio | Qualità > quantità; pipeline interna da 1–3 giorni per gioco semplice |
| R4 | Violazione di proprietà intellettuale (cloni, asset) | Legale | Media | Alto | Registro licenze con blocco di pubblicazione, solo asset originali o CC0, nessun nome o trade dress di terzi |
| R5 | GDPR/ePrivacy (cookie, analytics, account) | Legale | Media | Alto | Analytics senza cookie e aggregato, nessun tracker di terzi, DPIA leggera, revisione legale |
| R6 | Utenti minorenni | Legale | Media | Alto | Niente profilazione, nessuna pubblicità personalizzata, contenuti PEGI 3–12, chat assente |
| R7 | Lock-in o modifica dei piani gratuiti Cloudflare | Tecnico | Media | Medio | Hono + SQLite portabili, export D1 giornaliero, IaC in repo |
| R8 | Gioco malevolo o compromesso (terzi/OSS) | Sicurezza | Bassa | Alto | Origin separato, sandbox, CSP, revisione del codice, kill switch |
| R9 | Abuso o frode pubblicitaria (clic e impression falsi) | Sicurezza/Econ. | Media | Medio | Deduplica, rate limit, filtro bot, report "certificabili" con metodologia pubblica |
| R10 | Obblighi fiscali sottovalutati (OSS, PDV ID, fatture B2B estero) | Fiscale | Media | Alto | Checklist da commercialista prima del primo incasso |
| R11 | Dipendenza dal tempo del titolare | Operativo | Alta | Medio | Automazioni, runbook, fasi con criteri chiari |
| R12 | Perdita del lavoro (container effimero, nessun push) | Tecnico | Media | Medio | Autorizzare push su repo dedicato privato (D-001/D-002) |

---

## I. Criteri GO / NO-GO

| Gate | Momento | GO se | NO-GO / correzione se |
|---|---|---|---|
| G1 | Fine FASE 1 | Nicchia con keyword di volume verificato (strumenti gratuiti: Google Trends, Search Console di siti esistenti, autocomplete) e concorrenza affrontabile; nessun blocco legale | Nessuna nicchia difendibile ⇒ si rivede la tesi |
| G2 | Fine FASE 6 | ≥ 6 giochi interni completi, Lighthouse ≥ 90 su mobile, isolamento sandbox verificato da test | Giochi < 6 o performance < 80 |
| G3 | Fine FASE 10 | 0 vulnerabilità alte, checklist legale rivista da un professionista, tutti i test verdi | Qualunque punto aperto bloccante |
| G4 | Prima del lancio pubblico | Autorizzazione esplicita dell'utente, dominio, soggetto fiscale definito | Mancanza di autorizzazione |
| G5 | Lancio + 6 mesi | ≥ 10.000 visitatori/mese organici e retention D7 ≥ 10 % **[IPOTESI soglia]** | < 3.000 visitatori/mese ⇒ pivot di nicchia o stop |
| G6 | Lancio + 12 mesi | Traffico ≥ soglia di pareggio dello scenario intermedio (~30.000/mese) e primo inserzionista diretto | Sotto il 50 % della soglia ⇒ rivalutare modello (D-007) |
| G7 | FASE 13 | Utile netto ≥ 3.000 € per 3 mesi consecutivi, documentato da contabilità reale | — |

---

## J. Primo passo tecnico a costo zero

**Proposta (richiede approvazione):**

1. **D-001/D-002:** creare un repository GitHub **privato dedicato** `game-portal`
   (gratuito) e autorizzare il push; spostare lì questa documentazione.
2. **FASE 1 (ricerca)**, interamente gratuita e senza contatti: dossier concorrenti con
   fonti classificate, analisi keyword con strumenti gratuiti, verifica normativa su
   fonti ufficiali (EUR-Lex, Porezna uprava, AZOP).
3. In parallelo, **proof of concept locale** (nessun account, nessun deploy): scaffold
   pnpm + Vite + React + Hono e `wrangler dev` con D1 locale, più un iframe sandbox
   che carica un mini-gioco originale da un secondo origin locale. Serve a validare
   l'architettura di isolamento prima della FASE 2.

Costo: **0 €**. Nulla viene pubblicato online.
