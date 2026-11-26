# Politica dei costi

**Budget autorizzato: 0 €.** Ogni spesa è un'azione di livello 5 e richiede
l'approvazione esplicita del proprietario.

## Regole

1. Nessun acquisto, abbonamento, ricarica, credito o prova che chieda una carta.
2. Un servizio esterno si integra solo dopo aver verificato condizioni, limiti e
   licenza; finché non è verificato resta un'integrazione opzionale **disattivata**.
3. Il router (Fase 3) non sceglierà mai un provider a pagamento, nemmeno come fallback.
4. Un piano gratuito non è considerato gratuito finché le sue condizioni non
   sono state lette e registrate qui, con la data.

## Stato dei servizi

| Servizio | Uso | Costo verificato | Note |
|---|---|---|---|
| Python, SQLite, libreria standard | core | 0 € (open source) | — |
| GitHub Actions (`genesis-core-ci`) | test Linux e Windows | 0 € finché il repo è pubblico | runner standard |
| OpenRouter (solo modelli a prezzo zero) | motore online di GÉNESIS, spento finché `genesis online enable` | **0 € verificato (2026-11-24)**, vedi registro | privacy: le rotte gratuite possono registrare i prompt; comprare crediti è vietato |
| Google AI Studio (Gemini) | Fase 3, disattivato | NON VERIFICATO | gratuito solo senza fatturazione sul progetto: da confermare dal proprietario |
| Groq, Cerebras, Mistral, Cohere, Z.ai, NVIDIA NIM, Cloudflare | Fase 3, disattivati | NON VERIFICATO | da verificare uno per uno prima di attivarli |
| Kilo / OVHcloud senza chiave | motore online di GÉNESIS, **solo con `keyless_allowed = true`** (scelta del proprietario del 2026-11-26) | **0 €** (nessun account, nessuna chiave, nessun modo di pagare), vedi registro | privacy: le rotte gratuite possono registrare i prompt; limiti bassi (Kilo ~200 richieste/ora per IP, OVH 2/minuto per modello) |
| Firma del codice, hosting, domini | — | a pagamento | non usati |

## Come si attiva un motore online (Fase 3)

Nel file `genesis.toml` della cartella dati, **solo dopo** aver verificato e
registrato qui le condizioni gratuite di ogni provider usato da freelm:

```toml
[intelligence]
remote_enabled = true
remote_free_verified = true
```

Servono anche la libreria `freelm` (`pip install freelm`, installazione = livello 4)
e le chiavi gratuite nelle variabili d'ambiente. Gli endpoint senza chiave (Kilo,
OVHcloud) si usano solo se il proprietario aggiunge `keyless_allowed = true`
(`genesis online enable --keyless --confirm`).

## Registro delle verifiche

**2026-11-24 — OpenRouter, verifica delegata dal proprietario a Claude.**
Evidenze: (1) API pubblica dei modelli: 473 modelli, 15 con prezzo 0/0 (12 con
suffisso `:free`); (2) GÉNESIS usa solo il servizio `openrouter` di freelm e solo
se la sua guardia «solo gratuito» è attiva, quindi chiede esclusivamente modelli
`:free` o a prezzo zero (prova reale: scelto `nvidia/nemotron-3.5-super-vl:free`);
(3) nessun acquisto di crediti è previsto né consentito. Non verificabile senza una
chiave funzionante: lo stato dell'account (crediti, limite giornaliero, di solito
50 richieste/giorno senza crediti secondo i dati di freelm). Rischio residuo: la
privacy dei modelli gratuiti, mitigata dall'opzione «privata» che resta locale.

**2026-11-26 — Kilo Gateway e OVHcloud senza chiave, scelta del proprietario.**
Il proprietario non ha creato la chiave OpenRouter e ha scelto esplicitamente i servizi senza chiave,
dopo l'avviso sulla privacy. Perché costano 0 €: nessun account né chiave esiste, quindi non c'è un mezzo di
pagamento; Kilo è usato con la guardia «solo gratuito» di freelm (solo rotte `:free`/a prezzo zero); OVHcloud
solo nel livello anonimo (con una chiave sarebbe a consumo: freelm la scarta sempre). Limiti dichiarati da freelm
(verificati 2026-10): Kilo ~200 richieste/ora per IP, OVH 2 richieste/minuto per IP e per modello. Rischio
residuo: le domande inviate possono essere registrate dai servizi → le conversazioni «private» restano locali.
Prova reale dal PC del proprietario: risposta corretta in italiano (vedi TEST_REPORT.md).

| Data | Servizio | Esito |
|---|---|---|
| 2026-11-26 | Kilo/OVH senza chiave, `genesis ask` e chat in streaming | risposte ricevute; 1ª risposta in 26 s (avvio), poi 2,4 s |
| 2026-11-23 | OpenRouter, elenco pubblico dei modelli | 476 modelli, 15 con prezzo 0/0 (chiamata gratuita, senza chiave) |
| 2026-11-23 | OpenRouter, informazioni sulla chiave | 401: la chiave non viene inserita dal proxy |
| 2026-11-23 | Gemini, endpoint OpenAI-compatibile | 404 su ogni modello dopo il nuovo salvataggio della chiave |
