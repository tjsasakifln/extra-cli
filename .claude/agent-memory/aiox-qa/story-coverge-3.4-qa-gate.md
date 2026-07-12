---
name: story-coverge-3.4-qa-gate
description: CONCERNS verdict for COVERAGE-3.4 — 1110/1264 entities uninvestigated, heuristic-only approach
metadata:
  type: project
---

**Fact:** Story COVERAGE-3.4 (Coverage Validation & Residual Documentation) received **CONCERNS** verdict on QA Gate (2026-07-11).

**Why:** AC2/AC7 were partially unmet. The story mandates individual per-entity investigation (Google search, DOM-SC check, CNPJ check, max 5 min/entity). Implementation used heuristic batch categorization via `NATUREZA_CAUSA_HEURISTIC` mapping only 8 of ~28 `natureza_juridica` types. Result: 1110 of 1264 uncovered entities (87.8%) have `causa_raiz = "nao_investigado"`. Risk mitigation (sampling top 50 municipios) from the story was not applied either.

**How to apply:** For stories with investigation components, ensure the protocol is executed on at least a statistically significant sample when scope exceeds estimates. The DoD checklist should reflect actual implementation approach. Ruff lint F541 issues should be auto-fixed before PR.

**Related:** [[story-COVERAGE-3.4-deliverables]] — CSV, report, dashboard, and INDEX.md are all complete and functional.
