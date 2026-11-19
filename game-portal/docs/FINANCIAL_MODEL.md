# GAME PORTAL — Modello finanziario (v2 — modello ibrido, D-015)

> **Tutti i parametri sono [IPOTESI].** Il portale non ha traffico né ricavi: nessun numero
> qui è un risultato. Lo scopo è rendere **misurabile** quando i 3.000 € di utile netto
> mensile diventano realistici. Calcolo riproducibile:
> `python3 game-portal/scripts/financial_model.py [--target 3000]`.

## Formule
```
impression          = visitatori × sessioni/visitatore × pagine/sessione × slot/pagina
ricavi_ads          = impression × sell_through / 1000 × CPM_diretto
ricavi_rete         = impression × (1 − sell_through) × fill_rete / 1000 × CPM_rete_netto   (D-015)
ricavi_premium      = visitatori × conversione × prezzo / (1 + IVA) × (1 − fee_incasso)
ricavi_sponsor      = min(max_sponsor, ⌊visitatori / visitatori_per_sponsor⌋) × valore_medio
costi               = contributi + commercialista + dominio + infrastruttura + licenze
imposte             = ricavi × aliquota_effettiva        (paušalni: da verificare)
utile_netto         = ricavi − costi − imposte
```
"Visitatori" = visitatori unici mensili. Il fatturato **non** è denaro netto disponibile.

## Parametri comuni
| Parametro | Valore | Natura |
|---|---|---|
| Sessioni / visitatore / mese | 1,6 | [IPOTESI] |
| Pagine / sessione | 3,0 | [IPOTESI] |
| Slot pubblicitari / pagina | 1,5 | scelta di prodotto |
| IVA su Premium | 25 % (HR); aliquota del paese cliente oltre 10.000 € B2C UE | [UFF da verificare] |
| Fee di incasso Premium | 4 % | [IPOTESI] |
| Contributi obrt paušalni | 295 €/mese (fonti: 290,98–298,98) | [TERZI] |
| Commercialista | 80 €/mese | [IPOTESI] |
| Dominio | 15 €/anno | [IPOTESI] |
| Workers Paid | 5 $/mese oltre 100k richieste/giorno (12 richieste API per visitatore) | [TERZI]/[IPOTESI] |

## Scenari
| Parametro | Prudente | Intermedio | Ambizioso | Stress |
|---|---|---|---|---|
| CPM rete netto all'editore, già ridotto per mancato consenso (€) | 0,8 | 1,5 | 2,5 | 0,5 |
| Fill della rete sull'invenduto | 70 % | 80 % | 90 % | 50 % |
| CPM diretto (€) | 1,5 | 3,0 | 6,0 | 1,0 |
| (riferimento [TERZI]: display web 2,5–4,5 $; mediana programmatica 4,2 $) | | | | |
| Sell-through | 15 % | 35 % | 60 % | 5 % |
| Sponsor max / visitatori per sponsor | 2 / 200k | 4 / 75k | 8 / 40k | 0 |
| Valore sponsor (€/mese) | 200 | 400 | 800 | — |
| Conversione Premium | 0,02 % | 0,08 % | 0,20 % | 0,01 % |
| Prezzo Premium (IVA incl.) | 3,99 € | 3,99 € | 4,99 € | 2,99 € |
| Licenze (€/mese) | 0 | 100 | 300 | 200 |
| Aliquota imposte effettiva | 6 % | 5 % | 4 % | 8 % |

## Risultati v2 — modello ibrido (output reale, 2026-11-19)
```
scenario    visitatori/mese   impression  diretta    rete  premium  sponsor   ricavi   costi  imposte   utile
prudente            564,773    4,066,363      915   1,936      346      400    3,597     381      216   3,000
intermedio          182,961    1,317,317    1,383   1,028      449      800    3,659     476      183   3,000
ambizioso            75,613      544,417    1,960     490      580      800    3,829     676      153   3,000
stress            1,692,544   12,186,317      609   2,894      389        0    3,892     581      311   3,000

Pareggio: prudente 70,718 / intermedio 32,079 / ambizioso 17,582 / stress 274,548 visitatori/mese
Sensibilità (intermedio): 50k -> utile 266 € · 100k -> 1.388 € · 250k -> 4.375 €
```
**Valore reale della rete:** il modello assume per semplicità che il sell-through diretto
esista dal primo giorno, ma in pratica nei primi 6–18 mesi sarà vicino a 0. In quel periodo
la rete è **l'unica fonte di ricavo pubblicitario**: con la sola vendita diretta i ricavi
reali iniziali sarebbero ~0 €. Confronto: `--no-network` riproduce il modello v1.

## Risultati v1 — solo vendita diretta (`--no-network`)
v1: conversione Premium ridotta dopo la FASE 1 (siti di solitario indipendenti dichiarano
ricavi da abbonamento trascurabili rispetto alla pubblicità).
```
scenario    visitatori/mese   impression      ads  premium  sponsor   ricavi   costi  imposte   utile
prudente          1,431,636   10,307,781    2,319      877      400    3,597     381      216   3,000
intermedio          245,640    1,768,605    1,857      602    1,200    3,659     476      183   3,000
ambizioso            80,000      576,000    2,074      613    1,600    4,287     676      171   3,439
stress            6,601,114   47,528,023    2,376    1,516        0    3,892     581      311   3,000

Pareggio: prudente 179,261 / intermedio 50,074 / ambizioso 20,975 / stress 1,070,767 visitatori/mese

Sensibilità (intermedio):
     10,000 visitatori -> ricavi      100  utile     -381 EUR
     50,000 visitatori -> ricavi      501  utile       -1 EUR
    100,000 visitatori -> ricavi    1,401  utile      855 EUR
    250,000 visitatori -> ricavi    3,703  utile    3,041 EUR
```
Nota: nello scenario ambizioso a 80.000 visitatori scatta il secondo sponsor (gradino),
per questo l'utile supera l'obiettivo.

v0 (FASE 0, conversione Premium più alta) richiedeva 62k / 171k / 682k / 2,58 M visitatori.

## Interpretazione
- **Traffico richiesto per i 3.000 € netti (v2 ibrido): da ~76.000 a ~565.000 visitatori/mese**
  (~183.000 nell'intermedio); stress test ~1,7 milioni. Solo vendita diretta (v1): ~246.000 nell'intermedio.
- La voce più incerta è il **CPM diretto con sell-through**: un piccolo sito che vende
  da solo i propri spazi raramente riempie l'inventario. Va misurato, non assunto.
- Premium "pesa" molto nel modello ma richiede un sistema di incasso (vedi D-006):
  **fino ad allora va considerato 0**.
- Il regime paušalni ha un tetto di **60.000 €/anno di ricavi** [TERZI]: 3.000 € netti
  (~3.600–3.900 € di ricavi/mese, cioè ~43.000–47.000 €/anno) ci rientrano, ma il margine è
  stretto. Oltre serve un altro regime (contabilità ordinaria o d.o.o.).
- La forma giuridica cambia le imposte: in un d.o.o. l'"utile netto aziendale" è dopo
  l'imposta sugli utili, e la distribuzione al socio è tassata a parte. Da verificare col commercialista.

## Validazione (FASE 1 e FASE 12)
Ogni parametro sarà sostituito da: (1) benchmark pubblici con fonte classificata in
FASE 1; (2) dati misurati dal sistema analytics proprio dopo il lancio. Il modello va
rieseguito ogni mese con i dati reali, registrando le differenze in `CHANGELOG.md`.
