# Tabluo — Come andare online (beta pubblica a 0 €)

**Perché è urgente:** il traffico di un sito come questo arriva soprattutto da Google, e
Google impiega mesi a fidarsi di un sito nuovo. **Il conto alla rovescia parte solo quando il
sito è online e indicizzato.** Ogni settimana offline sposta in avanti i primi ricavi.

## Cosa serve da te (≈ 20 minuti, tutto gratuito)

| # | Azione | Tempo | Costo | Perché solo tu |
|---|---|---|---|---|
| 1 | Crea il repository GitHub **privato e vuoto** `game-portal` e dimmi il nome | 2 min | 0 € | È il tuo account |
| 2 | Crea un account **Cloudflare** gratuito (cloudflare.com → Sign up) con la tua email | 5 min | 0 € | Accettare i termini spetta a te |
| 3 | In Cloudflare crea un **API token** (My Profile → API Tokens → Create Token → modello "Edit Cloudflare Workers", aggiungi i permessi *D1: Edit* e *Cloudflare Pages: Edit*) | 5 min | 0 € | Il token si inserisce in un modulo sicuro della sessione: **non incollarlo mai in chat** |
| 4 | Scrivimi: **"autorizzo la beta pubblica"** | 1 min | 0 € | Pubblicare richiede la tua autorizzazione (vincolo 8) |

## Cosa faccio io subito dopo
1. Sposto il progetto nel repository dedicato, con tutta la storia (vedi MIGRATION.md).
2. Creo database D1, API Worker e i due siti Pages (portale + giochi) sul tuo account.
3. Pubblico su indirizzi gratuiti: `tabluo.pages.dev` (portale) e `tabluo-play.pages.dev` (giochi).
4. Rilancio tutti i test sul sito vero e ti mando il link.

## Cosa NON succede nella beta
- **Nessuna pubblicità e nessun incasso**: richiedono il soggetto fiscale (obrt) e l'account presso la rete pubblicitaria, entrambi con tua autorizzazione separata.
- Nessun account utente e nessun dato personale raccolto: solo statistiche anonime aggregate.
- Nessun dominio acquistato: `tabluo.com` (~10–15 €/anno) si aggiunge dopo, senza perdere nulla.

## Rischi della beta (da conoscere prima di autorizzare)
- Privacy e termini sono **bozze**. La beta non usa cookie né raccoglie dati personali, quindi il
  rischio è basso, ma la revisione di un legale resta consigliata prima della monetizzazione (D-009).
- Il nome "Tabluo" non è ancora verificato nelle banche dati dei marchi (verifica gratuita su TMview da fare prima del dominio).
