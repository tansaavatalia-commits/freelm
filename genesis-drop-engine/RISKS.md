# RISKS — Registro dei rischi

Probabilità (P) e impatto (I): Bassa / Media / Alta.

| ID | Rischio | P | I | Mitigazione | Responsabile |
|----|---------|---|---|-------------|--------------|
| R-01 | **Economia unitaria irrealizzabile**: con dazio UE €3 (dal 2026-07-01), spedizione e commissioni, €3 di profitto netto su un'unità venduta a €6–7 da Cina è quasi impossibile | Alta | Alta | Multipack, fornitori con magazzino UE, selezione paesi, Profit Engine prudenziale; decisione D-010 | Operatore + sistema |
| R-02 | **Conflitto di liquidità**: fornitori prepagati vs payout marketplace ritardati → ordini bloccati con capitale zero | Alta | Alta | Zero-Advance blocca correttamente; ricerca fornitori con termini; decisione D-011 | Operatore |
| R-03 | Interpretazione del dazio (per articolo vs per linea tariffaria) e futuro diritto di gestione | Media | Alta | Modellare entrambe, usare la prudente; verifica ufficiale in Fase 2 | Sistema |
| R-04 | Paese di registrazione non deciso → IVA, idoneità marketplace, obblighi incerti | Alta | Alta | Nessuna assunzione fiscale finale; motore parametrico; decisione D-002 | Operatore + consulente |
| R-05 | Requisito GPSR (operatore responsabile UE) non soddisfatto da fornitori extra-UE | Alta | Alta | Compliance Engine blocca; preferire fornitori che lo garantiscono | Sistema |
| R-06 | Sospensione account marketplace per policy dropshipping (es. Amazon "seller of record") | Media | Alta | Canali compatibili prima; verifica imballi/fatture del fornitore | Operatore |
| R-07 | Accesso API negato o revocato (AliExpress, marketplace) | Media | Media | Connettori indipendenti, fallback CSV/manuale | Sistema |
| R-08 | Dati di prezzo/stock obsoleti → ordini in perdita | Media | Alta | Ricontrollo profitto all'ordine, TTL sui dati, stato di verifica | Sistema |
| R-09 | Qualità del fornitore bassa → resi e chargeback | Media | Alta | Score affidabilità, riserve, campioni di prova (da approvare) | Operatore |
| R-10 | Proprietà intellettuale/contraffazione | Media | Alta | Filtri marchi, revisione manuale, blocco | Sistema + operatore |
| R-11 | Fuga di credenziali | Bassa | Alta | `SECURITY.md` §1, gitleaks, cifratura | Sistema |
| R-12 | Errore di automazione che genera ordini/pagamenti indesiderati | Bassa | Alta | Livelli di automazione, limiti, outbox con approvazione, kill switch | Sistema |
| R-13 | Free tier LLM limitato o variabile | Media | Bassa | `freelm` failover; generazione asincrona; fallback manuale | Sistema |
| R-14 | Repository attuale non dedicato (`freelm`) | Alta | Bassa | Spostamento in repo privato dedicato (D-001) | Operatore |
| R-15 | Regole polacche di fatturazione elettronica (KSeF) su Allegro | Media | Media | Verifica in Fase 3 prima di scegliere Allegro come primo canale | Operatore |
| R-16 | Complessità eccessiva prima di validare il modello | Media | Media | Roadmap con MVP verticale e milestone verificabili | Sistema |
