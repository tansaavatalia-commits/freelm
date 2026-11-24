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
| Kilo / OVHcloud senza chiave | — | — | esclusi: le rotte gratuite possono registrare i prompt |
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
e le chiavi gratuite nelle variabili d'ambiente. Gli endpoint senza chiave non
vengono mai usati.

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

| Data | Servizio | Esito |
|---|---|---|
| 2026-11-23 | OpenRouter, elenco pubblico dei modelli | 476 modelli, 15 con prezzo 0/0 (chiamata gratuita, senza chiave) |
| 2026-11-23 | OpenRouter, informazioni sulla chiave | 401: la chiave non viene inserita dal proxy |
| 2026-11-23 | Gemini, endpoint OpenAI-compatibile | 404 su ogni modello dopo il nuovo salvataggio della chiave |
