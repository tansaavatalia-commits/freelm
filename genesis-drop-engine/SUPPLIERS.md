# SUPPLIERS — Ricerca fornitori e stato di integrabilità

Ricerca di Fase 1 (data: 2026-11-20). **Nessun account è stato creato, nessuna API attivata.**
Le informazioni marcate *(da verificare)* provengono da fonti secondarie o incomplete e vanno
confermate sui siti ufficiali prima di qualsiasi integrazione (Fase 3).

## 1. Criteri di valutazione

Per ogni fornitore il sistema registrerà: disponibilità API ufficiale, requisiti di accesso, feed,
autorizzazioni, costi, copertura prodotti, sincronizzazione stock, matching varianti, destinazioni,
tempi di consegna, tracking, resi, **condizioni di pagamento**, affidabilità e storico.

## 2. Tabella comparativa iniziale

| Fornitore | Stato integrazione | Accesso / costi | Pagamento | Rilevanza per €1/unità | Note |
|-----------|--------------------|-----------------|-----------|------------------------|------|
| **CJdropshipping** | OFFICIAL_API (API 2.0) | Account gratuito + chiave API | **Prepagato dal saldo** (`payType=2` paga dal saldo alla creazione; `payType=3` crea e poi paga con `payBalanceV2`) | Alta (catalogo ampio a basso costo) | Webhook per ordini/tracking; importi in USD; magazzini UE per parte del catalogo *(da verificare per SKU)* |
| **AliExpress** (Open Platform) | API_APPROVAL_REQUIRED | Registrazione sviluppatore, accettazione Open Platform Agreement, audit dell'app; categoria "Dropship"/"Order Management" | Prepagato | Alta | Requisiti di idoneità e restrizioni geografiche *(da verificare)*; solo integrazione ufficiale, nessuno scraping |
| **BigBuy** (Spagna, magazzino UE) | OFFICIAL_API (piano a pagamento) | Abbonamento richiesto; prezzi divergenti nelle fonti (da ~€52 a ~$149/mese + eventuale quota di attivazione) *(da verificare)* | Prepagato/wallet *(da verificare)* | Bassa (prezzi unitari raramente ≤ €1) ma **nessun dazio UE** e consegne rapide | Utile per prodotti/multipack sopra soglia solo con eccezione approvata |
| **Syncee** | Marketplace di fornitori; API per i fornitori, accesso retailer via app | Piani ~€0–129/mese *(da verificare)* | Varia per fornitore | Media | Recensioni recenti negative su rimborsi/affidabilità *(segnalazioni utenti, non verificate)* |
| **Spocket** | App (orientata a Shopify/WooCommerce) | Da ~$39,99/mese *(da verificare)* | Varia | Bassa (fornitori UE/US più costosi) | Segnalati "fornitori locali" che sono rivenditori |
| **Alibaba** | Accesso API limitato; principalmente manuale/RFQ | Gratuito per sourcing manuale | Termini negoziabili (Trade Assurance) | Alta per **acquisto all'ingrosso** | Rilevante se si passa a stock in magazzino UE (modello diverso dal dropshipping puro) |
| **Printful** | OFFICIAL_API | Gratuito, si paga per ordine | Prepagato/carta | Nulla (costi unitari molto superiori a €1) | Fuori dal modello €1; solo eventuale linea separata |
| **Produttori/grossisti diretti** | MANUAL / AUTHORIZED_FEED (CSV/XML) | Accordi commerciali | **Unica via realistica per termini di pagamento differito** | Variabile | Richiede negoziazione da parte dell'operatore |

## 3. Implicazioni per la politica Zero-Advance

- I principali fornitori dropshipping con API (CJ, AliExpress) operano a **pagamento anticipato**.
  Il pagamento differito o il credito commerciale sono, in pratica, ottenibili solo da grossisti/produttori
  con accordo diretto e storico ordini. Il sistema non li presume mai: vanno verificati e registrati.
- Conseguenza: all'avvio, con saldo zero, l'ordine fornitore sarà `BLOCKED_INSUFFICIENT_FUNDS` finché il
  primo payout del marketplace non è `AVAILABLE` (vedi `BUSINESS_RULES.md` §7.5, decisione D-011).

## 4. Implicazioni del dazio UE €3 (dal 2026-07-01)

- Fornitori con spedizione **dalla Cina** verso clienti UE: ogni spedizione ≤ €150 paga il dazio forfettario
  (conteggio per articolo/linea tariffaria da verificare). Su prodotti da €1 questo costo supera il prezzo del prodotto.
- Fornitori con **magazzino UE** (BigBuy, magazzini UE di CJ, grossisti europei): nessun dazio sulla vendita
  intra-UE, ma prezzi unitari più alti. Il Supplier Intelligence confronterà le due strade per ciascun prodotto.

## 5. Piano di integrazione proposto (ordine)

1. **Connettore CSV/XML generico** (`csv_feed`) + inserimento **manuale**: costo zero, permette di testare
   tutto il motore con dati reali raccolti legalmente.
2. **CJdropshipping API 2.0**: API ufficiale, account gratuito → primo connettore reale (sola lettura prima,
   ordini solo in Fase 3 con approvazione).
3. **AliExpress Open Platform**: richiesta di accesso quando l'impresa è registrata (l'approvazione può
   richiedere dati aziendali).
4. **BigBuy**: solo se l'operatore approva l'abbonamento (vedi `COST_CONTROL.md`).
5. Grossisti/produttori UE: feed autorizzati caso per caso.

## Fonti consultate

- CJ API 2.0 — Shopping/Order: https://developers.cjdropshipping.com/en/api/api2/api/shopping.html
- CJ — Sincronizzazione ordini: https://developers.cjdropshipping.com/en/api/start/Orders-Synchronization-Processing.html
- CJ — Webhook: https://developers.cjdropshipping.com/en/api/start/webhook.html
- AliExpress SDK (migrazione all'Open Platform internazionale): https://unpkg.com/ae_sdk@0.6.0/README.md
- Guida AliExpress API (secondaria): https://zuplo.com/learning-center/aliexpress-api-guide.md
- BigBuy API (ufficiale): https://www.bigbuy.eu/hr/api_bigbuy.html
- BigBuy prezzi (secondarie, discordanti): https://www.itechguides.com/products/bigbuy/ · https://services.wizishop.com/en/service/bigbuy
- Syncee vs Spocket: https://syncee.com/page/syncee-vs-spocket · https://www.stackscored.com/pricing/dropshipping-suppliers/compare/spocket-vs-syncee/
- Syncee recensioni: https://apps.shopify.com/Syncee-1
