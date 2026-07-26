# FINAL INTEGRITY CLOSURE — CONFENGE-COMMERCIAL-READY-01

Generated: `2026-07-26T17:11:31Z`

## Terminal

```
BLOCKED_ONLY_OFFICIAL_REGISTRY_AND_HUMAN_REVIEW
```

| Field | Value |
|-------|-------|
| status | BLOCKED |
| technical_status | BLOCKED |
| terminal_reason | BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE |

## SHAs

| Field | Value |
|-------|-------|
| current_pr_head_sha | `5c8c796163574a8988b7a6d67d287438e75ced35` |
| final_integrity_code_freeze_sha | `5c8c796163574a8988b7a6d67d287438e75ced35` |
| executed_code_sha | `5c8c796163574a8988b7a6d67d287438e75ced35` |
| match_run_to_head | `True` |
| non_artifact after execution | `[]` |

## CI

| Layer | Status |
|-------|--------|
| Structural CI | PASS |
| Real-data CI | NOT_EXECUTED |

## Snapshot / restore

- rows: 11974, observation_days: 718
- restore ok: True, rows_restored: 11974

## Registry

- universe: 5640
- official coverage: 0.05319148936170213
- operational: 100%

## E2E

- full pipeline (from discovery): **PASS**
- downstream (frozen universe): **PASS**

## Corpus

- n_total: 538, real-v2, human labels empty

## Offer

- distribution: {'licitacoes_propostas': 8, 'diagnostico_b2g': 12}
- sensitivity: {'near_expiry': 0.0, 'concurrent_portfolio': 0.0, 'agency_concentration': 0.0, 'contract_concentration': 0.0}
- diagnose.block: None

## Human packages

- generated: true
- workflow artifact upload: pending Actions (`confenge-human-review-packages`)

## Remaining blockers

Machine: `BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE` only

Human: holdout review, labels, acceptance

## Answers

1. executed == freeze? **True**
2. non-doc change after exec? **False**
3. SHA semantics coherent? **True**
4. Discovery re-run both E2E passes? **True**
5. Downstream re-run? **True**
6. Human packages downloadable via workflow? **False** (local ready; CI upload on next Actions run)
7. Restore evidence available? **True**
8. Corpus FP strata? **True** (n>=538, scarcity declared)
9. Offer internal block? **None**
10. Structural vs real CI separated? **True**
11. Official registry 100%? **False** (0.05319148936170213)
12. Only technical blocker? **BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE**
