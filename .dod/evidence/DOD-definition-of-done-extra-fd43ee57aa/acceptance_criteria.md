# Acceptance — Suíte global completa verde

## Item
DOD: "Suíte global completa verde..."

## Given / When / Then
- Given isolated PostgreSQL compatible with production and all migrations applied from clean state
- When the canonical full suite runs via `python3 -m scripts.ops.run_full_suite` (or CI job Test All (full suite))
- Then exit code is 0, no failed tests, and the job is not skipped
- And a second run on clean/reused isolated DB also exits 0 (no state-order flake)
- And required CI jobs on the PR are green including Test All (full suite)

## Non-goals
- Do not lower thresholds, skip, xfail, or soft-fail to hide defects
- Do not mark DOD checkbox until ACCEPTED on main with CI run ID

## Evidence required
- Local dual-run logs OR CI run ID for Test All (full suite) SUCCESS
- Independent adversarial review note
