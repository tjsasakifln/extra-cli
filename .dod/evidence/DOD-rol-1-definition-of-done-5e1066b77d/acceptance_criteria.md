# O golden path calcula cobertura

## Acceptance (dual measurement)

Given main at merge SHA of dual capability PR with migrations applied
When dual coverage runs via golden_path `--execute-dual-coverage-only` or coverage step
Then method is `dual_capability_coverage`
And both open_tenders and historical_contracts are computed independently
And universe stamps include seed_sha256, canonical_ids_sha256, entity_count
And measurement_success may be true while coverage_gate_pass is false below 95%
And exit overall distinguishes coverage_gate_failed (exit 2) from measurement failure (exit 1)
And legacy any_row / undifferentiated is_covered are forbidden methods
And never_checked/pending/stale aggregates are published (absence of proof is not healthy unknown=0)

## OUT of this acceptance

- Live 95% gate PASS
- LOCAL_READY
- Data backfill completeness
