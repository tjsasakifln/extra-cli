# FINAL EVIDENCE CLOSURE — CONFENGE-COMMERCIAL-READY-01

Generated: 2026-07-30T14:46:39Z
Aggregator: `build_final_campaign_status()`

## Terminal

| Field | Value |
|-------|-------|
| status | `BLOCKED` |
| technical_status | `BLOCKED` |
| terminal_reason | `BLOCKED_CODE_EXECUTION_SHA_MISMATCH` |
| terminal_declaration | `BLOCKED_CODE_EXECUTION_SHA_MISMATCH` |

## SHAs

| Field | Value |
|-------|-------|
| pr_head_sha / current_pr_head_sha | `26d32410395ddef1d8babdb853617132372bb230` |
| workflow_merge_sha | `None` |
| checked_out_sha | `26d32410395ddef1d8babdb853617132372bb230` |
| executed_code_sha | `d469b87bf16df033e80e69ee706d96e400c87340` |
| final_integrity_code_freeze_sha | `d469b87bf16df033e80e69ee706d96e400c87340` |
| match_run_to_head | `False` |
| code_changed_after_execution | `True` |
| artifact_only_commits_after_execution | `False` |

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

- `BLOCKED_CODE_EXECUTION_SHA_MISMATCH`
- `BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE`

## Human blockers

- `BLOCKED_REAL_HOLDOUT_NOT_REVIEWED`
- `BLOCKED_INSUFFICIENT_HUMAN_LABELS`
- `BLOCKED_PENDING_HUMAN_ACCEPTANCE`

## Commercial

- commercial_status: `BLOCKED_PENDING_HUMAN_ACCEPTANCE`
- code_merge_ready: `False`
- commercial_release_ready: `False`
- Official registry coverage: `0.05319148936170213`
