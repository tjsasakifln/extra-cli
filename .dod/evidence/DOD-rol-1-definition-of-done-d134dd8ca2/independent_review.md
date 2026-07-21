# Independent adversarial review — O tempo total de execução é registrado.

| Field | Value |
|-------|-------|
| **Item** | `DOD-rol-1-definition-of-done-d134dd8ca2` |
| **Requirement (DOD.md L919)** | O tempo total de execução é registrado. |
| **Reviewer** | adversarial-qa-continue-03 |
| **Reviewed at (UTC)** | 2026-07-21T23:45:00Z |
| **main_sha** | `432da028f1fed7d70d9d489e689cf3afa350571d` |
| **Verdict** | **PASS_FOR_ACCEPT** |

## Falsification attempts

| Attack | Result |
|--------|--------|
| `proof.json` has `"wall_clock_ms": null` → not recorded? | **Pack quality bug only.** Actual reproof ledger `ledger-meta.json` has `wall_clock_ms: 449.60…`; snap/reports ledgers also have positive wall_clock_ms. `RunRecord.wall_clock_ms` is always set in `_save_final_ledger`. |
| Unit-only without ledger field? | Test asserts `last.get("wall_clock_ms", 0) > 0` after real CLI run. |
| Confusion with §30 "O tempo do golden path é medido"? | Separate open item (L1534). This item is registration of total runtime on the run record. |

## Evidence accepted

- `wall_clock_ms` on every reproof ledger run object
- Wired in `RunRecord` + `_save_final_ledger`

## Residuals

- Coordinator `proof.json` null field should not be trusted alone — use ledger body
- Per-step `duration_ms` exists but is not required by this item

## Decision

**PASS_FOR_ACCEPT** — total execution time is registered on the ledger run.
