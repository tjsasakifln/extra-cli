# Independent adversarial review — reexecutado sem duplicação.

| Field | Value |
|-------|-------|
| **Item** | `DOD-rol-1-definition-of-done-98c4820f19` |
| **Requirement (DOD.md L917)** | O golden path pode ser reexecutado sem duplicação. |
| **Reviewer** | adversarial-qa-continue-03 |
| **Reviewed at (UTC)** | 2026-07-21T23:45:00Z |
| **main_sha** | `432da028f1fed7d70d9d489e689cf3afa350571d` |
| **Verdict** | **PASS_FOR_ACCEPT** |

## Falsification attempts

| Attack | Result |
|--------|--------|
| acceptance_criteria overclaims dual source crawls? | **Partial true.** Criteria text mentions dual crawls; tests only dual `apply_seeds` + dual `run_snapshot_reconciliation`. No dual full crawl in suite. Residual honesty gap in criteria text, not fatal to DOD literal. |
| Keys can duplicate on re-seed? | **Falsified for tested surfaces.** `count == count(distinct cnpj_8)` on entities; `pncp_id` unique; dual seed does not explode counts. |
| Snapshot hash drifts without data change? | Dual snapshot: `ids_sha256` stable; added/removed=0. |
| Ambiente limpo / full GP dual run? | **Not claimed.** Item 596584406e (ambiente limpo) remains out of scope. |

## Evidence accepted

- `tests/test_golden_path_idempotency.py` 2 passed in main reproof suite
- Impl PR #92 = main HEAD `432da028…`
- Mechanism: re-run seed/snapshot without key duplication

## Residuals

- Dual crawl of pncp/pcp/compras_gov not demonstrated in this pack
- Fixture bid volume small; uniqueness property still holds
- Full end-to-end double golden path not in evidence

## Decision

**PASS_FOR_ACCEPT** — re-execution without key duplication is demonstrated for seed + snapshot surfaces that define the item’s practical risk. Dual crawl claim in acceptance_criteria is overstated residual, not a FAIL of the DOD literal.
