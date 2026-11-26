# Ricerca: Claude, ChatGPT, DeepSeek, Gemini, Perplexity, Grok — e cosa può fare meglio GÉNESIS

- **Data:** 2026-11-26 · richiesta del proprietario: «esamina ogni dettaglio dei più usati; non copiarli,
  creare una versione migliore e più potente; obiettivo: superare il livello di Claude Max».
- **Fonti:** ricerca web del 2026-11-26 (elenco in fondo). Le guide di terze parti si contraddicono spesso su
  prezzi e nomi dei modelli: i dettagli marcati NON VERIFICATO vanno ricontrollati sulle pagine ufficiali.

## 1. Cosa offrono oggi (novembre 2026)

| Funzione | Claude (Max) | ChatGPT (Pro) | DeepSeek | Gemini (Ultra) | Perplexity | Grok | **GÉNESIS oggi** |
|---|---|---|---|---|---|---|---|
| Prezzo | 100–200 $/mese | fascia alta (NON VERIFICATO) | chat gratuita | 99,99–199,99 $/mese | 20–200 $/mese | 0–200 $/mese | **0 €** |
| Chat a turni con cronologia | sì | sì | sì | sì | sì | sì | **no** (richieste singole agli agenti) |
| Risposta che scorre mentre viene scritta | sì | sì | sì | sì | sì | sì | **no** |
| Modello di punta | modelli Claude, anche Fable | serie GPT più recente | V4 / V4.1-Flash (pesi MIT) | Gemini più recente | più modelli in un piano | Grok | motori locali + online gratuito **spento** |
| Ragionamento esteso | sì | «pro reasoning» | 3 livelli di pensiero (V4) | sì | dipende dal modello | sì | Reasoning Engine a regole |
| Memoria tra conversazioni | sì | sì, raddoppiata a giugno 2026 | limitata | sì | limitata | sì | **Memory Engine esiste**, non collegato a una chat |
| Progetti con istruzioni e file | sì | sì, con memoria separata | no | Gems | Spaces | sì | progetti senza istruzioni né file |
| Ricerca approfondita con fonti | sì | ~250 al mese (NON VERIFICATO), domini scelti, MCP | ricerca web | sì | **punto di forza** (fonti trasparenti) | dati di X | `web.fetch` (spento), nessun motore di ricerca |
| Agente che usa il computer / il browser | sì | modalità agente, «Dot» sempre attivo | no | sì | sì | — | no |
| Codice eseguito / anteprime | Artifacts, Claude Code | Canvas, Codex | — | Canvas | — | — | no |
| File e documenti caricati | sì | sì | sì | sì, 1M di contesto | sì | sì | strumenti file nella sandbox, nessun caricamento dall'interfaccia |
| Voce | sì | sì | sì | sì | sì | sì | no |
| Immagini generate | no (le analizza) | sì, illimitate su Pro | no | sì | sì | sì | **no** |
| Compiti pianificati / lavoro autonomo | routine | «Pulse» quotidiano, attività | no | sì | — | — | coda dei compiti, nessuna pianificazione |
| Connettori (Gmail, Drive, …) / MCP | sì | sì | no | Google Workspace | sì | X | client MCP (nessun server configurato) |
| I dati restano sul tuo PC | no | no | no | no | no | no | **sì** |
| Ogni passo spiegato e registrato | parziale | parziale | parziale | parziale | fonti | no | **sì: audit con catena di hash** |
| Miglioramenti misurati con statistica | interno | interno | interno | interno | interno | interno | **sì: Research Lab pubblico** |

## 2. La verità sul «superare Claude Max»

**Cosa non è possibile, e perché.** L'intelligenza di Claude, ChatGPT, Gemini e DeepSeek viene da modelli
addestrati su migliaia di schede grafiche, con costi di centinaia di milioni di dollari, ed eseguiti su
server che costano migliaia di euro al mese. Su questo PC (Celeron a 2 core, 3,4 GB di RAM, Intel HD) e con un
budget di 0 € **nessun programma può essere più intelligente di quei modelli**. Su questo PC non gira nemmeno un
modello locale piccolo (profilo `lite-4gb`). Chi dice il contrario mente.

**Cosa invece è possibile, ed è il vantaggio reale di GÉNESIS.** Un abbonamento ti dà *un* modello, dentro
*un* sito, alle *sue* regole. GÉNESIS può essere il **posto da cui guidi tutti i modelli gratuiti insieme**,
con cose che nessuno di loro offre:

1. **Molti cervelli invece di uno, a 0 €.** Attraverso `freelm` (già nel repository) GÉNESIS può usare a turno i
   livelli gratuiti di più fornitori: OpenRouter (modelli `:free`), Groq, Google AI Studio, Cerebras, Mistral,
   Cloudflare. Quando uno è esaurito, passa al successivo. Le quote gratuite sono limitate: circa 50
   richieste al giorno su OpenRouter, secondo `COST_POLICY.md`.
2. **Consiglio e verifica.** La stessa domanda può andare a più modelli diversi. Il Verifier confronta le risposte
   e i controlli deterministici (calcoli, formati) bocciano gli errori. Un insieme di modelli verificati può
   sbagliare meno di un modello singolo: va **misurato** nel Research Lab, non promesso.
