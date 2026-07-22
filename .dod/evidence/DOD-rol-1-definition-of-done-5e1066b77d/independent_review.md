# Independent review — dual capability coverage calculation (DoD §12.1)

| Field | Value |
|-------|-------|
| **Reviewer** | aiox-qa (Quinn) — independent of implementer |
| **Verdict** | PASS_FOR_ACCEPT (measurement method dual) |
| **reviewed_commit** | `edd76189153a4734381447fe6933bce61d883d4f` (origin/main merge PR #108) |
| **CI main** | run 29887826689 SUCCESS |
| **Campaign review** | PASS_FOR_MERGE after H1 (docs/ops/campaigns/DUAL-CAPABILITY-COVERAGE-TRUTH-01/independent-review-v1.1.md) |

## Scope of acceptance

Accepts only: **O golden path calcula cobertura** under dual definition
(`method=dual_capability_coverage`).

Does **not** accept:

* capability_monitoring_coverage ≥95% (either capability)
* LOCAL_READY / PROJECT_DONE
* legacy 214/1093=19.5791% as canonical

## Attacks / checks performed

1. Fail-open schema/query → fail-closed (classified)
2. Outsider fail-closed
3. Hash validation expected_*
4. success_with_data requires persist
5. success_zero rejects error_message-only 429
6. never_checked published (not unknown=0)
7. Denominators independent; no average
8. H1: obs unknown does not shrink A_C
9. Main reproof: measurement_success=true, gate=false, never=1093 both caps

## Residual MEDIUM (non-blocking for this item)

* Config PNCP draft blanket applicable
* identity_unresolved_count=4 (ambiguous cnpj8) — gates 95% blocked until resolved
* Ops backfill required for 95%

## Decision

**PASS_FOR_ACCEPT** for dual calculation method on main `edd76189153a4734381447fe6933bce61d883d4f`.
