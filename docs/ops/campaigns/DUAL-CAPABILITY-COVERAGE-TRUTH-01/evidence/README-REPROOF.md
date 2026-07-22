# Dual reproof evidence pointer

`dual-reproof-summary.json` is the **canonical live dual snapshot** for campaign
stamp consistency. Its `git_sha` must be an **ancestor of (or equal to)
`origin/main`** and must carry the honest identity state. Docs-only merges may
advance HEAD without forcing a restamp loop; the gate checks ancestry + metrics.

**Refresh command:**

```bash
git rev-parse origin/main
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"
export REQUIRE_REAL_DB=1
python3 -m scripts.coverage.dual_capability_coverage --capability both --output-dir output/coverage
cp output/coverage/dual-capability-coverage-summary.json \
  docs/ops/campaigns/DUAL-CAPABILITY-COVERAGE-TRUTH-01/evidence/dual-reproof-summary.json
python3 docs/ops/campaigns/DUAL-CAPABILITY-COVERAGE-TRUTH-01/scripts/check_campaign_stamp_consistency.py
```

Current closure snapshot (2026-07-22, evidence `86cb02856a3c76c5dd13ef64188453728e10dc82`):

| Field | Value |
|-------|-------|
| evidence git_sha | `86cb02856a3c76c5dd13ef64188453728e10dc82` |
| measurement_success | false |
| coverage_gate_pass | false |
| pipeline_success | false |
| dual_gate_status | NOT_READY |
| mapping_status | identity_unresolved |
| identity_unresolved_count | 4 |
| ambiguous_cnpj8 | 00394494 |
| open_tenders | den=1093 num=0 never=1093 cap_meas=false |
| historical_contracts | den=1093 num=0 never=1093 presence=0.0915% cap_meas=false |

Gate script: `scripts/check_campaign_stamp_consistency.py` (exit 0 required for docs closure).
