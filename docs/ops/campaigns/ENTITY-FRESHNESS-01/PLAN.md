# ENTITY-FRESHNESS-01 — Campaign Plan (Canonical Acceptance)

| Campo | Valor |
|-------|-------|
| **ID** | ENTITY-FRESHNESS-CANONICAL-ACCEPTANCE-01 |
| **Base** | `origin/main` @ `d6d9e1984e348d64a669546613e192e4ebf610cd` |
| **Branch** | `goal/entity-freshness-canonical-acceptance` |
| **Worktree** | `wt-entity-freshness-canonical` |
| **Objetivo único** | Freshness **mensurável** por entidade × capability com identidade canônica |
| **Não-objetivo** | 95% freshness / cobertura / recall; VPS; migration 058 |

## Onda Zero

Ver `ACCEPTANCE-MATRIX.md` (Product / Architecture / Data / QA-DevOps).

## Prerequisites

| ID | Descrição | Status |
|----|-----------|--------|
| P1 | Identidade canônica + reconciliação fail-closed | **DONE** |
| P2 | CI obrigatório + manifesto selado + run operacional | **DONE** |

## Waves

1. **Wave-0 fixture** — FRESH/STALE/NEVER/INCOMPLETE×3 + capability isolation + dup/non-canonical → manual review GO.
2. **Full 1093** — set equality vs `load_canonical_universe().included`.
3. **CI + op run + manifest** — evidence sealed.
4. **ADR + HANDOFF + DOD** (serial, DOD last).

## SUCCESS criteria

- Igualdade exata de conjuntos de `entity_id` com universo canônico
- Teste `tests/test_freshness_by_entity.py` no CI crítico
- Comando operacional exit 0 + manifesto com hashes
- Dual report; breaches nominais
- Somente o item de freshness do DOD marcado
- Claims forbidden respeitados

## Comando operacional

```bash
python -m scripts.coverage.freshness_by_entity \
  --seed "Extra - alvos de licitação. R-0.xlsx" \
  --registry data/entity_source_registry.jsonl \
  --output-dir output/coverage \
  --strict \
  --as-of 2026-07-20T12:00:00+00:00 \
  --evidence-manifest docs/ops/campaigns/ENTITY-FRESHNESS-01/evidence/acceptance-manifest.json
```
