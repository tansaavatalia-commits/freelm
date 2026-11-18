# yt_factory: fabbrica multi-agente di canali YouTube (gratis)

Sistema di agenti AI organizzati in team che gestiscono **3 canali YouTube in parallelo**. Ogni giorno:

1. cercano cosa è virale adesso;
2. inventano idee originali;
3. scrivono, revisionano e ottimizzano gli script;
4. producono i video (voce neurale, sottotitoli animati, montaggio);
5. li **programmano** negli orari migliori;
6. imparano dalle statistiche per migliorare i video successivi.

Tutto gira su **LLM gratuiti** tramite [freelm](../../README.md), che fa failover automatico tra Gemini, Groq, OpenRouter, Cerebras e altri provider.

```
                         ┌──────────── ORCHESTRATORE (ogni giorno, GitHub Actions) ────────────┐
                         │      3 canali in parallelo · più video in produzione insieme        │
                         └─────────────────────────────────────────────────────────────────────┘
 per ogni canale:
  ANALYTICS ──► lezioni dai video pubblicati (cosa ha funzionato, cosa no)
  RICERCA ────► YouTube più visti + views/ora · canali concorrenti (RSS) · Google Trends ──► Trend Analyst
  CREATIVO ───► Ideatore (niente ripetizioni) ──► Sceneggiatore (Short) | Capo Autore + capitoli in parallelo (lungo)
  QUALITÀ ────► Revisore: voto 0-10, originalità, policy di monetizzazione ──► riscrittura guidata / scarto
  SEO ────────► titolo, descrizione, tag, hashtag, testo miniatura, primo commento
  PRODUZIONE ─► voce neurale Edge TTS ─► sfondi (stock Pexels o grafica) ─► sottotitoli parola-per-parola ─► ffmpeg
  PUBBLICAZ. ─► upload programmato (12:30 · 18:00 · 21:00) · dichiarazione AI · commento · controllo quota
  CRESCITA ───► (settimanale) avanzamento verso il Programma Partner + priorità + entrate extra
```

**Output predefinito:** 3 canali × 3 Shorts al giorno (= **9 video/giorno**), più 1 video lungo orizzontale a settimana per canale. Tutto si modifica in [`config/channels.toml`](config/channels.toml): nicchie, voci, orari, numero di video e soglia di qualità.

| Canale | Nicchia | Perché |
|---|---|---|
| **Fatti Pazzeschi** | curiosità: scienza, corpo umano, storia, psicologia | il formato più condiviso negli Shorts |
| **Soldi Smart** | risparmio e finanza personale pratica | la nicchia con l'RPM (guadagno per 1000 views) più alto |
| **Misteri del Mondo** | misteri, luoghi incredibili, enigmi | tempo di visione alto e molti commenti |

---

## Da leggere prima: cosa fa e cosa non può fare

