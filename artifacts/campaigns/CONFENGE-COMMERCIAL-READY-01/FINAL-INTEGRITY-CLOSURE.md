# FINAL INTEGRITY CLOSURE — CONFENGE-COMMERCIAL-READY-01

Generated: 2026-07-30T14:46:39Z
Aggregator: `build_final_campaign_status()`

## Terminal

| Field | Value |
|-------|-------|
| status | `BLOCKED` |
| technical_status | `BLOCKED` |
| terminal_reason | `BLOCKED_CODE_EXECUTION_SHA_MISMATCH` |
| terminal_declaration | `BLOCKED_CODE_EXECUTION_SHA_MISMATCH` |
| code_merge_ready | `False` |
| commercial_release_ready | `False` |

## SHAs

| Field | Value |
|-------|-------|
| pr_head_sha | `26d32410395ddef1d8babdb853617132372bb230` |
| workflow_merge_sha | `None` |
| executed_code_sha | `d469b87bf16df033e80e69ee706d96e400c87340` |
| final_integrity_code_freeze_sha | `d469b87bf16df033e80e69ee706d96e400c87340` |
| match_run_to_head | `False` |
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
| **Real-data CI (aggregate)** | **`NOT_EXECUTED`** |

## Residual blockers

Machine: `BLOCKED_CODE_EXECUTION_SHA_MISMATCH`, `BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE`

Human: `BLOCKED_REAL_HOLDOUT_NOT_REVIEWED`, `BLOCKED_INSUFFICIENT_HUMAN_LABELS`, `BLOCKED_PENDING_HUMAN_ACCEPTANCE`

all_other_machine_blockers: ['BLOCKED_CODE_EXECUTION_SHA_MISMATCH']
