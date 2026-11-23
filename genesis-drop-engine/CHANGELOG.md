# CHANGELOG

Formato basato su Keep a Changelog. Versioni SemVer a partire dal primo codice.

## [Non rilasciato]

### Aggiunto — 2026-11-23 (Fase 2, M2.0 parziale + M2.1 dominio)
- Scaffolding Python 3.12+: pyproject, ruff, mypy strict, pytest, hypothesis, import-linter, CI dedicata.
- `core`: Money (centesimi interi, niente float), FX con margine prudenziale, Provenance, Clock, hashing.
- `policy`: RuleSet versionato con i valori approvati (€1, €3, multipack, fondo €100), GateResult.
- Profit Engine: tre scenari, gate BR-001/004/010/011, dazio UE €3 (interpretazione prudente), confronto multipack.
- 36 test (unità + property-based), tutti superati.

### Modificato — 2026-11-20
- Registrate le approvazioni dell'operatore: D-001 (resta in `freelm`), D-003, D-010, D-011 (fondo €100).

### Aggiunto — 2026-11-20 (Fase 1)
- Documentazione iniziale: README, MASTER_SPECIFICATION, BUSINESS_RULES, ARCHITECTURE, DATABASE,
  SUPPLIERS, MARKETPLACES, SECURITY, TESTING, COST_CONTROL, RISKS, DECISIONS, ROADMAP,
  PROJECT_STATUS, NEXT_TASK, CHANGELOG.
- Ricerca su fornitori (CJdropshipping, AliExpress, BigBuy, Syncee, Spocket, Alibaba, Printful) e
  marketplace europei (Allegro, Kaufland, Amazon, Cdiscount, WooCommerce, Shopify).
- Analisi di fattibilità illustrativa con dazio UE €3 (in vigore dal 2026-07-01).
