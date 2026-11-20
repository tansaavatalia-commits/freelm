# BUSINESS_RULES — Regole di business vincolanti

Queste regole sono **vincoli applicati dal sistema** (codice + database), non suggerimenti.
Ogni regola ha un identificativo stabile (`BR-xxx`) usato nel codice, nei test e nei log di audit.
I valori numerici sono parametri versionati (`rule_set_version`): cambiarli richiede
un'approvazione esplicita dell'operatore e genera una voce di audit.

---

## 1. Acquisizione prodotto

| ID | Regola | Applicazione |
|----|--------|--------------|
| BR-001 | Prezzo d'acquisto fornitore ≤ **€1,00 per unità**, escluse spedizione e altri costi | Gate `ACQUISITION_CAP` nel passaggio a `PROFIT VERIFIED` |
| BR-002 | Prodotti oltre il limite possono essere **scoperti e analizzati** (ricerca) ma non diventare `ELIGIBLE` | Flag `research_only=true`; sblocco solo con `Approval(type=ACQUISITION_CAP_EXCEPTION)` firmata dall'operatore |
| BR-003 | Prezzo di rivendita obiettivo **€6–7 o più per unità** | Parametro di pricing; non è un vincolo di blocco, è un obiettivo dell'ottimizzatore |
| BR-004 | Un prezzo basso **non implica** redditività: spedizione e costi sono sempre calcolati a parte | Il Profit Engine rifiuta calcoli con componenti di costo mancanti (`status=INCOMPLETE`) |
| BR-005 | Prezzi in valuta estera convertiti con tasso registrato (fonte + timestamp) e **margine di cambio prudenziale** (default 3%) | Il limite €1,00 si verifica sul valore convertito *con* margine |

## 2. Profitto minimo

| ID | Regola |
|----|--------|
| BR-010 | Profitto operativo netto minimo **€3,00 per unità** |
| BR-011 | Multipack: minimo = €3,00 × numero di unità (1→€3, 3→€9, 5→€15, 10→€30) |
| BR-012 | Il sistema confronta sempre configurazioni singola e multipack (default: 1, 2, 3, 5, 10) |
| BR-013 | La configurazione scelta massimizza il **risultato commerciale realistico atteso** (profitto × probabilità di conversione stimata, penalizzato per resi, concorrenza e incertezza dei dati), non il margine teorico |
| BR-014 | Il controllo del minimo usa lo **scenario prudenziale** (vedi §4), non quello centrale |

## 3. Definizioni contabili (devono restare distinte ovunque)

| Grandezza | Definizione |
|-----------|-------------|
| **Ricavo lordo** | Prezzo pagato dal cliente, IVA inclusa, spedizione addebitata inclusa |
| **Ricavo netto IVA** | Ricavo lordo − IVA dovuta (aliquota del paese di destinazione) |
| **Margine lordo** | Ricavo netto IVA − costo prodotto − spedizione fornitore − dazi/oneri import |
| **Margine di contribuzione** | Margine lordo − commissioni marketplace − commissioni di pagamento − spedizione cliente − imballaggio/fulfillment − accantonamenti resi/rimborsi/chargeback |
| **Profitto operativo netto** | Margine di contribuzione − costo di acquisizione cliente (pubblicità) − altri costi variabili allocati |
| **Profitto contabile/fiscale finale** | **Non calcolabile** finché paese di registrazione e struttura fiscale non sono definiti. Il sistema mostra la dicitura "non certificato" |

Ogni valore porta uno stato di verifica: `VERIFIED` (da fonte ufficiale/API con timestamp),
`ESTIMATED` (stima con metodo dichiarato), `UNVERIFIED` (dato non confermato), `MISSING`.
**Una stima non viene mai presentata come risultato verificato.**

## 4. Formula del Profit Engine

Per una configurazione `c` (prodotto, fornitore, multipack `n`, paese di destinazione, canale, prezzo `P` IVA inclusa):

```
ricavo_netto_iva   = P / (1 + iva_paese)
costo_prodotto     = n × prezzo_unitario_fornitore × (1 + margine_cambio)
spedizione_fornit  = quota spedizione (fornitore → cliente o → magazzino)
dazi_import        = f(regime doganale, valore, linee tariffarie)     # vedi §6
commissione_mkt    = P × aliquota_categoria (+ quota fissa)            # base dichiarata per canale
commissione_pag    = % + fisso (se non inclusa nella commissione marketplace)
imballaggio        = costo dichiarato
accantonamento_resi= P × tasso_resi_atteso × costo_medio_reso
accant_chargeback  = P × tasso_chargeback
cac                = costo pubblicitario per ordine (0 solo se dichiarato e giustificato)

profitto_netto = ricavo_netto_iva − Σ costi
profitto_per_unita = profitto_netto / n
```

**Analisi di sensibilità obbligatoria:** ogni costo incerto ha intervallo `[ottimistico, centrale, prudenziale]`.
Il sistema calcola i tre scenari; **il gate BR-010 usa il prudenziale**. Se un costo è `MISSING`,
il calcolo è `INCOMPLETE` e il prodotto non può avanzare.

