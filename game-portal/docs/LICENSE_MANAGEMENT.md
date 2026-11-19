# GAME PORTAL — Gestione licenze

**Regola bloccante:** un gioco può passare a `published` solo se la sua licenza è
`approved`, non è scaduta, copre il territorio e include diritti di hosting e di
monetizzazione. Il controllo è applicato **sia nel backend sia nel database**, non solo nell'interfaccia.

## Registro (tabella `licenses`)
| Campo | Tipo | Note |
|---|---|---|
| `id` | ULID | identificativo |
| `game_id` | FK | gioco |
| `title` | testo | titolo concesso |
| `developer` | testo | sviluppatore |
| `rights_holder` | testo | proprietario dei diritti |
| `license_type` | enum | `internal`, `direct_license`, `commissioned`, `open_source` |
| `spdx_id` | testo | per open source (es. `MIT`, `CC0-1.0`) |
| `territory` | testo | es. `WORLD` o elenco ISO 3166 |
| `start_date` / `end_date` | data | `end_date` null = perpetua |
| `exclusivity` | enum | `none`, `exclusive`, `exclusive_territory` |
| `hosting_rights` | bool | |
| `monetization_rights` | bool | pubblicità/sponsor/Premium attorno al gioco |
| `marketing_assets_rights` | bool | immagini, screenshot, video |
| `attribution_text` | testo | testo obbligatorio da mostrare |
| `game_version` | testo | versione coperta |
| `approval_status` | enum | `draft`, `under_review`, `approved`, `rejected`, `expired`, `revoked` |
| `approved_by` / `approved_at` | | utente admin + data |
| `evidence` | lista | file probatori (contratto firmato, copia della LICENSE, commit di origine con hash) |
| `notes` | testo | |

## Procedure
- **Giochi interni:** registrazione `internal` con riferimento al commit sorgente; asset
  di terzi elencati uno per uno con licenza (solo CC0/CC-BY o equivalenti).
- **Open source:** copia della LICENSE e hash del commit di origine archiviati, verifica
  della compatibilità con la monetizzazione e con gli asset (spesso con licenze diverse dal codice).
- **Scadenze:** job giornaliero che segnala le licenze in scadenza a 60/30/7 giorni e
  **sospende automaticamente** i giochi con licenza scaduta (`suspended`, non cancellato).
- **Sospensione immediata:** pulsante admin + endpoint che mette un gioco in
  `suspended`, invalida la cache e registra l'evento nell'audit log; tempo di effetto < 1 minuto.
