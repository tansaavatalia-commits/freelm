# Installazione su Windows: guida rapida (20–40 minuti)

La strategia principale è il **momentum giornaliero** (quella che ha reso di più nei
test). Il bot lavora **solo in carta** (100 € simulati). Non tocca mai soldi veri e non
chiede mai permessi di prelievo. Tutto ciò che salva resta in
`C:\Users\<tu>\freelm-bot-datos`.

## Prima di iniziare

- Windows 10 o 11, connessione a internet, circa 2 GB liberi.
- Facoltativo: chiave gratuita di Gemini o Groq (l'analista IA), bot Telegram per gli avvisi.

## 1. Scarica il bot

1. Apri https://github.com/tansaavatalia-commits/freelm, poi pulsante verde
   **Code → Download ZIP**.
2. Fai clic destro sul file ZIP → **Estrai tutto** → scegli `Documenti\freelm`.
   Non usare una cartella sincronizzata con OneDrive.

## 2. Avvia l'installatore

1. Entra in `Documenti\freelm\freelm-main\examples\trading_agents\windows`.
2. Doppio clic su **`Instalar-Bot.bat`**.
   - Se compare «Windows ha protetto il PC»: **Ulteriori informazioni → Esegui comunque**.
3. Nel menu scrivi **1** (Instalación completa) e premi Invio. L'installatore
   è in spagnolo; ecco cosa chiede, passo per passo:

| Passo | Cosa succede | Cosa rispondere |
|---|---|---|
| 1/7 Python | Se manca, lo installa con winget | **S** e Invio. Se poi dice di riaprire, chiudi la finestra e rifai il doppio clic |
| 2/7 Entorno | Installa il bot e le sue dipendenze (2–5 min) | Niente, aspetta |
| 3/7 Claves | Chiavi facoltative (IA, Telegram) | Incollale (clic destro) oppure premi solo Invio per saltarle. Alla domanda sulle chiavi dell'exchange rispondi **N** |
| 4/7 Optimización | Prima ottimizzazione con dati reali (10–20 min) | **S** se hai tempo, altrimenti **n** |
| 5/7 Bot sperimentale | Il bot a 105 agenti a 5 minuti, che quasi non opera mai | **N** (resta spento; se ti serve si attiva con l'opzione 20). Alla domanda sulla sospensione del PC: **S** se il PC resta acceso di notte |
| 6/7 Prueba diaria | **La strategia principale**: momentum in carta ogni giorno alle 01:30, più segnali e pannello | **S** a «¿Procesar ya el día de hoy?» |
| 7/7 Accesos | Tre icone sul desktop | Niente |

## 3. Controlla che funzioni

- Icona **«Bot de trading - Resultados»**: apre il pannello nel browser, con
  capitale, aciertos dei segnali e monete.
- Icona **«Bot de trading - Informe»**: come va il momentum in carta e quanto
  azzeccano i segnali dal vivo.
- Icona **«Bot de trading - Panel»**: riapre questo menu.

## 4. Facoltativo (anche un altro giorno)

- **Opzione 17**: database Supabase (gratis) per avere i risultati anche nel cloud.
- **Opzione 18**: avvisi via email con Zapier e Gmail.
- **Opzione 11 (consigliata subito dopo l'installazione)**: testnet di Binance,
  cioè un conto demo con denaro finto ma ordini veri. In 6 passi guidati:
  1. entri con GitHub su testnet.binance.vision;
  2. crei le chiavi;
  3. le incolli;
  4. il bot verifica la connessione;
  5. parte il **momentum in testnet** (portafoglio proprio di 1000 USDT finti, ordini
     ogni giorno alle 01:30) e, se vuoi, anche il bot a 5 minuti (scegli **b**);
  6. ti spiega cosa controllare.

  Così le prove vere sull'exchange girano insieme alla prova in carta.
  Opzione 13 = rapporto della testnet.

## Se qualcosa va storto

| Problema | Soluzione |
|---|---|
| «L'esecuzione degli script è disabilitata» | Apri sempre `Instalar-Bot.bat`, non il file `.ps1` |
| Python installato ma «non trovato» | Chiudi la finestra e rifai il doppio clic su `Instalar-Bot.bat` |
| Errore al passo 2 | Controlla la connessione e scegli di nuovo l'opzione 1 |
| Altro | Fai una foto dello schermo o copia il testo dell'errore e mandamelo |

Registri: `freelm-bot-datos\registros\` (`bot-AAAAMMGG.log`, `diario-AAAAMMGG.log`).
