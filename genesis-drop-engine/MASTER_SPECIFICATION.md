# MASTER_SPECIFICATION — Specifica principale

Versione 0.1 (Fase 1, in attesa di approvazione). Documenti normativi collegati:
`BUSINESS_RULES.md` (regole vincolanti), `ARCHITECTURE.md`, `DATABASE.md`, `SECURITY.md`.
In caso di conflitto prevale `BUSINESS_RULES.md`.

## 1. Identità e obiettivo

GENESIS DROP ENGINE è un sistema operativo privato per il dropshipping, mercato iniziale Europa,
architettura predisposta per più negozi, marketplace, paesi, fornitori e operatori.
Obiettivo: trovare prodotti con potenziale reale, scegliere i fornitori migliori, calcolare la
redditività operativa reale, pubblicare prodotti approvati, gestire ordini, proteggere la liquidità,
automatizzare in sicurezza.

Priorità (in ordine): profitto reale → protezione della liquidità → affidabilità fornitori → qualità →
consegna → conformità → automazione → scalabilità → costi bassi → accuratezza e tracciabilità.

## 2. Attori e ruoli

| Ruolo | Permessi |
|-------|----------|
| `owner` | Tutto, incluse modifiche alle regole (`rule_sets`), livello di automazione, kill switch, approvazioni finanziarie |
| `operator` | Revisione e approvazione prodotti/listing/ordini entro limiti; nessuna modifica alle regole |
| `viewer` | Sola lettura |
| `system` | Job automatici; solo azioni consentite dal livello di automazione |

## 3. Requisiti funzionali per modulo

### M1 — Market Radar
- Rileva nicchie, trend, stagionalità, saturazione, opportunità geografiche, fasce di prezzo, bisogni.
- Finestre 30/90/365 giorni solo quando esistono dati affidabili; altrimenti `MISSING`.
- Mai inventare volumi di vendita; mai dedurre vendite da visualizzazioni/engagement.
- Fonti: solo API/feed autorizzati o dati pubblici consentiti dai termini d'uso (elenco fonti da
  validare in Fase 2; esempi: dati di catalogo dei marketplace via API ufficiali, servizi di trend
  con API ufficiali, dati statistici pubblici).

### M2 — Product Radar
- Ricerca multi-fonte, normalizzazione (titolo, attributi, unità, peso), deduplica.
- Matching tra fornitori: GTIN → attributi strutturati → similarità testuale (`pg_trgm`/`rapidfuzz`)
  → conferma manuale sotto una soglia di confidenza. Matching anche di varianti e SKU.
- Confronto prezzi, spedizione, copertura, stock; ogni dato con fonte e timestamp e stato di verifica.
- Flusso di stati: vedi `ARCHITECTURE.md` §5.1. I rifiutati conservano il motivo.

### M3 — Global Market Intelligence
- Per ogni prodotto candidato e paese: domanda, concorrenza, prezzi, fee, IVA, consegna, import, resi,
  requisiti normativi, profitto netto atteso. Classifica dei paesi per opportunità.

### M4 — Global Supplier Intelligence
- Confronto fornitori per prodotti equivalenti e destinazione (costo, spedizione, tempi, magazzino,
  qualità, stock, tracking, resi, **termini di pagamento**, storico).
- Sostituzione fornitore quando esiste un'opzione migliore **verificata**, mai violando profitto,
  conformità o liquidità.

### M5 — Profit Engine
- Calcolo per unità, multipack, paese, fornitore, canale, prezzo, ipotesi pubblicitarie.
- Tre scenari (ottimistico/centrale/prudenziale), voce per voce; gate sul prudenziale.
- Snapshot immutabili e riproducibili. Formula in `BUSINESS_RULES.md` §4.

### M6 — Compliance Engine
- Regole per categoria e paese (`compliance_rules`), evidenze richieste, esito `PASSED/FAILED/UNRESOLVED`.
- Blocco dell'approvazione se non verificabile, con elenco di ciò che manca. Nessuna falsa certezza legale.

