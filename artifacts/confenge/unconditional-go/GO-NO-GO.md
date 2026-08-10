# GO / NO-GO — Unconditional CONFENGE email pilot

Generated: `2026-08-10T07:21:12Z`

## Terminal state

### `GO_FOR_REAL_CONFENGE_EMAIL_PILOT`

All controllable engineering gates for the EMAIL_ONLY pilot are satisfied on production SHAs.

This is **not** `EXTERNAL_BLOCKER_REQUIRES_TIAGO`: remaining human action is optional policy unpause of kill-switch, not a missing engineering fix.

## §21 scorecard

| Criterion | Value |
|-----------|-------|
| extra_cli main/host SHA match | **true** `313266f1` |
| warmbly main/host SHA match | **true** `81d83429` |
| clean EMAIL_SEND_READY companies | **50** |
| demo_or_fixture_sendable | **0** |
| tainted_provenance_sendable | **0** |
| wrong_contact first-50 | **0** |
| provenance_chain present | **50/50** |
| clean_cohort_imported_to_production | **true** (`import.status=completed`, `dry_run=false`, `leads_processed=50`) |
| contaminated_cohort_disabled | **true** (demo contacts=0 in DB) |
| smtp_self_smoke | **true** Hostinger → operator mailbox; Unibox synced |
| continuous_imap | **true** (status.sh PASS + Unibox 229 msgs; self-smoke + Re/RES) |
| reply_stop | **true** (inbound replies with `in_reply_to`; REPLY_STOP_FORCE thread present; dispatch paused) |
| outcome_loop | **true** (API ready + status.sh PASS) |
| dispatch_governor | **healthy/paused** (kill-switch, cap=10, auto_send=false) |
| whatsapp | **off** |

## Import (this session)

```text
status=completed dry_run=false leads_processed=50 invalid=0
unchanged=50 (idempotent re-import of V8 after prior create/update)
```

## Residual honesty

1. Target-fit plane on host is **SHADOW** (`TARGET_CONFIRMED` in shadow store); `confenge_company_target_fit_current` rowcount=0. Send-readiness accepts SHADOW CONFIRMED.
2. Kill-switch remains **engaged** — commercial dispatch will not fire until an operator clears it.
3. GREEN autorun remains **OFF**.

## Operator-only (policy, not engineering blocker)

When ready for live pilot volume: clear `/data/confenge-ops/kill-switch` / resume dispatch under EMAIL_ONLY 10/h business hours. Not required to claim engineering GO.
