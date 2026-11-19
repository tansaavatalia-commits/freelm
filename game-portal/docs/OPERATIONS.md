# Tabluo — Operatività e automazioni

Principi: ogni automazione ha **log**, **interruttore** (disattivabile), **gestione degli
errori**. Nessuna automazione paga, firma, pubblica giochi senza licenza valida o contatta
terzi.

| Automazione | Stato | Strumento (gratuito) | Interruttore | Esito in caso di errore |
|---|---|---|---|---|
| Test + build ad ogni push | **Pronta** (`.github/workflows/ci.yml`) | GitHub Actions | disabilitare il workflow | PR/commit segnato rosso |
| Controllo licenze giornaliero | **Pronta** (job `licenses`, cron 05:17 UTC) | GitHub Actions + `scripts/build-catalog.ts` | rimuovere `schedule` | job fallito = licenza scaduta; avviso a 30 giorni nel log |
| Blocco pubblicazione senza licenza | **Attiva** | `build-catalog.ts` (exit 1) | — (non disattivabile per scelta) | build interrotta |
| Sospensione immediata gioco | **Attiva** | `POST /admin-api/games/:slug/suspend` | — | registrata in `audit_log` |
| Aggiornamenti dipendenze | Da attivare nel repo dedicato | Dependabot | file di configurazione | PR automatica, mai merge automatico |
| Monitoraggio uptime | FASE 11 | cron GitHub Actions su `/api/v1/health` | workflow | issue automatica nel repo |
| Backup D1 | FASE 11 | `wrangler d1 export` in Actions → artifact cifrato | workflow | job fallito |
| Report traffico/giochi | FASE 11 | `/admin-api/stats/daily` → CSV settimanale | workflow | job fallito |
| Report pubblicità | FASE 11 | `/admin-api/campaigns/:id/report` | — | — |
| Link checker e performance | FASE 10 | Playwright + Lighthouse CI | workflow | job fallito |
| Anomalie (picchi di errori, clic sospetti) | FASE 12 | query su `events_daily`/`ad_daily_stats` | workflow | issue automatica |

## Runbook essenziali
- **Gioco con problema di sicurezza o diritti:** sospendere subito via admin API, motivo
  obbligatorio; poi correggere o rimuovere il gioco via Git e aggiornare `license.json`.
- **Token admin compromesso:** `wrangler secret put ADMIN_TOKEN` con un nuovo valore
  (effetto immediato); controllare `audit_log`.
- **Superamento limiti del piano gratuito:** le pagine statiche continuano a funzionare;
  l'API risponde con errori ⇒ il player resta giocabile (kill switch "fail-open") e la
  pubblicità collassa. Valutare Workers Paid (~5 $/mese) **solo con autorizzazione**.
