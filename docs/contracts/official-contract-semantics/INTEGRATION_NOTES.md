# Integration notes

- Superfície exclusiva: `scripts/official_contract_semantics/**`, `tests/official_contract_semantics/**`, `data/contracts/fixtures/official_semantics/**`, `docs/contracts/official-contract-semantics/**`.
- Import permitido: `scripts.contract_comparables`, `scripts.contract_publication`, `scripts.process_documents.models.DocumentRecord`.
- Projeção #415: `valor_global` e `valor_contratado` → `valor_integral_nominal` somente no exportador. A observação original conserva a semântica da fonte.
- Projeção #414: snapshot `contract-publication-snapshot/1.0` + `coverage` + `hold_report`. `authorizes_publication` e `authorizes_indexation` permanecem false.
- Integração futura (fora desta campanha): apontar o canário SC para o JSONL desta camada em vez de `pncp_supplier_contracts` cru.
