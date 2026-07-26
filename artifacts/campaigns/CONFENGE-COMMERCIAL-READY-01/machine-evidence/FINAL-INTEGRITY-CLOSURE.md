# FINAL INTEGRITY CLOSURE — CONFENGE-COMMERCIAL-READY-01

Generated: `2026-07-26T17:09:31Z`

## Terminal

```
BLOCKED_ONLY_OFFICIAL_REGISTRY_AND_HUMAN_REVIEW
```

| Field | Value |
|-------|-------|
| status | `BLOCKED` |
| technical_status | `BLOCKED` |
| terminal_reason | `BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE` |

## SHAs

| Field | Value |
|-------|-------|
| current_pr_head_sha | `3ef795ae0caf555710bf7ffb91f816afdd5aa44b` |
| final_integrity_code_freeze_sha | `3ef795ae0caf555710bf7ffb91f816afdd5aa44b` |
| executed_code_sha | `3ef795ae0caf555710bf7ffb91f816afdd5aa44b` |
| workflow_head_sha | `3ef795ae0caf555710bf7ffb91f816afdd5aa44b` |
| evidence_commit_sha | (pending artifact-only commit) |
| match_run_to_head | `True` |
| non_artifact_files_changed_after_execution | `[]` |

## CI

| Layer | Status | Run ID |
|-------|--------|--------|
| Structural CI | `PASS` | `None` |
| Real-data CI | `NOT_EXECUTED` | `None` |

Workflow jobs renamed: Structural Historical/Registry/E2E/Human Evaluation Checks vs Real Historical/Registry/Full Pipeline E2E/Snapshot Restore/Human Package Publication/Final Evidence Integrity. Real-data jobs never treat exit 2 as success; when DSN secrets missing they report **NOT EXECUTED**.

## Snapshot

- rows: `11974`
- observation_days: `718`
- status_distribution: `{"ACTIVE": 7532, "COMPLETED": 4442, "CANCELLED": 0, "TERMINATED": 0, "SUSPENDED": 0, "UNKNOWN": 0}`
- restore: `PASS` rows_restored=`11974`

## Registry

- candidate universe: `5640`
- official coverage: `0.05319148936170213` (~5.32%)
- operational coverage: `None`
- residual machine blocker: `BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE`

## E2E

- full_pipeline_e2e: `PASS` (starts from raw snapshot discovery)
- downstream: `PASS` (frozen universe only)
- discovery re-executed both passes: `True`

## Corpus

- n_total: `538`
- version: real-v2
- human_labels_filled: `False`
- scarce strata declared (no fabrication): see scarcity_declarations in JSON

## Human review packages

- generated: `True`
- published as workflow artifact: `False` (requires Actions upload of `confenge-human-review-packages`)
- package dir: `artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/human-review/`
- bound executed_code_sha: `3ef795ae0caf555710bf7ffb91f816afdd5aa44b`

## Offer

- distribution: `{'licitacoes_propostas': 8, 'diagnostico_b2g': 12}`
- sensitivity change rates: `{'near_expiry': 0.0, 'concurrent_portfolio': 0.0, 'agency_concentration': 0.0, 'contract_concentration': 0.0}`
- diagnose.block: `None`
- sensitivity status: `PASS`
- discrimination status: `PASS`

## Remaining blockers

**Machine:** ['BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE']

**Human:** ['BLOCKED_REAL_HOLDOUT_NOT_REVIEWED', 'BLOCKED_INSUFFICIENT_HUMAN_LABELS', 'BLOCKED_PENDING_HUMAN_ACCEPTANCE']

## Answers (12)

1. Código executado == congelado? **True**
2. Alteração não documental após execução? **False**
3. SHAs com semântica coerente? **True**
4. Descoberta reexecutada nas duas passagens E2E? **True**
5. Downstream completo reexecutado? **True**
6. Pacotes humanos disponíveis para download (workflow artifact)? **False** (local ready; upload via CI job)
7. Evidência de restore disponível? **True**
8. Corpus representa principais FPs? **True**
9. Gate de oferta ainda tem diagnostic block? **None**
10. CI estrutural vs real separadas? **True**
11. Cobertura oficial integral? **False**
12. Único blocker técnico restante? **`BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE`**

## Gate summary

```json
{
  "sha_semantics": "PASS",
  "cross_artifact_consistency": "PASS",
  "full_pipeline_e2e": "PASS",
  "downstream_reproducibility": "PASS",
  "offer_sensitivity": "PASS",
  "offer_discrimination": "PASS",
  "snapshot_history": "PASS",
  "snapshot_restore": "PASS",
  "registry_selection_independence": "PASS",
  "real_corpus_stratification": "PASS",
  "human_review_package": "PASS_LOCAL_READY_AWAITING_WORKFLOW_UPLOAD"
}
```
