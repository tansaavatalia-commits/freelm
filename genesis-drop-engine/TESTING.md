# TESTING — Strategia e standard di test

## 1. Stato attuale

**Nessun test eseguito**: in Fase 1 non esiste codice applicativo. Questa sezione verrà aggiornata con
risultati reali (comando, data, esito) a ogni sessione in cui si eseguono test.

## 2. Livelli di test

| Livello | Strumenti | Cosa copre |
|---------|-----------|-----------|
| Unità | pytest | Dominio puro: Money, Profit Engine, gate BR-xxx, state machine, scoring |
| Property-based | hypothesis | Profit Engine (monotonia: costo ↑ ⇒ profitto ↓; multipack; arrotondamenti), ledger (somma zero sempre), liquidità (mai negativa dopo un'autorizzazione) |
| Integrazione | pytest + testcontainers (PostgreSQL reale) | Repository, vincoli DB, lock concorrenti, outbox, migrazioni |
| Contract | suite comune per connettori | Ogni connettore (reale e fake) rispetta lo stesso contratto; risposte registrate (cassette) sanificate |
| End-to-end | connettori fake deterministici | Flusso completo scoperta → riconciliazione (`MASTER_SPECIFICATION.md` §5) |
| Simulazioni finanziarie | scenari dichiarativi YAML | Payout immediato/ritardato, fondi trattenuti, liquidità insufficiente, aumenti prezzo/spedizione, resi, rimborsi, chargeback, fornitori alternativi, pagamento fornitore fallito |
| Architetturali | import-linter | Confini tra moduli (il dominio non importa connettori/infrastruttura) |
| Sicurezza | gitleaks, pip-audit, bandit | Segreti, dipendenze vulnerabili, pattern rischiosi |
| Ripristino | job dedicato | Restore del backup e verifica integrità |

## 3. Regole critiche con test obbligatori (non rimovibili)

Ogni regola ha almeno un test positivo, uno negativo e uno di confine:

- BR-001 €1,00: 1,00 ammesso; 1,01 rifiutato; conversione valuta con margine di cambio.
- BR-010/011: €3,00 esatti ammessi; €2,99 rifiutati; multipack 5 → €15; scenario prudenziale usato.
- Calcolo `INCOMPLETE` quando manca un costo → impossibile `PROFIT_VERIFIED`.
- Compliance `FAILED`/`UNRESOLVED` → impossibile `READY_FOR_APPROVAL`, anche con punteggio 100.
- Zero-Advance: fondi `MARKETPLACE_HELD` non contano; ordine bloccato se le riserve scendono sotto il minimo;
  fornitore alternativo scelto solo se tutti i vincoli reggono; due autorizzazioni concorrenti non spendono
  lo stesso denaro.
- Idempotenza: stessa `idem_key` → un solo ordine fornitore / un solo listing / una sola scrittura ledger.
- Kill switch: nessuna azione esterna esce quando attivo.
- eBay: impossibile registrare il connettore o il marketplace.

## 4. Standard

- Copertura minima: **95% righe e rami** su `core/`, `policy/`, `modules/profit`, `modules/zero_advance`,
  `modules/cashflow`, `modules/compliance`; 80% sul resto.
- Nessun test usa la rete reale; i test contro sandbox ufficiali sono marcati `@pytest.mark.sandbox` ed
  eseguiti solo manualmente con credenziali di test.
- Nessun test può essere disattivato o messo in quarantena per far passare la CI.
- Dati di test sintetici e dichiarati come tali; nessun dato reale di clienti nei fixture.
- CI (GitHub Actions, gratuita per l'uso previsto): ruff, mypy, pytest (unità + integrazione), gitleaks.

## 5. Registro esecuzioni

| Data | Comando | Esito | Note |
|------|---------|-------|------|
| 2026-11-20 | — | Nessun test (Fase 1, solo documentazione) | — |
