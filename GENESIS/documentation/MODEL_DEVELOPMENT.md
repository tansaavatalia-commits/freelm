# Model Development Lab (Fase 8)

Sul PC iniziale (Windows 10, 4 GB) **non si addestra e non si scarica nessun modello**. Questi strumenti
servono a decidere con i numeri quando ci sarà hardware adeguato.

| Comando | Cosa fa |
|---|---|
| `genesis models list` | catalogo di modelli aperti con la migliore quantizzazione eseguibile su questo PC |
| `genesis models check ID --quant q4_k_m --context 4096` | stima dettagliata: pesi, cache, sovraccarico, memoria libera |
| `genesis models plan ID --method qlora --examples 1000 --tokens 300` | piano di fine-tuning in `<home>/reports` |

## Come sono fatte le stime (indicative, non misure)

- **Pesi** = parametri × byte per peso della quantizzazione (approssimazioni GGUF: q4_k_m ≈ 0,61 byte, q8_0 ≈ 1,06).
- **Cache** ≈ 20 KB per token per miliardo di parametri (fp16, attenzione a gruppi).
- **Memoria libera** = RAM totale − riserva per il sistema (2,5 GB su Windows) − 0,15 GB per GÉNESIS.
- Verdetto: *eseguibile* se serve al massimo il 70% della memoria libera (o sta nella VRAM), *al limite*
  fino al 100%, altrimenti *non eseguibile*. Il profilo `lite-4gb` disattiva comunque i modelli locali.
- **Fine-tuning** (±50%): full 16 byte/parametro, LoRA 2, QLoRA 0,55, + adattatori (~1% dei parametri)
  + attivazioni. Serve una GPU: su questo PC è sempre «non fattibile».

## Catalogo

I dati (parametri, licenza, contesto) sono quelli delle schede ufficiali **come note alla data di scrittura,
non verificati**: controllare sempre la scheda prima dell'uso. Attenzione alle licenze non Apache/MIT
(Llama Community License, Gemma Terms, Qwen Research License). Il proprietario può aggiungere modelli con un
file JSON in `<home>/models/` (`id`, `family`, `params_b`, `license`, `context`, `source`, `notes`).

## Modello locale (quando l'hardware lo permette)

GÉNESIS può usare un server compatibile OpenAI avviato dal proprietario **sullo stesso PC** (llama.cpp server,
Ollama, LM Studio). GÉNESIS non installa né scarica nulla.

```toml
[models.local]
endpoint = "http://127.0.0.1:8080/v1"   # solo indirizzi locali: altri vengono rifiutati
model = "qwen2.5-1.5b-instruct-q4_k_m"
# allow_on_lite = true                  # solo per forzarlo sul profilo lite-4gb (sconsigliato)
# timeout = 120
```

È un modello esterno a GÉNESIS (risposte «non verificate»), ma i dati restano sul PC: può servire anche le
richieste private. Il router preferisce comunque il motore deterministico per calcoli e conteggi.
