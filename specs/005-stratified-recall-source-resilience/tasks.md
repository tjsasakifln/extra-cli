# Tasks — Spec 005

- [x] T01 Harden `recall_benchmark` fail-closed (status, floors, hash, exit)
- [x] T02 Expand adversarial unit tests
- [x] T03 Independent inventory collector
- [x] T04 Makefile gates (campaign-gate / RC / verify-isolated)
- [x] T05 Campaign gate/verify/RC modules
- [x] T06 Collect + freeze gold sample (≥50, ≥5/stratum)
- [x] T07 Spec kit (spec/plan/tasks/checklists/analyze/converge)
- [x] T08 Capture window into isolated DB + match + recall artifacts
- [x] T09 Source-health / contracts / misses / operational report / manifest / result
- [ ] T10 Independent review findings + critical fixes
- [ ] T11 DevOps merge path (out of agent push authority) + main ACCEPTED

## Traceability FR → code/test/evidence

| FR | Code | Test | Evidence |
|----|------|------|----------|
| FR-01 | recall_benchmark.gate_exit | test_cli_* | recall.json |
| FR-02 | evaluate_sample NOT_READY | test_scaffold_* | baseline |
| FR-03 | evaluate_sample PARTIAL | test_unlabeled_*, test_insufficient_* | recall-unlabeled.json |
| FR-04 | evaluate_sample FAIL | test_global_recall_below_95_*, test_stratum_floor_* | recall.json |
| FR-05 | denominator_hash, freeze_lock | test_denominator_* | sample-lock.json |
| FR-06 | forbidden_proxy_used | test_db_count_proxy_* | methodology |
| FR-07 | independent_inventory | structural | gold-sample.json |
| FR-08 | try_match fail_closed | test_auto_match_fail_closed_* | — |
| FR-09..11 | inventory strata | sample-validation | gold-sample |
| FR-12 | campaign verify + report | gate | artifacts/* |
| FR-13 | Makefile/CI notes | gate G3 | plan.md |
