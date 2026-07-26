# FINAL EVIDENCE CLOSURE — CONFENGE-COMMERCIAL-READY-01

Generated: 2026-07-26T20:01:16Z
Aggregator: `build_final_campaign_status()`

## Terminal

| Field | Value |
|-------|-------|
| status | `BLOCKED` |
| technical_status | `BLOCKED` |
| terminal_reason | `BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE` |
| terminal_declaration | `BLOCKED_ONLY_OFFICIAL_REGISTRY_AND_HUMAN_REVIEW` |

## SHAs

| Field | Value |
|-------|-------|
| pr_head_sha / current_pr_head_sha | `6dcab34860fb016aa1ef3152db4d9b0ae97adae6` |
| workflow_merge_sha | `None` |
| checked_out_sha | `6dcab34860fb016aa1ef3152db4d9b0ae97adae6` |
| executed_code_sha | `adc59faf6e4a204e545d401810601ebfa1f8bdb0` |
| final_integrity_code_freeze_sha | `adc59faf6e4a204e545d401810601ebfa1f8bdb0` |
| match_run_to_head | `False` |
| code_changed_after_execution | `False` |
| artifact_only_commits_after_execution | `True` |

## CI (layered)

| Layer | Status |
|-------|--------|
| GitHub workflow | `PASS` |
| Structural CI | `PASS` |
| Real historical CI | `NOT_EXECUTED` |
| Real registry CI | `NOT_EXECUTED` |
| Real full-pipeline CI | `NOT_EXECUTED` |
| Real snapshot restore CI | `NOT_EXECUTED` |
| Human package publication | `PASS` |
| Machine evidence publication | `PASS` |
| Real-data CI (aggregate) | `NOT_EXECUTED` |

## Machine blockers

- `BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE`

## Human blockers

- `BLOCKED_REAL_HOLDOUT_NOT_REVIEWED`
- `BLOCKED_INSUFFICIENT_HUMAN_LABELS`
- `BLOCKED_PENDING_HUMAN_ACCEPTANCE`

## Commercial

- commercial_status: `BLOCKED_PENDING_HUMAN_ACCEPTANCE`
- code_merge_ready: `True`
- commercial_release_ready: `False`
- Official registry coverage: `0.05319148936170213`
