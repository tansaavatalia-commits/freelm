# Registro della ricerca

Ogni voce riporta solo risultati misurati dal Research Lab (`genesis lab …`), con dataset,
versione e hash. Nessun miglioramento è dichiarato senza un confronto appaiato significativo.

## R-001 — 2026-11-24 — Il classificatore a regole contro la baseline di maggioranza

- **Obiettivo:** sapere se il classificatore a regole del router (Fase 3) è meglio di una scelta banale.
- **Ipotesi:** le regole battono la baseline «rispondi sempre chat».
- **Dati:** `classify-it@1` (30 richieste in italiano etichettate per intento; sha256 `e04089e03a99…`).
  Le etichette sono state assegnate per intento, **non** adattate al classificatore.
- **Soggetti:** `baseline:majority` (risponde sempre `chat`) e `classifier` (regole@0.6.0); seed 0.
- **Risultato:** baseline 10/30 (33,3%); regole 27/30 (90,0%). Solo le regole corrette: 17;
  solo la baseline corretta: 0. McNemar esatto p ≈ 1,5·10⁻⁵; IC 95% bootstrap della differenza [0,40; 0,73].
- **Valutazione:** ipotesi **sostenuta dai dati**. Deterministico: riprodotto identico elemento per elemento.
- **Limiti trovati (3 errori, tutti classificati `chat`):**
  1. problemi a parole («Ho 3 mele e ne compro 4…») → atteso `math`;
  2. conteggi impliciti («Quante parole ci sono in questa frase?») → atteso `text.stats`;
  3. domande causali senza parole chiave («qual è la causa principale dell'inflazione?») → atteso `reasoning`.
- **Prossimo passo:** un classificatore migliorato va confrontato con questo sullo **stesso** dataset
  e su un dataset nuovo (per non adattarsi ai 30 esempi). Candidato per le Fasi 7 e 9.

## R-002 — 2026-11-24 — Motore locale e router sui calcoli

- **Dati:** `math-basic@1` (26 elementi; sha256 `714e5b61638c…`).
- **Risultato:** `local.math` 24/26; `router` in modalità privata 24/26 (tutte le risposte dal motore locale).
  I 2 errori sono i problemi a parole: il motore locale non li capisce e il router, senza motore online,
  dichiara «nessun motore disponibile» invece di inventare una risposta.
- **Valutazione:** nessuna differenza dimostrata tra i due (atteso: stesso motore). Le risposte calcolate sono
  esatte; il limite è la comprensione del linguaggio naturale, non l'aritmetica.

## Da misurare quando il motore online sarà attivo sul PC del proprietario

- `qa-facts@1` con `agent:researcher` (max 40 chiamate per esperimento per rispettare la quota gratuita).
- Consiglio contro singolo agente sullo stesso dataset: il Consiglio usa 3 chiamate per domanda, quindi
  conviene un campione di 10–13 elementi per esperimento e più esperimenti con seed diversi.

## R-003 — 2026-11-25 — Classificatore v2 contro v1 su dati pre-registrati

- **Metodo:** `classify-holdout@1` (40 richieste, 8 per categoria; sha256 `ef006e8e0f69…`) è stato
  committato **prima** di scrivere la v2 (commit `a8fb109`). La v2 corregge i 3 limiti trovati in R-001.
- **Risultati:**

  | Dataset | v1 | v2 |
  |---|---|---|
  | `classify-it@1` | 27/30 | 29/30 |
  | `classify-holdout@1` | 17/40 | 39/40 |

  Sul holdout: McNemar esatto p < 0,001, differenza dimostrata.
- **Scoperta importante:** la v1 generalizzava male (90% sui dati originali, 42,5% su dati nuovi).
- **Errori nuovi della v2, NON corretti** (correggerli dopo averli visti vorrebbe dire adattarsi alla prova):
  «le **api** sono importanti» → `code` (api = insetti); «query SQL per **contare le righe**» → `text.stats`.
- **Limite metodologico dichiarato:** le regole v2 sono state scritte dallo stesso autore che ha scritto e
  letto il holdout. La pre-registrazione dimostra che i dati non sono stati cambiati, **non** che la valutazione
  sia alla cieca. Per una prova indipendente serve un dataset scritto dal proprietario
  (`genesis lab import file.json`). La v2 resta **sperimentale** finché non passa il ciclo della Fase 9.

## R-004 — 2026-11-25 — Calcolo v2 (aritmetica a parole e problemi) contro v1

- **Dati:** `math-basic@1` e `math-words@1` (20 problemi pre-registrati, sha256 `8b48daf18493…`).
- **Risultati:** `math-basic@1` 24/26 → 26/26; `math-words@1` 0/20 → 20/20.
- **Stesso limite di R-003:** il risolutore è stato scritto dopo aver letto i problemi pre-registrati.
  È un risolutore a un passo con parole indizio: problemi con tre numeri o due passaggi vengono rifiutati
  («problema non riconosciuto») invece di dare una risposta inventata.
