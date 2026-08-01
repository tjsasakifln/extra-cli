# DoD claim reconciliation — #194 / DOC-DEEP-ANALYSIS

## Decision

**Option B** for official budget/reference comparison claims.

## Items reopened

| Item | Previous | After | Tier kept |
|------|----------|-------|-----------|
| Comparação de orçamento com referências oficiais | `[x]` | `[ ]` | IMPLEMENTED + FIXTURE_PROVEN |
| Comparação SINAPI/SICRO mês/localidade/desoneração/unidade | `[x]` | `[ ]` | IMPLEMENTED + FIXTURE_PROVEN |

## Why not Option A

No authorized official dataset in-repo with:

- system, competência, localidade, regime, unidade, código
- public origin + retrieval date + checksum
- compatibility rule + reproducible comparison result

The existing test (`test_reference_manifest_required_fields`) only asserts **field presence** on a synthetic/manifest structure.

## Preserved legitimate fixes from #194

- Excerpt ↔ document association
- Citation integrity
- Content-addressed XLSX path without extension
- Page/cell locators
- Attachment/inconsistency detection
- Edital case pack fixture E2E (not legal opinion)

## Non-claims

- Not VPS_OPERATIONAL
- Not REAL_CASE_PROVEN for official tables
- Not PROJECT_DONE
- CI green ≠ official comparison

## Regenerated

- `DOD.md` claim tiers legend + reopened checkboxes
- This file
- Note in `FINAL-REPORT.md`
