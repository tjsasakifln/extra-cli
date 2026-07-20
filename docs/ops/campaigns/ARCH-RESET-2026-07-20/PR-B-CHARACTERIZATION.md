# PR B — Characterization notes

**Branch:** `test/architecture-characterization`  
**Base:** `origin/main` @ `d6d9e19`  
**Intent:** Lock weekly pipeline boundaries without changing product behavior.

## What is characterized

| Contract | Test |
|----------|------|
| `make extra-weekly` → `scripts.ops.weekly_cycle --strict` | `test_makefile_extra_weekly_points_to_weekly_cycle_module` |
| `canonical-entry-points.yaml` weekly command | `test_canonical_entry_points_yaml_marks_weekly` |
| Competing Make targets still present | `test_competing_make_targets_still_exist_but_are_not_extra_weekly` |
| CLI seams `--strict` / `--offline` | `test_cli_parser_exposes_strict_and_offline_seams` |
| Stage name seams for strangler | `test_stage_boundary_names_stable_for_strangler` |
| Partial collect ≠ EXIT_OK | `test_partial_collect_never_exit_ok_strict` |
| Freshness fail-closed | `test_freshness_fail_closed_for_partial` |
| No DB → EXIT_TECH + cycle ids | `test_run_weekly_without_db_is_tech_fail_and_has_ids` |
| Distinct run ids | `test_two_offline_cycles_get_distinct_cycle_ids` |
| Forbidden claim list | `test_forbidden_claims_always_listed` |

## Explicitly not changed

- No weekly_cycle production logic edits
- No Makefile reclassification (reserved for PR C)
- No DoD flips
- No dependency adoption

## Next (PR C)

Reclassify `run-pipeline` / `golden-path` as legacy/diagnostic without breaking these characterization tests (update tests only when intentional).
