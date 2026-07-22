# Independent adversarial review v1.3 (final)

| Field | Value |
|-------|-------|
| reviewer_agent | adversarial-qa-skeptic-shell |
| review_session | v1.3-final |
| reviewed_commit | `ed7be1c94b7497fef92073f90d024ff132a0a119` |
| generated_at | 2026-07-22T03:58:30.758084+00:00 |
| verdict | **PASS_FOR_MERGE** |
| transcript_dir | session scratch review-v1.3-transcripts/ |

## Attacks (20 mandated + live + pytest)

| # | Attack | Result | Command | Detail |
|---|--------|--------|---------|--------|
| 1 | 01_schema_outsider_not_zero | PASS | `compute outsider obs` | entity_id_outside_canonical_universe: obs capability=open_tenders entity_id=outsider |
| 2 | 02_query_presence_outsider | PASS | `compute presence outsider` | entity_id_outside_canonical_universe: presence capability=open_tenders entity_id=outsider |
| 3 | 03_cnpj_hash_failclosed | PASS | `build_universe_identity hash` | raised |
| 4 | 04_outsider_ignored | PASS | `outsider only` | entity_id_outside_canonical_universe: obs capability=open_tenders entity_id=outsider |
| 5 | 05_hash_same_count_diff_ids | PASS | `ids hash mismatch` | raised |
| 6 | 06_success_with_data_no_persist | PASS | `persisted=0` | no_records_persisted |
| 7 | 07_success_zero_403_message | PASS | `403 in message` | error_signal:403 |
| 8 | 08_no_evidence_reference | PASS | `empty evidence_reference` | missing_evidence_reference |
| 9 | 09_required_source_missing | PASS | `no pncp` | missing |
| 10 | 10_complementary_not_required | PASS | `dom_sc only` | ['pncp'] |
| 11 | 11_unknown_not_hiding_pending | PASS | `never_checked` | 1 |
| 12 | 12_single_cap_pipeline | PASS | `single capability` | False/NOT_EVALUATED/False |
| 13 | 13_tenders_not_contracts | PASS | `tenders only` | ok |
| 14 | 14_contracts_not_tenders | PASS | `contracts only` | ok |
| 15 | 15_stale_numerator | PASS | `stale` | stale |
| 16 | 16_no_or_true | PASS | `scan tests` | clean |
| 17 | 17_state_reconciliation | PASS | `partition` | recon |
| 18 | 18_mapping_failure_cap_measurement | PASS | `identity cap measurement` | report=False caps=[False, False] |
| 19 | 19_table_absent_enum | PASS | `PresenceStatus` | table_absent distinct from no_rows |
| 20 | 20_no_except_pass | PASS | `scan dual module` | no bare pass |
| 21 | 21_live_identity_and_cap_meas | PASS | `live dual both` | report=False map=identity_unresolved caps=[False, False] |
| 22 | 22_pytest | PASS | `pytest dual` | ......................................                                   [100%]
38 passed  |

Total=22 failures=0

Non-claims: no 95%, no LOCAL_READY.
