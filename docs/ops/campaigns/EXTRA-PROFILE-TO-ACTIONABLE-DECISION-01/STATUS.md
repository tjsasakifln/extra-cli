# EXTRA-PROFILE-TO-ACTIONABLE-DECISION-01 — STATUS

**Campaign:** EXTRA-PROFILE-TO-ACTIONABLE-DECISION-01  
**Date:** 2026-07-30  
**Branch:** `campaign/extra-profile-to-actionable-decision-01`  
**Base main:** post `#180` + `#179` (`d469b87b…`)

## Objective

Close the Extra loop:

`profile → actionable opportunity → human decision → revisable package`

without inventing capacity, tenders, or human acceptance.

## Delivered (software)

| Capability | Module | Notes |
|------------|--------|-------|
| Profile CLI | `scripts/ops/extra_profile.py` | init / validate / show / intake / stamp / diff |
| Profile hash + provenance | same | `UNKNOWN` / `NOT_PROVIDED` / pending capacity |
| Actionable classifier | `scripts/ops/extra_actionable.py` | strict states; max shortlist 5; `NO_ACTIONABLE_TENDER` |
| Human review CLI | `scripts/ops/extra_decision_review.py` | ACCEPT/REJECT/DEFER; accept-empty; finalize |
| Orchestrator | `scripts/ops/extra_decision_loop.py` | weekly pack → package → `READY_FOR_HUMAN_ACCEPTANCE` |
| Tests | `tests/test_extra_decision_loop.py` | 12 unit tests |

## Terminal states

| State | When |
|-------|------|
| `READY_FOR_HUMAN_ACCEPTANCE` | Package generated; decisions pending or package_decision omitted |
| `PASS_EXTRA_DECISION_LOOP_ACCEPTED` | **Only** after human `finalize --package-decision ACCEPTED*` |

## Canonical commands

```bash
# Profile
python3 -m scripts.ops.extra_profile validate
python3 -m scripts.ops.extra_profile stamp
python3 -m scripts.ops.extra_profile intake
python3 -m scripts.ops.extra_profile show

# Weekly (real lake)
make extra-weekly
# or: python3 -m scripts.ops.weekly_cycle --strict

# Decision loop from weekly pack
python3 -m scripts.ops.extra_decision_loop run \
  --weekly-dir output/weekly/<cycle_id> \
  --out artifacts/campaigns/EXTRA-PROFILE-TO-ACTIONABLE-DECISION-01/runs/<run_id>

# Human review
python3 -m scripts.ops.extra_decision_review list --run-dir <OUT>
python3 -m scripts.ops.extra_decision_review decide <OPP_ID> --run-dir <OUT> \
  --decision ACCEPT --reason "..." --actor tiago
# or empty:
python3 -m scripts.ops.extra_decision_review accept-empty --run-dir <OUT> \
  --reason "Nenhum edital vigente defensável" --actor tiago
python3 -m scripts.ops.extra_decision_review finalize --run-dir <OUT> \
  --actor tiago --package-decision ACCEPTED
```

## Existing reuse (no duplication)

- Canonical profile YAML: `config/client_profiles/extra.yaml` (v3)
- Weekly: `scripts/ops/weekly_cycle.py` / `make extra-weekly`
- Client package (richer PDF/XLSX path): `scripts/ops.extra_first_client_delivery`
- Workspace decide: `python3 -m scripts.workspace decide`

## Live execution (this campaign branch)

| Field | Value |
|-------|-------|
| weekly `cycle_id` | `weekly-20260730T123831Z-8bdf4632d9` |
| weekly `exit_code` | **2** (completed, not consultive-reliable — skip-collect / partial PNCP) |
| decision run | `artifacts/campaigns/EXTRA-PROFILE-TO-ACTIONABLE-DECISION-01/runs/loop-20260730T123831Z` |
| candidates | 5 |
| by_state | all `NO_VERIFIABLE_FUTURE_DEADLINE` |
| result | **`NO_ACTIONABLE_TENDER`** (defensible empty) |
| terminal | **`READY_FOR_HUMAN_ACCEPTANCE`** |
| human | **NOT_PROVIDED** (not forged) |
| profile_hash | `aeaa8551547e167addfff707b642782b71d9526b8b8a8b8aa91b3a8cceaae92f` |

Honest: weekly exit 2 means the pack is technical evidence of the loop, **not** a claim of consultive reliability (`exit_code=0` required for that).

## Honest blockers

1. **Critical capacity still PENDING** on Extra profile (capital, garantia, simultânea, CATs, margem) → GO/ACTIONABLE certainty forced to REVIEW.
2. **Human acceptance NOT_PROVIDED** → cannot claim `PASS_EXTRA_DECISION_LOOP_ACCEPTED`.
3. **Weekly exit_code=2** on local skip-collect run — need fresher open-tender deadlines/source for consultive PASS.
4. Soak **not** modified.

## Soak

`soak_touched: false` — no timer/crawler/lock changes.

## DoD promotion

Do **not** promote operational DoD items that require human acceptance or live weekly evidence until those exist. Software gates are test-backed only.
