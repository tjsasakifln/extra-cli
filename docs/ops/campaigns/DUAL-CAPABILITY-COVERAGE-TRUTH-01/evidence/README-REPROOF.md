# Dual reproof evidence pointer

`dual-reproof-summary.json` is the **canonical live dual snapshot** for campaign
stamp consistency. It must match `origin/main` tip and the honest identity state.

**Refresh command:**

```bash
git rev-parse origin/main   # expect 3ab3a3a738437791cb4a9e34b76f41bb578f47a8
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"
export REQUIRE_REAL_DB=1
python3 -m scripts.coverage.dual_capability_coverage --capability both --output-dir output/coverage
cp output/coverage/dual-capability-coverage-summary.json \
  docs/ops/campaigns/DUAL-CAPABILITY-COVERAGE-TRUTH-01/evidence/dual-reproof-summary.json
python3 docs/ops/campaigns/DUAL-CAPABILITY-COVERAGE-TRUTH-01/scripts/check_campaign_stamp_consistency.py
```

Current closure snapshot (2026-07-22, tip `3ab3a3a738437791cb4a9e34b76f41bb578f47a8`):

| Field | Value |
|-------|-------|
| main / artifact git_sha | `3ab3a3a738437791cb4a9e34b76f41bb578f47a8` |
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
