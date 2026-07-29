# EXTRA-FIRST-CLIENT-DECISION-DELIVERY-01 — historical evidence only

## Classification

**HISTORICAL_BLOCKED_EXTERNAL**

The sanitized pack under `extra-first-20260728T123450Z-4fce77ba22/` was generated from
weekly `weekly-20260727T063446Z-0d158e9c60` with **`exit_code=2`**.

Under current D1 policy (`scripts/ops/extra_first_client_delivery.py`):

- weekly `exit_code != 0` → terminal state **`BLOCKED_EXTERNAL`** (process exit 3)
- never **`BUNDLE_READY_FOR_HUMAN_MERGE`**
- never proof of market absence
- never DOD promotion evidence
- never client-facing delivery

## Allowed uses

- Operator diagnosis of the pre-horizon / pre-fail-closed weekly failure
- Regression narrative (why open-tenders horizon + fail-closed were required)

## Forbidden uses

- Presenting to Leonardo / Extra as the first decision package
- Claiming zero opportunities as market absence
- Promoting any DOD item
- Citing as post-correction operational proof

The first **usable** client package must come from a post-merge weekly with
`exit_code=0` on the code after this PR is merged.
