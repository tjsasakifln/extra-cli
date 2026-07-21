# Independent adversarial review — exit code não zero em gate obrigatório.

| Field | Value |
|-------|-------|
| **Item** | `DOD-rol-1-definition-of-done-3500c05a66` |
| **Requirement (DOD.md L916)** | O golden path retorna exit code não zero em qualquer gate obrigatório. |
| **Reviewer** | adversarial-qa-continue-03 |
| **Reviewed at (UTC)** | 2026-07-21T23:45:00Z |
| **main_sha** | `432da028f1fed7d70d9d489e689cf3afa350571d` |
| **Verdict** | **PASS_FOR_ACCEPT** |

## Falsification attempts

| Attack | Result |
|--------|--------|
| Pure function never wired to CLI? | **Falsified.** `main` calls `evaluate_run_outcome(...)` and uses returned `exit_code` (≈L2288–2345). Module docstring documents exits 0–5. |
| Only unit tests, no CLI subprocess fail? | Residual true: suite tests pure `evaluate_run_outcome` for essential_fail→2 and freshness_fail→3 only. Report fail→4 and empty→1 are implemented but not covered by this module's tests. |
| "qualquer gate" overclaim? | Strict path covers essential sources, freshness, mandatory reports, empty data. Non-essential degraded returns 5. Sufficient for literal mandatory-gate fail-closed. |
| CI skip masking? | 11 passed local with real DB for suite; exit-code tests are pure (no skip risk). |

## Evidence accepted

- `evaluate_run_outcome` strict branch: essential_fail→2, freshness_fail→3, report_fails→4, empty→1
- Wired into production `main` summary/exit
- Impl on main via PR #85

## Residuals (non-blocking for accept)

- No integration test that spawns CLI with forced gate failure
- Report-gate exit 4 not in `test_golden_path_ledger_meta.py` matrix
- Does not claim full-path live fail demonstration on this campaign

## Decision

**PASS_FOR_ACCEPT** — fail-closed non-zero exits on mandatory gates are implemented and unit-proven for core gates; residual test gaps documented.
