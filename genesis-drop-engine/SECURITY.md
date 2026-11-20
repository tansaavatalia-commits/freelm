# SECURITY — Sicurezza e governance

## 1. Credenziali e segreti

- **Mai segreti in Git.** `.env` è escluso; `.env.example` contiene solo nomi di variabili.
- Sviluppo: variabili d'ambiente da `.env` locale. File di configurazione sensibili versionabili solo
  cifrati con **SOPS + age** (chiave privata solo sulla macchina dell'operatore).
- Produzione: Docker secrets o secret manager; migrazione a Vault/cloud solo se necessaria.
- Il database memorizza solo **riferimenti** ai segreti (`credentials_ref`), mai i token.
- Token OAuth dei marketplace: cifrati a riposo (chiave applicativa separata), rotazione documentata.
- Scansione automatica: `gitleaks` in pre-commit e CI.
- Log e audit mascherano qualsiasi valore riconoscibile come segreto.

## 2. Autenticazione e permessi

- Dashboard: login con password (hash Argon2id) + **TOTP** obbligatorio per `owner`.
- Ruoli `owner`, `operator`, `viewer`, `system` (vedi `MASTER_SPECIFICATION.md` §2), controllati
  lato server su ogni endpoint.
- Azioni critiche (cambio regole, livello automazione, approvazioni finanziarie oltre soglia):
  ri-autenticazione + conferma esplicita.
- Server in ascolto solo su `127.0.0.1` in sviluppo; esposizione esterna solo dietro reverse proxy con TLS.

## 3. Integrità delle operazioni

| Rischio | Contromisura |
|---------|--------------|
| Ordini duplicati | `UNIQUE(account_id, external_ref)` + import idempotente |
| Doppio pagamento fornitore | `idem_key` univoca su `supplier_orders` e `outbox_actions`; chiave inviata anche al fornitore quando l'API la supporta |
| Listing duplicati | `UNIQUE(account_id, product_id, pack_size)` |
| Doppia spesa della liquidità (concorrenza) | Lock di riga sul conto `bank_available` durante `FundingDecision` |
| Aggiramento delle regole | Gate nel dominio, non nell'interfaccia; test che provano ogni percorso |
| Manomissione dello storico | `audit_log` append-only con catena di hash, verificata da un job giornaliero |

## 4. Validazione degli input

- Pydantic v2 su tutti gli input API e su tutte le risposte dei connettori (i dati esterni sono non fidati).
- Limiti di dimensione, normalizzazione Unicode, sanificazione HTML nei contenuti generati.
- Protezione CSRF sulla dashboard; header di sicurezza (CSP, HSTS dietro TLS).
- I contenuti generati dall'LLM sono **dati non fidati**: mai eseguiti, sempre validati e approvati.

## 5. Rate limit e resilienza

Token bucket per connettore, backoff esponenziale con jitter su errori transitori, circuit breaker,
rispetto di `Retry-After`. Il guasto di un connettore non propaga.

## 6. Arresto di emergenza (kill switch)

- Flag `automation_settings.kill_switch` controllato dal dispatcher prima di **ogni** azione esterna.
- Attivabile da dashboard, CLI (`genesis kill-switch on`) o variabile d'ambiente all'avvio.
- Con kill switch attivo: nessun ordine, listing, aggiornamento prezzi o messaggio esce; la lettura continua.
- Disattivazione solo da `owner` con conferma; evento registrato.

## 7. Backup e ripristino

- `pg_dump` giornaliero cifrato + **restic** (deduplicato, cifrato) verso destinazione esterna scelta dall'operatore.
- Retention proposta: 7 giornalieri, 4 settimanali, 12 mensili.
- **Test di ripristino mensile automatizzato**: restore in DB temporaneo + verifica catena audit e bilanciamento ledger.
- RPO obiettivo 24 h (riducibile con WAL archiving), RTO obiettivo 2 h.

## 8. Dati personali (GDPR)

- Dati clienti minimi necessari al fulfillment; cifratura a riposo dei campi indirizzo/contatto.
- Retention configurabile; cancellazione/pseudonimizzazione dopo i termini legali.
- Registro dei trattamenti da redigere con l'impresa registrata (decisione legale fuori dal software).

## 9. Governance finanziaria

Nessuna transazione non autorizzata, nessun impegno finanziario nascosto, nessuna attivazione automatica di
abbonamenti, nessuna pubblicazione esterna senza autorizzazione (BR-031…BR-036, BR-052, BR-053).