### M7 — Cashflow Guardian
- Liquidità attuale e proiettata (14/30/60 giorni) dal ledger; payout attesi, trattenute, fee,
  obblighi fornitori, riserve, IVA, ordini aperti. Avviso prima di qualsiasi saldo negativo.

### M8 — Zero-Advance Engine
- Algoritmo in `BUSINESS_RULES.md` §7.3. Decisione idempotente e registrata (`funding_decisions`).
- Non aggirabile: la verifica avviene nel servizio di dominio dentro la stessa transazione che crea
  l'azione di outbox dell'ordine fornitore.

### M9 — Listing Studio
- Titoli SEO, descrizioni, attributi, traduzioni, keyword, prezzi proposti, istruzioni immagini,
  contenuto per marketplace e lingua.
- Generazione tramite `freelm` dietro il port `TextGenerator`; output validato (lunghezze, campi obbligatori
  del canale, lista di claim vietati, presenza delle informazioni GPSR).
- Ogni listing richiede approvazione dell'operatore (inizialmente sempre).

### M10 — Fulfillment Engine
- Ciclo completo dell'ordine (`ARCHITECTURE.md` §5.2) con audit trail per ordine: verifica prodotto/variante,
  scelta fornitore, ricontrollo profitto, liquidità, approvazione, ordine, tracking, notifiche, consegna,
  fallimenti, cancellazioni, resi, rimborsi.

### M11 — Marketplace Command Center
- Sync listing, prezzi, stock, ordini, tracking; prestazioni e fee per canale e paese; sospensione listing;
  salute dei canali con isolamento dei guasti.

### M12 — Control Tower
- Dashboard: ricavi, profitto operativo netto, liquidità utilizzabile, payout in attesa, ordini, prestazioni
  fornitori, prodotti migliori, opportunità, resi, canali, errori di integrazione, ordini bloccati, avvisi di
  conformità, stato automazione e kill switch. La prima schermata risponde a: *quanto denaro posso usare oggi?*
  Ogni cifra mostra se è verificata o stimata.

### Opportunity Scoring
- Pesi e interpretazione in `BUSINESS_RULES.md` §8. Filtri rigidi: conformità e liquidità.

## 4. Requisiti non funzionali

| Area | Requisito |
|------|-----------|
| Correttezza | Test obbligatori su tutte le regole BR-xxx; property test sul Profit Engine e sul ledger |
| Tracciabilità | Ogni decisione (gate, transizione, finanziamento, approvazione) è ricostruibile dall'audit |
| Sicurezza | Vedi `SECURITY.md` |
| Affidabilità | Nessuna perdita di ordini (import idempotente); outbox con retry; recovery testato |
| Prestazioni | Obiettivo iniziale: 100k offerte fornitore, 10k prodotti canonici, 1k ordini/mese su hardware modesto |
| Costi | Infrastruttura €0 in sviluppo; vedi `COST_CONTROL.md` |
| Portabilità | Docker Compose; nessun lock-in su cloud specifici |
| Continuità | Documentazione aggiornata a fine sessione; GitHub come fonte di verità |

## 5. Flusso end-to-end di riferimento

```
SCOPERTA → ANALISI → CONFRONTO FORNITORI → VERIFICA PROFITTO → CONFORMITÀ → APPROVAZIONE OPERATORE
→ LISTING → ORDINE CLIENTE → CONTROLLO LIQUIDITÀ → ORDINE FORNITORE → TRACKING → NOTIFICA CLIENTE
→ RICONCILIAZIONE FINANZIARIA
```

Ogni freccia è un use case con test di integrazione; il flusso completo è un test end-to-end eseguito
con connettori *fake* (Fase 2) e sandbox ufficiali (Fase 3). Nessuna transazione reale senza autorizzazione.

## 6. Criteri di accettazione finale

I 20 criteri del prompt master (sezione 10) sono adottati integralmente come checklist di lancio;
saranno tracciati in `PROJECT_STATUS.md` con stato e prova (test/file) per ciascuno.

## 7. Fuori ambito (per ora)

- Contabilità fiscale ufficiale e dichiarazioni (solo export per il commercialista).
- eBay (escluso permanentemente).
- Qualsiasi raccolta dati non autorizzata.
