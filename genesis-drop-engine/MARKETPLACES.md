# MARKETPLACES — Ricerca canali di vendita (Europa)

Ricerca di Fase 1 (data: 2026-11-20). **Nessun account creato o attivato.**
eBay è **escluso permanentemente** (BR-050). Il paese di registrazione dell'impresa non è deciso:
l'idoneità finale dipende da questa scelta.

## 1. Tabella comparativa

| Canale | API | Costi noti | Pagamenti / payout | Dropshipping | Idoneità e obblighi | Valutazione |
|--------|-----|-----------|--------------------|--------------|---------------------|-------------|
| **Allegro** (PL, CZ, SK, HU…) | REST ufficiale (OAuth 2.0, JSON), **sandbox** disponibile | Nessun abbonamento/listing fee nella maggior parte delle categorie per venditori internazionali; commissioni ~5–22% per categoria *(da verificare)* | Ciclo payout *(da verificare)* | Diffuso; segnalate nuove regole di fatturazione in Polonia che potrebbero limitarlo *(da verificare: obbligo e-fattura KSeF)* | Venditori esteri ammessi; prezzi bassi tipici del mercato | **Candidato primario** |
| **Kaufland Global Marketplace** (DE, CZ, SK, PL, AT, IT, FR…) | Seller API ufficiale | Canone mensile + commissione ~6–16% per categoria *(cifre discordanti, da verificare)* | *(da verificare)* | Ammesso con identificazione del venditore *(da verificare)* | Commerciante registrato; extra-UE: registrazione IVA in ogni paese; EPR (imballaggi, RAEE) per paese; possibili indirizzo resi UE e GTIN obbligatori *(da verificare)* | **Candidato secondario** |
| **Amazon Europe** | SP-API ufficiale | Piano Professional mensile + commissioni di categoria *(da verificare)* | Payout periodico con riserve per nuovi account *(da verificare)* | Ammesso **solo** se il venditore è chiaramente il "seller of record": nessun riferimento a terzi su bolle, fatture, imballi; fornitore che accetta i resi | Policy rigide, rischio sospensione alto per dropshipping da Cina | Fase successiva, dopo storico e fornitore conforme |
| **Cdiscount** (Octopia) | REST Octopia (SOAP dismesso 31/03/2025) | €39,99/mese + commissioni per categoria | Bonifico al netto commissioni | *(da verificare)* | Mercato francese; idoneità venditori esteri *(da verificare)* | Fase successiva |
| **WooCommerce** (negozio proprio) | REST ufficiale | Software gratuito; hosting, dominio, pagamenti (Stripe/PayPal) a carico | Dipende dal PSP (attese iniziali possibili) | Libero (sotto la propria responsabilità legale) | Tutti gli obblighi consumatore UE ricadono sul venditore; richiede traffico → **costo pubblicità** | Canale proprio a medio termine |
| **Shopify** | API ufficiale | Abbonamento mensile | Shopify Payments | Libero | Come WooCommerce | Scartato inizialmente (costo fisso; WooCommerce è gratuito) |

## 2. Raccomandazione iniziale (provvisoria)

1. **Allegro** come primo canale: API REST con sandbox (sviluppo e test a costo zero), assenza di canone,
   mercato orientato al prezzo coerente con prodotti economici. Da verificare: payout, regole di fatturazione
   polacche, requisiti per il paese di registrazione scelto.
2. **Kaufland** come secondo canale: mercato tedesco ampio, API ufficiale; da valutare il canone rispetto ai volumi.
3. **Amazon** solo dopo aver dimostrato un fornitore conforme alla policy "seller of record".
4. **WooCommerce** quando esiste un budget pubblicitario approvato.

Questa raccomandazione **non è definitiva**: richiede le decisioni D-002 (paese di registrazione) e la verifica
delle condizioni ufficiali in Fase 3.

## 3. Requisiti trasversali UE (qualunque canale)

- **GPSR** (Reg. (UE) 2023/988, in applicazione dal 13/12/2024): per prodotti di fabbricanti extra-UE serve un
  operatore economico responsabile stabilito nell'UE; nome e contatti devono essere sul prodotto/imballo o
  documento e visibili nell'offerta online prima dell'acquisto.
- **IVA**: OSS/IOSS o registrazioni nazionali a seconda della struttura; marketplace come "fornitore presunto"
  per alcune vendite B2C ≤ €150 da extra-UE.
- **EPR**: registrazioni imballaggi/RAEE/batterie per paese (es. LUCID in Germania).
- **Diritti del consumatore**: recesso 14 giorni, garanzia legale, informazioni precontrattuali.

## 4. Requisiti per il Marketplace Command Center

Ogni canale è un connettore indipendente con circuit breaker: il guasto di un canale non blocca gli altri.
Prima dell'attivazione reale: verifica idoneità, policy, fee, permessi API, ciclo di payout (input del
Cashflow Guardian).

## Fonti consultate

- Allegro Developer: https://developer.allegro.pl/about · https://developer.allegro.pl/news/gotowosc-integracji-na-uruchomienie-zagranicznych-serwisow-allegro-integration-readiness-for-the-launch-of-foreign-allegro-marketplaces-2YnKeXkEYUR
- Allegro (secondarie): https://www.zunapro.com/europa/en/marketplace/allegro-eu · https://antyweb.pl/pakiet-ecommerce-vat-allegro
- Kaufland registrazione: https://www.kauflandglobalmarketplace.com/en/seller-registration/
- Kaufland registrazione IVA per paese: https://www.kauflandglobalmarketplace.com/en/seller-university/formal-framework/tax-registration/
- Kaufland IVA 2021: https://www.kauflandglobalmarketplace.com/en/seller-university/formal-framework/infopage-eu-vat-regulation-2021/
- Amazon dropshipping (secondarie): https://www.sellersprite.com/en/blog/amazon-dropshipping-policy · https://casrai.org/guides/amazon-dropshipping-policy
- Cdiscount/Octopia: https://marketplace.cdiscount.com/?p=2752 · https://support.channelengine.com/hc/en-us/articles/21087078328861 · https://help.lengow.com/hc/en-us/articles/20226316694556--Cdiscount-Octopia-Migrating-Offer-Order-Feeds-to-the-REST-API
- GPSR: https://ecommercegermany.com/blog/gpsr-general-product-safety-regulation/ · https://webgate.ec.europa.eu/safety/consumers/consumers_safety_gate/obligationsForBusinesses/documents/GPSR-Presentation-E-Academy.pdf · https://www.bakermckenzie.com/en/insight/publications/resources/product-risk-radar-articles/general-product-safety-regulation
- Dazio €3: https://taxation-customs.ec.europa.eu/news/guidance-and-legal-text-temporary-flat-fee-low-value-imports-which-will-apply-until-1-july-2028-2026-06-08_en · https://globalimportblog.bakermckenzie.com/2026/07/02/eu-low-value-consignment-relief-abolished-and-eur-3-customs-duty-introduced-from-1-july-2026/ · https://gerlach-customs.com/?p=136126
