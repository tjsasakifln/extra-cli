# Evidence — docs definition consistency (DoD §25 residual)

**Story:** ROI-cand-dyn-slice-a41d7a2033b7  
**Cycle:** cyc-2026-07-18T130315Z  

## Items
- Nenhum documento promete capacidade fora do escopo
- README, PRD, DOD, manifests e relatórios usam as mesmas definições
- Números conflitantes são eliminados ou contextualizados historicamente

## Proof
- `scripts/ops/scan_docs_definition_consistency.py` exit 0
- `tests/test_docs_definition_consistency.py` 5 passed
