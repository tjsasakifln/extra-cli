---
name: manifest-265pct-coverage-bug
description: Fixed manifest.py 265.95% coverage bug — canonical universe 1093, JOIN filter raio_200km, test_batch exclusion, assertion guards
metadata:
  type: project
---

**Bug:** `_build_manifest()` gerava `pct_entities_with_data = 265.95%` porque:
1. Denominador: `SELECT COUNT(*) FROM sc_public_entities WHERE raio_200km = TRUE` retornava 1448 (DB flag inconsistente com planilha canonica que tem 1093)
2. Numerador: `SELECT COUNT(DISTINCT orgao_cnpj) FROM opportunity_intel` sem filtro `raio_200km` contava 3851 entes de todo SC
3. JOIN do `_build_gaps()` usava `spe.cnpj_8 = oi.orgao_cnpj` (8 chars = 14 chars) — nunca match
4. `generate()` acessava `manifest["coverage"]` em vez de `manifest["universe"]` — coverage_pct sempre 0, exit_code sempre 2
5. `test_batch` (5 registros) nao era filtrado das queries de producao

**Fix applied 2026-07-12/13:**
- Adicionado `CANONICAL_UNIVERSE_WITHIN_200KM = 1093` com provenance documentada (audit doc + planilha seed)
- Numerador agora faz INNER JOIN com `sc_public_entities` filtrando `raio_200km = TRUE`
- JOIN corrigido para `spe.cnpj_8 = LEFT(oi.orgao_cnpj, 8)` no `_build_gaps()`
- `AND source != 'test_batch'` adicionado a todas as queries
- Assertions preventivas: `entities_with_data >= 0`, `total_entities > 0`, `entities_with_data <= total_entities`, `0 <= pct_covered <= 100`, `entities_without_data >= 0`
- Testes: 9 unitarios + 4 integracao (test_manifest.py)

**Result:** Coverage: 42.18% (461/1093), entities_without_data: 632 (positivo). Exit code 2 (abaixo do threshold 95%).

**Files modified:**
- `/mnt/d/extra consultoria/scripts/opportunity_intel/manifest.py`
- `/mnt/d/extra consultoria/tests/test_manifest.py`

**Related:** docs/coverage-truth/fase0-audit-2026-07-12.md (contradicoes C1-C4 resolvidas)
**Why:** The DB flag raio_200km is inconsistent (1448 vs canonical 1093). Using canonical constant avoids reliance on potentially incorrect DB flag.
**How to apply:** When the DB flag is eventually corrected to match the canonical spreadsheet, this constant can be replaced with `SELECT COUNT(*) FROM sc_public_entities WHERE raio_200km = TRUE`.
