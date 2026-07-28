# ADR-023 — Dual capability coverage como autoridade de monitoring

- **Data:** 2026-07-28 (retroativo)
- **Status:** Aceito (as-is no código)
- **Confiança:** 🟢

## Contexto
Existiam múltiplas noções de “cobertura” (`entity_coverage`, artefatos multi-source, contract metrics). Gates comerciais e campanhas precisavam de denominadores honestos por capacidade.

## Decisão
Autoridade de monitoring coverage para capacidades `open_tenders` e `historical_contracts` é `scripts/coverage/dual_capability_coverage.py` + `coverage_evidence` (+ view `v_dual_capability_evidence_latest`). `entity_coverage` permanece legado/diagnóstico.

## Consequências
- Gates dual não podem usar `is_covered` indiferenciado.
- Universe identity e source_policy entram no cálculo.
- Specs e DoD devem citar dual capability, não M-genérico ambíguo.