3. **Tutto tuo.** Memoria, progetti, cronologia e documenti restano sul tuo disco, si esportano in un file e si
   portano su un altro PC (Passo 5 verificato).
4. **Trasparenza totale.** Per ogni risposta GÉNESIS può mostrare quale motore ha risposto, quanto è costato
   (0 €), quali strumenti ha usato e perché. Ogni azione resta nel registro di audit.
5. **Miglioramento dimostrato.** GÉNESIS non dichiara «più bravo» senza un esperimento statistico (R-001…R-005).
6. **Un'interfaccia che nessuno ha:** il Núcleo, il globo di luci che mostra gli agenti al lavoro.

## 3. Cosa manca, in ordine di importanza

| # | Funzione | Perché conta | Fattibile a 0 € su questo PC? |
|---|---|---|---|
| 1 | **Motore online gratuito acceso** (Passo 6) | senza, GÉNESIS sa fare solo calcoli e analisi di testo semplici | sì: chiave gratuita OpenRouter (e altre gratuite via `freelm`), creata dal proprietario |
| 2 | **Chat vera nel Núcleo**: conversazione a turni, cronologia, risposta che scorre, testo formattato | è l'esperienza base di tutti i concorrenti | sì (interfaccia + API) |
| 3 | **Memoria collegata alla chat** («ricorda che…», contesto automatico) | personalizzazione | sì: Memory Engine con FTS5 già pronto |
| 4 | **Caricare documenti e farci domande** | uso quotidiano | sì: indice FTS5 già scritto (`text.find`) |
| 5 | **Ricerca web con fonti citate** | il punto di forza di Perplexity | parziale: `web.fetch` c'è; serve un motore di ricerca gratuito senza chiave (da verificare in `COST_POLICY.md`) |
| 6 | **Consiglio multi-modello visibile sul globo** (luci per motore, voto, verifica) | il vantaggio unico di GÉNESIS | sì, dopo il punto 1 |
| 7 | **Progetti con istruzioni e file** | lavoro organizzato | sì |
| 8 | **Voce** (dettatura e lettura) | comodità | sì, con la voce del browser; in Chrome la dettatura passa dai server di Google (da dire chiaramente) |
| 9 | **Compiti pianificati** (stile «Pulse»: un riassunto ogni mattina) | lavoro autonomo | sì: la coda dei compiti esiste |
| 10 | **Anteprime di codice e documenti** (stile Artifacts/Canvas) | creazione | sì, nel browser, in sandbox |
| — | Immagini generate | richiesta del proprietario («ragazza che balla») | solo con servizi gratuiti esterni: da verificare termini e privacy; niente in locale su questo PC |
| — | Agente che usa il computer | potente ma rischioso | rimandato: richiede permessi di livello 4–5 e approvazione |

## 4. Proposta

**Prima tappa (consigliata): punti 1 + 2 + 3.** Accendere il motore online gratuito e trasformare il Núcleo
in una **chat vera**: conversazioni salvate, risposta che scorre lettera per lettera, memoria. Durante la
risposta la regione dell'agente si accende sul globo e gli archi mostrano a chi il Director delega. Solo dopo:
documenti, ricerca con fonti, consiglio multi-modello.

**Come dimostreremo i progressi:** per ogni tappa un dataset scritto anche dal proprietario e un confronto
nel Research Lab. Il confronto sarà con *GÉNESIS prima e dopo*, non con Claude Max: con i suoi termini non si può
misurare Claude Max in automatico.

## Fonti

- [Claude — Plans & pricing (ufficiale)](https://claude.com/pricing)
- [Claude Max Plan Features, Limits, and Cost Breakdown (2026)](https://fast.io/resources/claude-max-plan-features/)
- [Claude Max Plan: $100 vs $200 Pricing & Usage Limits](https://intuitionlabs.ai/articles/claude-max-plan-pricing-usage-limits)
- [ChatGPT — Plans and Pricing (ufficiale)](https://chatgpt.com/pricing/)
- [ChatGPT release notes (ufficiale)](https://help.openai.com/en/articles/6825453-chatgpt-release-notes)
- [ChatGPT Plans 2026 compared](https://intuitionlabs.ai/articles/chatgpt-plans-comparison)
- [ChatGPT Features 2026: Projects, Memory, Agent](https://suprmind.ai/hub/chatgpt/features/)
- [DeepSeek previews new AI model (TechCrunch, 2026-04-24)](https://techcrunch.com/2026/04/24/deepseek-previews-new-ai-model-that-closes-the-gap-with-frontier-models/)
- [DeepSeek updated AI model (Bloomberg, 2026-10-17)](https://www.bloomberg.com/news/articles/2026-10-17/deepseek-pushes-out-updated-ai-model-it-says-is-faster-leaner)
- [DeepSeek (chatbot) — Wikipedia](https://en.wikipedia.org/wiki/DeepSeek_(chatbot))
- [Gemini vs Grok vs Perplexity: 2026 Comparison](https://www.chatari.com/compare/gemini-vs-grok-vs-perplexity)
- [AI Subscription Pricing Comparison 2026](https://perspectiveai.xyz/ai-pricing-guide-2026-every-plan-compared/)
- [AI Search and Deep Research Tools Compared 2026](https://felloai.com/ai-search-deep-research-comparison/)
