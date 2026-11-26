# Stato del progetto

Aggiornato: 2026-11-25 · Versione: 0.9.0 · Branch: `claude/genesis-phase-0-audit-zrvq7a`

| Fase | Stato |
|---|---|
| 0 — Audit | completata, anche sull'hardware reale del PC (2026-11-25) |
| 1 — Core | implementata e testata (Linux + Windows in CI) |
| 2a — Interfaccia nel browser | implementata e testata (test end-to-end in Chromium) |
| 2b — Finestra Tauri | PENDENTE (dopo la prova sul PC) |
| 3 — Intelligent Router | implementata; motore online OpenRouter gratuito pronto, mai provato dal vivo (chiave) |
| 4 — Agenti | implementata (8 agenti, Verifier, Director, Consiglio v0) |
| 5 — Strumenti e MCP | implementata (sandbox file, web.fetch provato dal vivo, MCP) |
| 6 — Research Lab | implementata (esperimenti, confronti statistici, riproduzione) |
| 7 — Motori GÉNESIS | implementata (6 motori; v2 sperimentali misurate in R-003/R-004) |
| 8 — Model Development | implementata (catalogo, fattibilità, piani, modello locale) |
| 9 — Auto-miglioramento | implementata (ciclo con prove, approvazione del proprietario, aree protette) |
| 10 — Release | PENDENTE |

## Misure

- 207 test Python (208 con freelm installato) + test end-to-end nel browser su tutte le pagine.
- Processo `genesis serve`: circa 32 MB di RAM (Linux); sul PC Windows **43,9 MB** (picco 49,4 MB),
  9 pagine su 9 senza errori, RAM libera del sistema 463 MB con GÉNESIS aperto (2026-11-26).
- PC del proprietario (2026-11-25): Windows 10 Pro 19045, Celeron N3060 2 core, 3,4 GB di RAM
  (0,4–0,6 GB liberi), HDD 466 GB, WebView2 presente. `genesis doctor`: 7/7 controlli OK, profilo
  `lite-4gb`. Test: 208 raccolti, **206 passati, 0 falliti, 2 saltati** (Python 3.15.2, ~100–130 s).
- 2026-11-26: nuovo strumento `text.find` (ricerca indicizzata FTS5). Test: **210, 208 passati, 0 falliti,
  2 saltati** sul PC. Misura R-005: 75–100 ms invece di 2,3–2,7 s per le parole rare su 1000 file.
- Interfaccia: circa 75 KB di JavaScript compressi.

## Versioni attive dei componenti

Di default `classifier = v1` e `math = v1`. Le v2 sono **sperimentali**: il ciclo della Fase 9 le raccomanda
(miglioramento dimostrato sui dataset pre-registrati), ma la promozione spetta al proprietario
(`genesis improve …` o pagina «Miglioramento»), sapendo che i benchmark sono interni (R-003).

## Problemi aperti

1. Sul PC del proprietario manca ancora la prova di portabilità (Passo 5). La RAM libera del PC è molto
   bassa (0,4–0,6 GB), occupata soprattutto da browser e app Claude, non da GÉNESIS.
2. Il motore online non ha mai risposto dal vivo (chiave OpenRouter da impostare sul PC).
3. Licenza di GÉNESIS da scegliere (D-06).
4. Serve un dataset scritto dal proprietario per una valutazione indipendente delle v2.
