# GO / NO-GO — Unconditional CONFENGE email pilot

Generated: `2026-08-10T04:59:40Z`

## Terminal state

```text
EXTERNAL_BLOCKER_REQUIRES_TIAGO
```

All controllable engineering gates for a real EMAIL_ONLY pilot are satisfied.
The sole remaining non-automatable step is **human review approval** of the stratified clean sample (policy forbids machine-minted `HUMAN_REVIEW_APPROVED`).

## Engineering vector (§21) — controllable bits

| Boolean | Value |
|---------|-------|
| extra_cli_ci_green (merged #213+#212) | **true** |
| warmbly_ci_green (merged #35) | **true** |
| extra_cli_main_deployed_sha_match | **true** (`c7fadc19`) |
| warmbly_main_deployed_sha_match | **true** (`81d83429`) |
| target_fit_runtime_healthy | **true** (SHADOW, lag 0s) |
| target_fit_fresh | **true** |
| clean_email_send_ready_companies | **53** |
| demo_or_fixture_sendable | **0** |
| tainted_provenance_sendable | **0** |
| first-50 audit counters | **all 0** |
| clean_cohort_imported_to_production | **true** (53 updates) |
| contaminated_cohort_disabled | **true** |
| smtp_self_smoke (operator only) | **true** (task completed) |
| whatsapp | **off** |
| kill_switch | **ENGAGED** |

## Human gate (only remaining)

1. **Action:** Review `artifacts/confenge/unconditional-go/HUMAN-REVIEW-SAMPLE.md` and record real decisions (`reviewer`, `reviewed_at`, `decision`, `evidence_inspected`).
2. **Where:** local `extra-cli` checkout of that path (or decisions JSONL beside it).
3. **Done when:** ≥1 real `HUMAN_REVIEW_APPROVED` with human identity (not grok/ci/script).
4. **Resume:**
```bash
cd /mnt/d/extra-cli && git pull origin main
# after decisions recorded, pilot can run EMAIL_ONLY 10/h with kill switch available
```

## Historical contaminated evidence — DO NOT REUSE

Prior ESR=62 / WRONG_CONTACT=0 / NEW-30-HUMAN-REVIEW invalidated: `INVALIDATED_REASON=PROVENANCE_CONTAMINATION`.
