# Independent adversarial review — O backfill cobre no mínimo os últimos três anos.

| Field | Value |
|-------|-------|
| **Item** | `DOD-rol-1-definition-of-done-c2443d2b03` |
| **Requirement (DOD.md L752)** | O backfill cobre no mínimo os últimos três anos. |
| **Reviewer** | campaign-independent-review-hc-closure-01 (not primary implementer of verify harness) |
| **Reviewed at (UTC)** | 2026-07-23T20:51:12Z |
| **main_sha** | `5f922114e566e30b123b97ebe9a2e06f2de487ad` |
| **Verdict** | **PASS_FOR_ACCEPT** |

## Falsification attempts

| Attack | Result |
|--------|--------|
| Claim 3y from volume alone (row count) | **Blocked.** Gate uses completed windows + date span, not row count as temporal proof. |
| Incomplete windows marked complete | **Falsified.** Checkpoint total_windows_completed=37 and planned_windows=37; failed windows resumed before completion. |
| Fabricated future windows | **Falsified.** Range 20230720 to 20260723 (span_years approx 3.01). |
| Unit tests only mock | **Residual low.** Window complete tests exercise checkpoint logic; live checkpoint is operational evidence. |

## Evidence accepted

- Checkpoint: 37/37 windows, min_start=20230720, max_end=20260723, span_years>=3.0
- verify_result.json ok with substantive python assert + pytest green (6 tests + 1 command)
- CI main run 30042874795 success on 5f922114e566e30b123b97ebe9a2e06f2de487ad

## Residuals

- Full host reboot residual (PG restart only) — out of scope for this item.
- Off-site backup and soak 7d are separate blockers; not claimed here.

## Decision

PASS_FOR_ACCEPT for temporal backfill coverage of at least three years only.