Ogni calcolo è salvato come **snapshot immutabile** (input, versione regole, versione formula,
risultato, fonti), così è sempre riproducibile e verificabile.

## 5. Esempio illustrativo — analisi di fattibilità (NON dati verificati)

> Tutti i numeri sotto sono **ipotesi** per testare la logica, non quotazioni reali.
> Servono a evidenziare un rischio strutturale da discutere prima della Fase 2.

Ipotesi: vendita in Italia (IVA 22%), commissione marketplace 15% sul lordo, accantonamento
resi 5%, prodotto €1,00, spedizione Cina→Italia €2,50 per pacco, **dazio forfettario UE €3,00**
(vedi §6), pubblicità €0 (vendita organica).

**Singola unità a €6,99:**

| Voce | € |
|------|---|
| Ricavo lordo | 6,99 |
| IVA 22% | −1,26 |
| Ricavo netto IVA | 5,73 |
| Prodotto | −1,00 |
| Spedizione | −2,50 |
| Dazio UE | −3,00 |
| Commissione 15% | −1,05 |
| Accantonamento resi 5% | −0,35 |
| **Profitto netto** | **−2,17** |

Con queste ipotesi, per ottenere €3 di profitto su una singola unità servirebbe un prezzo di circa **€15,33**.

**Multipack da 5 unità in un solo pacco (spedizione €3,50):**

| Interpretazione dazio | Dazio | Prezzo minimo per €15 di profitto | Prezzo per unità |
|-----------------------|-------|-----------------------------------|------------------|
| €3 per linea tariffaria (stesso prodotto = 1 linea) | €3 | ≈ €42,76 | ≈ €8,55 |
| €3 per singolo pezzo (scenario pessimistico) | €15 | ≈ €62,13 | ≈ €12,43 |

**Conclusione provvisoria (da validare con dati reali in Fase 2):** con prodotti spediti dalla Cina
verso l'UE, la singola unità a €6–7 con €3 di profitto netto è quasi certamente irrealizzabile dal
1° luglio 2026. I multipack, i fornitori con magazzino UE (senza dazio) e i paesi a IVA più bassa sono
le leve principali. **Questo è un punto che richiede una decisione dell'operatore** (vedi `DECISIONS.md`, D-010).

## 6. Dazi e IVA all'importazione (contesto normativo da verificare in Fase 2)

- Dal **1° luglio 2026** l'UE ha abolito l'esenzione dai dazi per spedizioni B2C extra-UE ≤ €150 e
  applica un **dazio temporaneo forfettario di €3** (Reg. (UE) 2026/382, fino al 1° luglio 2028).
  Le fonti divergono sul conteggio: "per articolo" secondo la guida della Commissione, mentre alcune
  fonti specialistiche lo descrivono come "per linea tariffaria/codice HS" nel pacco. Il sistema
  modella **entrambe le interpretazioni** e usa la più prudente finché non è verificata.
- Possibile ulteriore **diritto di gestione** UE per piccole spedizioni: tempistica incerta → parametro
  `handling_fee`, default prudenziale configurabile.
- IVA: regime IOSS / "fornitore presunto" (deemed supplier) del marketplace per vendite ≤ €150 da
  extra-UE. Il motore non deve contare l'IVA due volte (marketplace che la riscuote vs. venditore).
- Il regime effettivo dipende dal **paese di registrazione dell'impresa** (non ancora deciso).

## 7. Politica ZERO-ADVANCE (capitale personale zero di default)

### 7.1 Stati del denaro (mai confondibili)

```
AUTHORIZED → CAPTURED → MARKETPLACE_HELD → PAYOUT_SCHEDULED → PAYOUT_IN_TRANSIT → AVAILABLE
```

