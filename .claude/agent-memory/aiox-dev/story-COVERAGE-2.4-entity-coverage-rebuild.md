---
name: story-coverage-2.4-entity-coverage-rebuild
description: "COVERAGE-2.4: Entity Coverage Rebuild — migration 021 aplicada, rebuild-coverage CLI, 931/2085 entities covered (44.7%)"
metadata:
  type: project
---

**Story:** COVERAGE-2.4 Entity Coverage Rebuild
**Status:** InReview (implementado 2026-07-11)
**Mode:** YOLO

### Implementado

1. **DB (migration 021, sections 5-10):** v_unmatched_bids, v_coverage_trend, generate_coverage_snapshot(), v_coverage_summary (com match_method), v_coverage_gaps, _migrations tracking
2. **CLI (local_datalake.py):** `rebuild-coverage` subcommand — cascade 3 niveis: direct match (matched_entity_id) → CNPJ-8 fallback → hierarchical (via entity_hierarchy se existir). Idempotent, scoped to active bid sources only.
3. **Validations:** 38/38 tests pass, ruff clean, consistency check OK

### Coverage Result
- 931/2085 entities covered (44.7%)
- pncp: 771 (37.0%), pcp: 35 (1.7%), ciga_ckan: 125 (6.0%)
- 0 inconsistent entities (all bid entities have coverage)

### Key Decisions
- `rebuild-coverage` resets ONLY sources with active bid data in pncp_raw_bids (not all 9 sources) — preserves independent coverage paths like ciga_ckan
- MODE() aggregate used for match_method fallback instead of simple 'direct'
- Hierarchical support detected dynamically (COVERAGE-1.8)
