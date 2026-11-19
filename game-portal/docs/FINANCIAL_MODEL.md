# GAME PORTAL — Modello finanziario (v0, FASE 0)

> **Tutti i parametri sono [IPOTESI].** Il portale non ha traffico né ricavi: nessun numero
> qui è un risultato. Lo scopo è rendere **misurabile** quando i 3.000 € di utile netto
> mensile diventano realistici. Calcolo riproducibile:
> `python3 game-portal/scripts/financial_model.py [--target 3000]`.

## Formule
```
impression          = visitatori × sessioni/visitatore × pagine/sessione × slot/pagina
ricavi_ads          = impression × sell_through / 1000 × CPM_diretto
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
| CPM diretto (€) | 1,5 | 3,0 | 6,0 | 1,0 |
| Sell-through | 15 % | 35 % | 60 % | 5 % |
| Sponsor max / visitatori per sponsor | 2 / 200k | 4 / 75k | 8 / 40k | 0 |
| Valore sponsor (€/mese) | 200 | 400 | 800 | — |
| Conversione Premium | 0,10 % | 0,30 % | 0,60 % | 0,05 % |
| Prezzo Premium (IVA incl.) | 3,99 € | 3,99 € | 4,99 € | 2,99 € |
| Licenze (€/mese) | 0 | 100 | 300 | 200 |
| Aliquota imposte effettiva | 6 % | 5 % | 4 % | 8 % |

## Risultati (output reale dello script, 2026-11-19)
```
scenario    visitatori/mese   impression      ads  premium  sponsor   ricavi   costi  imposte   utile
prudente            682,415    4,913,386    1,106    2,091      400    3,597     381      216   3,000
intermedio          170,669    1,228,817    1,290    1,569      800    3,659     476      183   3,000
ambizioso            61,934      445,924    1,605    1,424      800    3,829     676      153   3,000
stress            2,580,779   18,581,612      929    2,963        0    3,892     581      311   3,000

Pareggio (utile = 0):
  prudente    85,448 / intermedio 29,924 / ambizioso 14,401 / stress 418,628 visitatori/mese

Sensibilità (intermedio):
     10,000 visitatori -> ricavi      168  utile     -317 EUR
     50,000 visitatori -> ricavi      838  utile      320 EUR
    100,000 visitatori -> ricavi    2,075  utile    1,495 EUR
    250,000 visitatori -> ricavi    5,388  utile    4,643 EUR
```

## Interpretazione
- **Traffico richiesto per i 3.000 € netti: da ~60.000 a ~700.000 visitatori/mese**
  secondo lo scenario; nello stress test oltre 2,5 milioni.
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