Solo `AVAILABLE` (fondi confermati sul conto dell'impresa) conta come liquidità utilizzabile.

### 7.2 Liquidità utilizzabile

```
liquidità_utilizzabile = saldo_AVAILABLE
                       − riserva_rimborsi − riserva_chargeback − riserva_IVA
                       − obblighi_fornitori_già_impegnati
                       − margine_di_sicurezza (parametro)
```

Le riserve sono parametri con minimo configurabile (default proposti: rimborsi = 10% del fatturato
degli ultimi 30 giorni non ancora fuori finestra resi; chargeback = 1%; IVA = 100% dell'IVA maturata
non versata, se il venditore è il soggetto debitore).

### 7.3 Algoritmo di autorizzazione ordine fornitore (BR-030)

Per ogni ordine cliente, prima di qualsiasi ordine al fornitore:

1. Verifica fondi disponibili (`AVAILABLE`, non stimati).
2. Verifica stato del payout del marketplace per quell'ordine.
3. Verifica scadenza di pagamento del fornitore (prepagato / a termine N giorni / credito).
4. Verifica che le riserve restino sopra il minimo dopo il pagamento.
5. Ricalcola la redditività con prezzi e spedizione **attuali** (BR-010 deve ancora valere).
6. Se i fondi non bastano o le condizioni di pagamento sono incompatibili:
   a. cerca fornitori alternativi **verificati** per lo stesso prodotto/variante;
   b. confronta costo totale, consegna, affidabilità e termini di pagamento;
   c. seleziona l'alternativa automaticamente **solo se** profitto minimo, conformità e liquidità
      restano soddisfatti **e** il livello di automazione lo consente;
   d. altrimenti **blocca** l'ordine (`FUNDING_BLOCKED`) e notifica l'operatore.

Esiti possibili (`FundingDecision`): `APPROVED_FUNDED`, `APPROVED_SUPPLIER_TERMS`,
`SWITCHED_SUPPLIER`, `BLOCKED_INSUFFICIENT_FUNDS`, `BLOCKED_PROFIT`, `BLOCKED_COMPLIANCE`,
`PENDING_OPERATOR`.

### 7.4 Divieti assoluti (BR-031…BR-036)

- Nessun uso di denaro personale senza approvazione esplicita e registrata.
- Nessun anticipo non autorizzato, nessun prestito automatico, nessun credito presunto.
- Termini di pagamento differito/credito del fornitore sono validi **solo se verificati** (documento
  o API) e registrati con data e fonte.
- Nessun ordine che non possa essere finanziato in modo sicuro.
- Nessuna automazione può aggirare questi controlli (il controllo è nel servizio di dominio, non nell'interfaccia).

### 7.5 Conflitto strutturale da conoscere subito

I marketplace trattengono i fondi (cicli di payout tipici: da pochi giorni a settimane, con riserve per
venditori nuovi), mentre molti fornitori dropshipping (es. CJdropshipping) richiedono **pagamento
anticipato dal saldo**. Con capitale zero, **i primi ordini verranno bloccati** finché non esiste un
saldo disponibile o un fornitore con termini compatibili verificati. È il comportamento corretto
secondo le regole, ma ha un impatto commerciale: decisione dell'operatore D-011.

## 8. Opportunity Score (0–100)

| Componente | Punti | Base del calcolo |
|------------|-------|------------------|
| Redditività | 30 | Profitto per unità nello scenario prudenziale rispetto al minimo (€3 → 0 pt aggiuntivi oltre la soglia di ammissione; scala lineare fino a un tetto configurabile) |
| Domanda e trend | 25 | Segnali misurati (fonti autorizzate) su finestre 30/90/365 giorni; nessun volume di vendita inventato |
| Concorrenza | 10 | Numero e qualità delle offerte concorrenti per destinazione/canale |
| Affidabilità fornitore | 15 | Storico consegne, stock, tracking, resi, verifiche |
| Logistica | 10 | Tempi di consegna, origine magazzino, copertura destinazione |
| Affidabilità dei dati | 10 | Quota di input `VERIFIED` vs `ESTIMATED`/`UNVERIFIED` |

Interpretazione: 80–100 alta priorità · 65–79 promettente · 50–64 da approfondire · <50 bassa priorità.

**Filtri rigidi non compensabili:** conformità (Compliance Engine) e liquidità (Zero-Advance).
Un punteggio alto non può mai sbloccare un prodotto non conforme o un ordine non finanziabile.
Il punteggio memorizza il dettaglio di ogni componente (trasparenza e audit).

## 9. Conformità (filtro rigido)

Un prodotto non può raggiungere `READY FOR APPROVAL` se esiste anche un solo controllo
`FAILED` o `UNRESOLVED`. Categorie bloccate o con verifica obbligatoria: contraffazione, proprietà
intellettuale, merci pericolose, batterie al litio, elettrico/elettronico (CE, RoHS, RAEE),
giocattoli e prodotti per bambini (EN 71), cosmetici (Reg. 1223/2009, persona responsabile UE),
prodotti a contatto con alimenti, dispositivi medici e integratori, imballaggi (EPR per paese).
Requisito trasversale GPSR (Reg. (UE) 2023/988): operatore economico responsabile stabilito nell'UE e
relative informazioni visibili prima dell'acquisto. Il sistema **non fornisce certezza legale**: segnala
ciò che manca e blocca.

## 10. Altre regole

| ID | Regola |
|----|--------|
| BR-050 | eBay è escluso in modo permanente (il connettore non esiste e non può essere registrato) |
| BR-051 | Nessuno scraping non autorizzato, nessun aggiramento di restrizioni di accesso |
| BR-052 | Nessuna attivazione di abbonamenti, API o servizi a pagamento senza approvazione esplicita |
| BR-053 | Nessuna pubblicazione esterna (listing, prezzi, messaggi) senza autorizzazione secondo il livello di automazione |
| BR-054 | Nessun uso di account di terzi né aggiramento dei requisiti di idoneità dei marketplace |
| BR-055 | Contenuti dei listing senza affermazioni non supportate (claim verificati o assenti) |
| BR-056 | Livello di automazione iniziale: **LEVEL 1** (ricerca e raccomandazioni); innalzamento solo con approvazione |
