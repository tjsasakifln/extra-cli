# Adversarial QA — DUAL-CAPABILITY-SUSTAINED-COVERAGE-95-01-PARALLEL

## Scope
Independent attempt to falsify dual ≥95% claims. Does not implement fixes.

## Checklist results

| Attack | Result | Evidence |
|--------|--------|----------|
| Raw/hash absent still counted | FAIL-CLOSED in unit path | `validate_success_zero` requires evidence_reference + pagination/provenance |
| HTTP 429 as SUCCESS_ZERO | REJECTED | `test_validate_success_zero_rejects_http_429_metadata` PASS |
| Timeout/error tokens | REJECTED | `observation_error_signal` + existing tests |
| Incomplete pages | REJECTED | `test_invalid_success_zero_missing_pagination` |
| Single capability called dual | REJECTED | `test_single_capability_never_pipeline_success`; dual-summary HC scope_complete=false |
| Manual join of different SHAs | INVALID | audit cross_claim_diff sha/as_of/policy diverge |
| Mass SUCCESS_ZERO without ledger | INVALID | 54-entity sample all UNSUPPORTED; floor 1/1093 |
| Denominator shrink | FAIL-CLOSED | expected universe version enforced; empty dual den=1093 both caps |
| Entity dupe | FAIL-CLOSED | `test_duplicate_entity_fail_closed` |
| Draft/fallback policy | FAIL-CLOSED | isolated run policy 2.1.1 active, fallback_used=false |
| Different as_of per capability | N/A blocked | single as_of CLI; joint run uses one stamp |
| CIGA skipped for municipal | Code path requires combinations via policy | no production re-proof under concurrent weekly |
| Contract window <3y | FAIL-CLOSED | `contracts_backfill_ok` |
| Isolated empty DB PASS fabrication | NOT DONE | dual_gate_status=FAIL, 0/1093 both; exit 2 with --require-gate |

## Critical blockers for dual PASS claim

1. **No joint production-backed dual run** this campaign (weekly_cycle concurrent → BLOCKED_CONCURRENT_PRODUCTION).
2. **Prior open_tenders 100%** relies on unproven SUCCESS_ZERO mass (1092) without entity ledger in repo.
3. **Prior historical_contracts 100%** is single-capability (dual_gate NOT_EVALUATED).

## Verdict
**No false dual PASS allowed.** Machinery correctly reports FAIL on empty evidence. Prior 100% claims are **not** joint dual proof.
