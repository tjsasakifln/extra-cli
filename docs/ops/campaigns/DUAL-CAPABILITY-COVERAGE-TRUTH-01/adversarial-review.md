# Adversarial review — dual capability coverage (independent of implementer narrative)

## Attempts

| Attack | Result |
|--------|--------|
| Use any_row / is_covered as method | Forbidden in FORBIDDEN_METHODS; golden_path method fixed to dual_capability_coverage |
| Average two capabilities | No average field; unit tests assert absence |
| Count stale as covered | observation_counts_as_covered returns False for stale |
| Count invalid success_zero | validate_success_zero requires pagination/run_id/timestamps |
| Inflate numerator outside universe | aggregate_capability raises DualCoverageError |
| Tenders prove contracts | Independent obs maps; unit test |
| Contracts prove tenders | Independent obs maps; unit test |
| Presence as coverage | Separate data_presence_* fields; claims_forbidden |
| Silent wrong denominator | expected_denominator mismatch → measurement_success false |
| Gate pass with low coverage | coverage_gate_pass false; require_gate exit 2 |

## Residual risks

1. cnpj8 mapping may leave evidence unmapped → under-count (not inflate)  
2. Default applicability=applicable may be refined later with full registry  
3. Live 95% not proven — correctly FAIL  

## Verdict

**PASS for measurement spine.** Do not accept dual 95% gates without live dual artifacts.
