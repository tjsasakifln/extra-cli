# Independent adversarial review v1.2 (skeptic remediation)

| Field | Value |
|-------|-------|
| reviewer_agent | adversarial-qa-skeptic (shell-executed, no implementer) |
| reviewed_commit | `30f5548262fb8b89065940b66a98b937e892733a` |
| generated_at | 2026-07-22T03:35:52.071985+00:00 |
| verdict | **PASS_FOR_MERGE** |

## Attacks executed

| Attack | Result | Detail |
|--------|--------|--------|
| outsider_obs | PASS | entity_id_outside_canonical_universe: obs capability=open_tenders entity_id=outsider |
| outsider_presence | PASS | entity_id_outside_canonical_universe: presence capability=open_tenders entity_id=outsider |
| hash_diverge | PASS | raised DualCoverageError |
| same_count_diff_ids | PASS | raised |
| success_with_data_no_persist | PASS | no_records_persisted |
| success_zero_403_message | PASS | error_signal:403 |
| stale_not_covered | PASS | stale |
| single_cap_no_pipeline | PASS | pipe=False dual=NOT_EVALUATED |
| tenders_not_contracts | PASS | ok |
| different_denominators | PASS | ot=3 hc=2 |
| never_checked_published | PASS | 1 |
| no_average_field | PASS | ok |
| identity_mapping_status_priority | PASS | identity_unresolved wins over partial |
| pytest_dual_suite | PASS | ......................................s.                                 [100%]
39 passed, 1 skipped in 3.40s
 |
| live_identity_unresolved_measurement_fail | PASS | status=identity_unresolved meas=False err=identity_unresolved: count=4 ambiguous_cnpj8=['00394494'] |
| live_schema_modern | PASS | modern |

Executed 16 attacks; failures=0.

Non-claims: no 95%, no LOCAL_READY.
