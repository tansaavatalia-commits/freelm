# Stato del progetto

Aggiornato: 2026-11-24 · Versione: 0.2.0 · Branch: `claude/genesis-phase-0-audit-zrvq7a`

| Fase | Stato |
|---|---|
| 0 — Audit | COMPLETATA, tranne l'hardware reale del PC (PENDENTE: serve l'output di `genesis doctor` dal PC) |
| 1 — Core | IMPLEMENTATA e testata (Linux e Windows in CI). Sul PC del proprietario: PENDENTE |
| 2a — Interfaccia nel browser | IMPLEMENTATA e testata (API + 5 sezioni + test end-to-end in Chromium). Sul PC: PENDENTE |
| 2b — Finestra desktop Tauri | PENDENTE |
| 3–10 | PENDENTI |

## Cosa funziona oggi (IMPLEMENTATO)

- `genesis serve`: interfaccia nel browser su 127.0.0.1 con Dashboard, Progetti,
  Compiti, Approvazioni e Diagnostica; i compiti girano in background.
- CLI completa: `status`, `doctor`, progetti, compiti, approvazioni,
  backup/ripristino, esportazione/importazione, audit.
- Database SQLite (WAL) con migrazioni, backup verificati e portabilità.
- Permessi a 5 livelli, approvazioni monouso, audit a catena di hash.
- Un solo esecutore di compiti per cartella dati (lock del sistema operativo),
  ripresa automatica dei compiti interrotti.
- Rilevamento hardware e profilo automatico; RAM del processo misurata dal vivo.

## Misure

- Processo `genesis serve` (core + API + esecutore): **~28 MB di RAM** (Linux, misurato
  nel test end-to-end). Sul PC Windows da 4 GB: PENDENTE.
- Interfaccia: 68 KB di JavaScript e 3 KB di CSS compressi.

## Cosa NON c'è ancora

- Finestra desktop nativa (Fase 2b), provider di IA e router (Fase 3), agenti
  (Fase 4), strumenti e MCP (Fase 5), laboratori e motori (Fasi 6–9).

## Problemi aperti

1. Il core non è ancora stato eseguito sul PC del proprietario (Windows 10, 4 GB).
2. Le chiavi OpenRouter e Gemini dell'ambiente cloud non funzionano (servono dalla Fase 3).
3. Licenza di GÉNESIS da scegliere (D-06).
