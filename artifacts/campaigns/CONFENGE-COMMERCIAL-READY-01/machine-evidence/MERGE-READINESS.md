# MERGE READINESS — CONFENGE-COMMERCIAL-READY-01

Generated: 2026-07-30T14:46:39Z
Aggregator: `build_final_campaign_status()`

## Declaration

```text
BLOCKED_CODE_EXECUTION_SHA_MISMATCH
```

| Field | Value |
|-------|-------|
| code_merge_ready | `False` |
| commercial_release_ready | `False` |
| status | `BLOCKED` |
| terminal_reason | `BLOCKED_CODE_EXECUTION_SHA_MISMATCH` |
| terminal_declaration | `BLOCKED_CODE_EXECUTION_SHA_MISMATCH` |

## SHAs

| Role | Value |
|------|-------|
| actual_pr_head_sha | `26d32410395ddef1d8babdb853617132372bb230` |
| workflow_merge_sha | `None` |
| freeze_sha | `d469b87bf16df033e80e69ee706d96e400c87340` |
| executed_code_sha | `d469b87bf16df033e80e69ee706d96e400c87340` |
| match_run_to_head | `False` |
| artifact_only_diff | `False` |
| non_artifact_changes | `['Makefile', 'artifacts/campaigns/EXTRA-PROFILE-TO-ACTIONABLE-DECISION-01/runs/loop-20260730T123831Z/actionable-all.json', 'artifacts/campaigns/EXTRA-PROFILE-TO-ACTIONABLE-DECISION-01/runs/loop-20260730T123831Z/actionable-summary.json', 'artifacts/campaigns/EXTRA-PROFILE-TO-ACTIONABLE-DECISION-01/runs/loop-20260730T123831Z/decision-loop-state.json', 'artifacts/campaigns/EXTRA-PROFILE-TO-ACTIONABLE-DECISION-01/runs/loop-20260730T123831Z/executive-summary.md', 'artifacts/campaigns/EXTRA-PROFILE-TO-ACTIONABLE-DECISION-01/runs/loop-20260730T123831Z/result.json', 'artifacts/campaigns/EXTRA-PROFILE-TO-ACTIONABLE-DECISION-01/runs/loop-20260730T123831Z/shortlist.json', 'docs/handoffs/extra-cli-strategic-execution-20260730.md', 'scripts/ops/extra_actionable.py', 'scripts/ops/extra_decision_loop.py', 'scripts/ops/extra_decision_review.py', 'scripts/ops/extra_profile.py', 'tests/test_extra_decision_loop.py']` |

## Workflow / artifacts

| Field | Value |
|-------|-------|
| latest_workflow_run_id | `30217720692` |
| latest_workflow_status | `PASS` |
| human_artifact_id | `8636290007` |
| machine_artifact_id | `8636294876` |

## Layer status

| Layer | Status | Evidence |
|-------|--------|----------|
| Structural CI | `PASS` | confenge structural jobs |
| Real historical CI | `NOT_EXECUTED` | confenge-real-historical-evidence |
| Real registry CI | `NOT_EXECUTED` | confenge-real-registry-evidence |
| Real full-pipeline CI | `NOT_EXECUTED` | confenge-real-full-pipeline-e2e |
| Real snapshot restore CI | `NOT_EXECUTED` | confenge-real-snapshot-restore |
| Human package publication | `PASS` | confenge-human-package-publication |
| Machine evidence publication | `PASS` | confenge-machine-evidence-publication |
| Real-data CI (aggregate) | `NOT_EXECUTED` | all four real jobs must PASS |
| Human review | PENDING | dual-review labels |
| Official registry coverage | `0.05319148936170213` | BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE |

## Answers (objective §15)

1. HEAD real da PR: `26d32410395ddef1d8babdb853617132372bb230`
2. Merge SHA Actions: `None`
3. Execução comercial == freeze: `True`
4. Código alterado após freeze: `True`
5. Jobs real-data executados (PASS): `[]`
6. Jobs NOT_EXECUTED: `['real_historical_ci_status', 'real_registry_ci_status', 'real_full_pipeline_ci_status', 'real_snapshot_restore_ci_status']`
7. Publicação de pacotes: `True`
8. Arquivos de status concordam: `True`
9. PR pronta para merge de código: `False`
10. Liberação comercial: `False`

## Residual blockers

Machine: `BLOCKED_CODE_EXECUTION_SHA_MISMATCH`, `BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE`

Human: `BLOCKED_REAL_HOLDOUT_NOT_REVIEWED`, `BLOCKED_INSUFFICIENT_HUMAN_LABELS`, `BLOCKED_PENDING_HUMAN_ACCEPTANCE`
