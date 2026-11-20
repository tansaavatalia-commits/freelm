# COST_CONTROL — Controllo dei costi

## 1. Costi effettivi sostenuti finora

**€0.** Nessun servizio a pagamento attivato, nessun account creato, nessuna API abilitata.

## 2. Stack di sviluppo (costo €0)

Python, FastAPI, PostgreSQL, SQLAlchemy, Alembic, Procrastinate, HTMX, Chart.js, Docker Compose,
pytest, ruff, mypy, restic: tutti open source. LLM tramite `freelm` (free tier di provider multipli).
GitHub Actions: gratuito entro i limiti dei repository (verificare se privato: minuti inclusi limitati).

## 3. Costi futuri potenziali (nessuno attivato)

Per ciascuno: perché serve · alternative gratuite · costo · beneficio · si può procedere senza?

| Servizio | Perché | Alternativa gratuita | Costo indicativo *(da verificare)* | Beneficio | Senza? |
|----------|--------|----------------------|------------------------------------|-----------|--------|
| VPS per esecuzione continua | Sync ordini 24/7 | PC locale acceso | ~€5–10/mese | Affidabilità | Sì in sviluppo; no in produzione |
| Storage backup esterno | Backup fuori sede | Disco esterno / cloud personale esistente | €0–5/mese | Continuità | Sì temporaneamente |
| Dominio + email | Contatti, GPSR, negozio | — | ~€10–20/anno | Credibilità, obblighi informativi | No per la vendita |
| BigBuy (API) | Catalogo UE senza dazi | CSV/inserimento manuale | ~€52–149/mese + attivazione | Consegne UE rapide | Sì |
| Kaufland canone | Canale DE | Allegro senza canone | ~€40/mese | Mercato DE | Sì |
| Cdiscount | Canale FR | — | €39,99/mese | Mercato FR | Sì |
| Amazon Professional | Canale Amazon | — | canone mensile | Traffico | Sì |
| Operatore economico responsabile UE (GPSR) / rappresentante fiscale | Obbligo legale per alcuni prodotti/strutture | Fornitore UE che copre il ruolo | variabile | Conformità | **No**, per prodotti di fabbricanti extra-UE |
| Registrazioni EPR, IVA estere, commercialista | Obblighi per paese | — | variabile | Conformità | No per vendere |
| Servizi trend/dati a pagamento | Market Radar più ricco | Dati da API ufficiali gratuite | variabile | Qualità segnali | Sì |
| Pubblicità | Traffico negozio proprio | Vendita organica su marketplace | budget da decidere | Volume | Sì sui marketplace |

**Regola:** un free trial non è una soluzione gratuita permanente. Ogni attivazione a pagamento richiede
approvazione esplicita dell'operatore e una voce in `cost_ledger`.
