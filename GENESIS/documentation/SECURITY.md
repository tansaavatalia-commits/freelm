# Sicurezza

## Livelli di autonomia (implementati in `genesis/security/permissions.py`)

| Livello | Significato | Regola |
|---|---|---|
| 1 | lettura, ricerca, analisi | entro il permesso del principal |
| 2 | creazione di file e record di lavoro | entro il permesso del principal |
| 3 | esecuzione di test e processi controllati | entro il permesso del principal |
| 4 | installazioni e modifiche del sistema | permesso **e** approvazione del proprietario, monouso |
| 5 | spese, pubblicazioni, cancellazioni definitive | permesso **e** approvazione esplicita del proprietario, monouso |

- I permessi massimi stanno in `genesis.toml` (cartella dati, fuori dal repo) e a
  runtime sono **in sola lettura**: non esiste alcuna API per aumentarli.
- Un principal senza permesso configurato ha livello 0: non può fare nulla.
- Solo `owner` decide le approvazioni; ogni approvazione vale per un principal,
  un'azione e un livello precisi, e si consuma al primo uso.
- Il permesso viene ricontrollato quando un compito parte: se nel frattempo è
  stato abbassato, il compito fallisce con «permesso revocato».

## Audit

- Ogni decisione (consentita o negata) e ogni approvazione finisce in `audit_log`.
- Le righe sono append-only (trigger SQL) e concatenate con SHA-256:
  `genesis audit verify` individua la prima riga modificata o cancellata.
- **Limite noto:** la cancellazione delle righe più recenti (troncamento) non è
  rilevabile senza un'ancora esterna. Possibile miglioramento futuro: pubblicare
  periodicamente l'ultimo hash in un luogo separato.

## Segreti

- `redact()` oscura i formati di chiave noti (OpenRouter, Google, Groq, NVIDIA,
  Cerebras, stile OpenAI, Bearer) e i valori `api_key=…`, `token: …`, `"password": "…"`.
- Si applica a ogni riga di log, ai dettagli dell'audit e ai messaggi d'errore dei compiti.
- Nessun segreto nel repository: database, `genesis.toml`, `.env` e cartelle dati
  sono in `.gitignore`, e un test fallisce se compaiono dentro `GENESIS/`.

## Modello di fiducia

- Il codice Python in esecuzione nello stesso processo è considerato fidato. Gli
  agenti (Fase 4) agiranno solo attraverso il livello dei permessi e non
  riceveranno mai un riferimento a `PermissionManager.decide`.
- Dalla Fase 5 gli strumenti dovranno negare la scrittura su `genesis.toml` e
  sulla cartella `data/` (PENDENTE).
- I contenuti esterni (web, documenti, output di strumenti) saranno trattati
  come dati non fidati e non potranno modificare le politiche (PENDENTE, Fase 5).

## Rischi dell'ambiente

- Windows 10 è fuori supporto: il PC potrebbe non ricevere patch di sicurezza
  (NON VERIFICATO). Il core non apre porte di rete; l'API della Fase 2 ascolterà
  solo su 127.0.0.1 con un token.
- Il repository è pubblico: tutto ciò che viene committato è visibile a chiunque.
- Un tag `v*` o `js-v*` avvierebbe la pubblicazione di `freelm`: vietato senza
  approvazione esplicita.

## Segnalazioni

Per vulnerabilità in `freelm` vale il `SECURITY.md` alla radice del repository.

## API locale (Fase 2a)

- Ascolta **solo su 127.0.0.1**; una richiesta con un `Host` diverso viene
  rifiutata (difesa dal DNS rebinding).
- Ogni chiamata `/api` richiede il token dell'installazione (`data/api_token`,
  generato con `secrets`, confronto a tempo costante). Il token è inserito solo
  nella pagina servita dalla stessa origine; non vengono mai inviate intestazioni
  CORS, e le richieste con `Origin` di un altro sito sono rifiutate.
- La pagina gira con una Content-Security-Policy rigorosa (nessuno script inline,
  nessun host esterno, nessun frame) e `X-Frame-Options: DENY`.
- Corpi delle richieste limitati a 64 KB; file statici confinati nella cartella
  dell'interfaccia (test di path traversal).
- Chi usa l'interfaccia è il proprietario (come per la CLI). Il ripristino dei
  backup resta solo da riga di comando con `--confirm`.
- Su Windows i permessi 0600 del file del token non si applicano: il file è protetto
  dai permessi della cartella utente `%LOCALAPPDATA%`.

## Strumenti (Fase 5)

- Ogni chiamata: autorizzazione centrale (livello dello strumento) + voce `tool.call` nell'audit.
- Gli agenti usano solo gli strumenti del proprio elenco e solo entro il proprio livello (predefinito 1).
- File: solo dentro `<home>/workspace`; percorsi assoluti, `..` e symlink verso l'esterno rifiutati.
  `genesis.toml` e `data/` sono fuori dalla cartella di lavoro, quindi irraggiungibili dagli strumenti.
- Web: spento di default; indirizzi locali/privati rifiutati (anche nei redirect). Limite noto: il
  controllo dell'indirizzo e la connessione risolvono il DNS separatamente.
- I risultati esterni (web, MCP) sono **dati non fidati**: prima di arrivare a un modello vengono
  racchiusi in delimitatori che non possono essere chiusi dal contenuto.
- MCP: solo i server scritti dal proprietario in `genesis.toml`; ogni processo vive per una sola
  richiesta ed è terminato allo scadere del tempo.

## Motori, modelli e auto-miglioramento (Fasi 7–9)

- Ogni operazione dei motori passa dall'autorizzazione centrale; i motori leggono file solo nella cartella di lavoro.
- Memoria: i segreti vengono oscurati prima del salvataggio; la memoria permanente scritta da un agente richiede
  livello 4 **e** un'approvazione; la ricerca usa termini tra virgolette (nessuna iniezione di sintassi FTS).
- Modelli locali: accettati solo endpoint su loopback, chiamati senza proxy; nessun download o installazione.
- Auto-miglioramento: aree protette rifiutate in codice (test); promozione e ritorno indietro richiedono
  un'approvazione monouso di livello 4; ogni passo è nell'audit.
