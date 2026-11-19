# Analisi GitHub: cosa esiste di forte e cosa ne abbiamo preso

Ricerca del 19-11-2026 su GitHub (oltre 20 ricerche: generatori di Shorts, produzione video agentica, video da
codice, sintesi vocale, sottotitoli, musica, miniature, automazione YouTube). Per ogni progetto: cosa fa meglio
di noi, licenza, fattibilità gratis su GitHub Actions (solo CPU), decisione.

## I progetti che contano

| Progetto | ★ | Licenza | Cosa fa di forte | Decisione |
|---|---|---|---|---|
| [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) | 144k | MIT | da tema a Short: stock Pexels/Pixabay, sottotitoli parola per parola, musica, tagli | ripreso: tagli brevi alternati, sottotitoli animati (già fatto) |
| [OpenMontage](https://github.com/OpenMontageInc/OpenMontage) | 82k | AGPL-3.0 | produzione video agentica: 12 pipeline, analisi di un video di riferimento, **controlli qualità dopo il render**, "rischio presentazione", filmati d'archivio reali (Archive.org, NASA, Wikimedia), Remotion/HyperFrames | **ripresi i concetti** (non il codice, AGPL): reparto controllo qualità `qc.py`; filmati d'archivio e grafica animata → roadmap |
| [Remotion](https://github.com/remotion-dev/remotion) | 74k | gratis per persone e piccole aziende | video da codice React: testo cinetico, animazioni a molla, grafici, card numeriche | roadmap fase 2: grafica animata per *Money Decoded* (numeri, grafici) |
| [HyperFrames](https://github.com/heygen-com/hyperframes) (HeyGen) | — | Apache-2.0 | video da HTML/CSS/GSAP: tipografia cinetica, motion graphics | alternativa a Remotion, licenza più libera |
| [rea-video](https://github.com/JuneYaooo/rea-video) | 11k | Apache-2.0 | reverse-engineering di un video inquadratura per inquadratura (tagli, ritmo, sottotitoli, musica, BPM) | idea per il Viral Deconstructor: analizzare il *montaggio* dei virali, non solo i titoli → roadmap |
| [Verticals / youtube-shorts-pipeline](https://github.com/rushindrasinha/youtube-shorts-pipeline) | 2.4k | MIT | profili di nicchia che guidano ogni fase; ricerca come "barriera anti-allucinazioni"; musica per umore con ducking | ripreso: musica di sottofondo che si abbassa sotto la voce (`music.py` + sidechain); la ricerca con fonti c'era già (Story Miner) |
| [anything2explainer](https://github.com/Vincentwei1021/anything2explainer) | 3.4k | — | spiegoni Remotion con voce Kokoro, sottotitoli allineati, barra capitoli | conferma la direzione Remotion per i video lunghi |
| [kinetograph](https://github.com/0xS4N4TG/kinetograph) | 0.5k | Apache-2.0 | renderizza progetti Remotion **senza browser** (Rust) | beta: da rivalutare per velocizzare il render |
| [whisperX](https://github.com/m-bain/whisperX) | 25k | BSD-2 | tempi parola per parola da qualsiasi audio | serve solo se cambiamo voce (Kokoro): Edge TTS dà già i tempi |
| [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) | 2.9k | MIT | voce inglese locale di alta qualità, CPU | opzione per non dipendere dal servizio Microsoft di Edge TTS |
| [ShortGPT](https://github.com/RayVentura/ShortGPT) | 8k | MIT | uno dei primi framework per Shorts | fermo dal 2025, niente di nuovo |

## Strumenti GitHub sfruttati

- **GitHub Models**: LLM gratuiti e forti (GPT-4.1, DeepSeek V3, Llama 3.3 70B) dentro Actions con il token
  automatico del repository (`ghmodels.py`, permesso `models: read`). Risolve il limite principale: i modelli
  pubblici senza chiave scrivevano concetti confusi e script da 5/10.
- **GitHub Actions**: computer gratuiti con IP non condiviso (niente blocchi di Wikipedia/Wikimedia), esecuzione
  ogni giorno, prove avviabili con un commit `[run-studio]`.
- **Segreti già presenti nel repository**: `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY` (usati dal
  trading bot) e `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` → riepilogo e video su Telegram (`notify.py`).
- **Artifact**: i video di ogni esecuzione restano scaricabili per 7 giorni.

## Fonti gratuite verificate

| Fonte | Per cosa | Note |
|---|---|---|
| Feed RSS dei canali YouTube | dati virali reali (views/ora) | senza chiave, 15 canali di riferimento configurati |
| Wikipedia REST | fonti per la scrittura e la verifica dei fatti | rispettare i limiti (429): gestiti con attesa |
| Openverse immagini | foto reali CC0/PD/CC BY | crediti CC BY scritti in descrizione |
| Openverse audio (Wikimedia Commons) | musica CC0: Komiku, Monplaisir, John Bartmann, Rafael Krux | Freesound escluso: il CDN rifiuta i download esterni |
| Pollinations | immagini AI originali | senza chiave; con token gratuito più veloce |
| NASA Images API | foto e video di pubblico dominio (spazio, Terra) | roadmap: filmati reali per i misteri spaziali |

## Roadmap (in ordine di impatto)

1. **Grafica animata con Remotion o HyperFrames** per *Money Decoded*: numeri che crescono, confronti, grafici.
   È ciò che distingue un canale finanza professionale da una presentazione.
2. **Filmati reali in movimento** (NASA, Wikimedia Commons video, Archive.org) al posto delle foto ferme, con
   selezione per pertinenza.
3. **Analisi del montaggio dei virali** (stile rea-video): ritmo dei tagli, durata dei sottotitoli e struttura,
   per tarare `shot_seconds` e il ritmo per nicchia con dati veri.
4. **Voce Kokoro** come alternativa locale a Edge TTS.