- **Niente copie di video virali.** Gli agenti copiano *argomenti, formati e strutture* che funzionano, mai i contenuti. Dal 2025 YouTube **demonetizza i canali con contenuti "inautentici", prodotti in serie o ripubblicati**. Per questo c'è il Revisore, che scarta e fa riscrivere, e ogni video deve portare un'informazione propria. Questa è la regola che tiene il canale monetizzabile.
- **La monetizzazione richiede soglie che nessuna automazione salta.** Per gli annunci (Programma Partner) servono 1.000 iscritti più 4.000 ore di visione in 12 mesi, *oppure* 10 milioni di views Shorts in 90 giorni. Il livello base (abbonamenti, Super Thanks, Shopping) chiede 500 iscritti più 3.000 ore o 3 milioni di views Shorts. Il sistema traccia l'avanzamento (`stats`) e propone fonti di entrata extra lecite, come i link affiliati in `affiliate_links`.
- **Le views non sono garantite.** Il sistema produce in modo costante e migliora con i dati. Quanti video diventano virali non lo decide il codice.
- **Upload automatico e blocco "privato".** I video caricati via API da un progetto Google **non verificato** restano bloccati come *privati* finché il progetto non supera l'audit di YouTube (gratuito, [modulo qui](https://support.google.com/youtube/contact/yt_api_form)). Nel frattempo i video si scaricano dagli *artifact* di GitHub e si caricano o programmano dall'app YouTube Studio (circa 1 minuto a video).
- **Quota API.** Ogni progetto Google ha 10.000 unità al giorno e un upload ne costa circa 1.600, quindi un progetto copre **~6 upload al giorno**. Per 9 video al giorno puoi:
  - creare 2-3 progetti Google Cloud e dare a ogni canale il suo (`YT_CLIENT_ID_<CANALE>` / `YT_CLIENT_SECRET_<CANALE>`);
  - oppure chiedere un aumento di quota (stesso modulo dell'audit).

  Se la quota finisce, il sistema non va in errore: il video resta pronto in coda.
- **Dichiarazione AI.** Ogni upload imposta `containsSyntheticMedia`, come richiesto da YouTube per i contenuti generati con AI. Non toglierla.

---

## Setup (circa 45 minuti, tutto gratis)

### 1. Prova subito, senza account
```bash
cd apps/yt_factory
pip install -e ../.. -r requirements.txt          # serve anche ffmpeg (apt/brew install ffmpeg)
python -m yt_factory run --offline --count 1       # catena completa senza rete (agenti finti)
python -m yt_factory run --channel fatti --count 1 # vero: LLM gratuiti + voce reale, nessun upload
```
I video finiscono in `data/videos/<canale>/<data>/` (`.mp4`, più `.json` con titolo, descrizione e tag, più `.png` della miniatura).

### 2. Chiavi gratuite (da mettere nelle variabili d'ambiente o nei Secrets di GitHub)
| Variabile | A cosa serve | Dove si prende |
|---|---|---|
| `GEMINI_API_KEY` | LLM principale (consigliato) | https://aistudio.google.com/apikey |
| `GROQ_API_KEY` | LLM veloce di riserva | https://console.groq.com/keys |
| `OPENROUTER_API_KEY` | altri modelli gratuiti | https://openrouter.ai/keys |
| `PEXELS_API_KEY` | **video stock veri come sfondo** (molto meglio della grafica astratta) | https://www.pexels.com/api/ |
| `YT_API_KEY` | trend YouTube live (video più visti, views/ora) | Google Cloud, vedi passo 3 |

Senza chiavi LLM il sistema usa gli endpoint pubblici senza chiave: limiti bassi e i prompt possono essere registrati. Per lavorare con costanza servono **almeno 2 chiavi**. `freelm doctor` mostra quali funzionano.

### 3. Progetto Google Cloud (pubblicazione e trend)
1. Apri https://console.cloud.google.com, crea il progetto `yt-factory` e abilita **YouTube Data API v3** e **YouTube Analytics API**.
2. In *Credenziali* crea una **chiave API** e salvala come `YT_API_KEY`.
3. In *Schermata consenso OAuth* scegli tipo **Esterno**, aggiungi te stesso come utente e poi premi **PUBBLICA L'APP** ("In produzione"). Se l'app resta in "Test", i token scadono dopo 7 giorni e l'automazione si ferma.
4. In *Credenziali* crea un **ID client OAuth** di tipo *App desktop* e salvalo come `YT_CLIENT_ID` / `YT_CLIENT_SECRET`.

### 4. I 3 canali
Con lo stesso account Google crea 3 canali "brand" da https://www.youtube.com/account, opzione *Crea un nuovo canale*. Verifica il telefono su https://www.youtube.com/verify: serve per miniature personalizzate e video oltre i 15 minuti. Poi, **sul tuo computer**, una volta per canale:
```bash
python -m yt_factory auth --channel fatti     # nel browser scegli il canale "Fatti Pazzeschi"
python -m yt_factory auth --channel soldi
python -m yt_factory auth --channel misteri
```
Ogni comando stampa `YT_REFRESH_TOKEN_<CANALE>=...`: salvalo come segreto.

### 5. Pilota automatico (GitHub Actions, gratis)
1. Nel repository su GitHub apri *Settings → Secrets and variables → Actions → New repository secret* e aggiungi tutte le chiavi dei passi 2-4.
2. Verifica: *Actions → yt-factory → Run workflow*, con `publish` spento. Alla fine scarica i video dall'artifact e guardali.
3. Quando ti piacciono, apri *Variables → New variable*: `YTF_PUBLISH` = `true`. Da quel momento **ogni giorno alle 06:17** (ora italiana) il sistema produce e programma i video da solo.

La "memoria" (storico, lezioni apprese, quota usata) resta salvata fra un'esecuzione e l'altra. Rilanciare nello stesso giorno non duplica i video.

---

## Comandi
```bash
python -m yt_factory run [--channel ID] [--count N] [--long] [--publish] [--offline]
python -m yt_factory trends --channel soldi   # cosa è virale ora e perché
python -m yt_factory stats                    # iscritti, ore, views Shorts, idoneità al Programma Partner
python -m yt_factory status                   # ultimi video, stato e views
```

## Migliorare la qualità (in ordine di impatto)
1. **`PEXELS_API_KEY`**: sfondi video reali al posto della grafica astratta.
2. **Musica**: metti 5-10 brani *royalty-free* (da YouTube Studio → Libreria audio) in `assets/music/`. Vanno sotto la voce all'8% del volume.
3. **`seed_channel_ids`**: aggiungi gli ID (`UC...`) di 5-10 canali di successo della tua nicchia. Il team ricerca ne segue i video in tempo reale.
4. **Revisione umana**: con `privacy_mode = "private"` ogni video resta privato finché non lo approvi in Studio.
5. **Lingua inglese**: mercato 10-20 volte più grande e RPM più alti. Nel canale imposta `language = "en"`, `region = "US"` e `voice = "en-US-AndrewNeural"`.

## Struttura
```
config/channels.toml   canali, nicchie, voci, orari, soglie
yt_factory/agents.py   i 9 agenti (ruoli + prompt + regole di policy)
yt_factory/pipeline.py orchestratore: team in parallelo, riscritture, quota, programmazione
yt_factory/trends.py   dati di tendenza (YouTube API, RSS, Google Trends)
yt_factory/tts.py      voce neurale gratuita con tempi parola-per-parola
yt_factory/render.py   sfondi, sottotitoli animati, montaggio ffmpeg, miniature
yt_factory/youtube.py  upload, miniature, commenti, statistiche, Analytics, avanzamento monetizzazione
yt_factory/auth.py     collegamento OAuth dei canali
.github/workflows/yt-factory.yml (nella radice del repo)  esecuzione quotidiana
```
