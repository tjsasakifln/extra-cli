# FINAL-EVIDENCE-CLOSURE — CONFENGE-COMMERCIAL-READY-01 (PR #144)

Generated: `2026-07-26T15:35:49Z`

## Terminal status

| Field | Value |
|-------|-------|
| status | `BLOCKED` |
| technical_status | `BLOCKED` |
| terminal_reason | `BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE` |

## SHAs

| Field | Value |
|-------|-------|
| PR HEAD (at generation) | `a8070968e92e5a0bb468fada17ae6b806d6a6c40` |
| main SHA | `8344254942ec48978566317df16d7b3e3caabd89` |
| final code freeze SHA | `4dc1ef995672605caec9cf30b885b47fe5bf0e5a` |
| executed code SHA | `4dc1ef995672605caec9cf30b885b47fe5bf0e5a` |

> After this document is regenerated post-commit, HEAD tip is re-synced. Code freeze remains `4dc1ef995672605caec9cf30b885b47fe5bf0e5a` until a new freeze commit.

## Snapshot (historical)

| Metric | Value |
|--------|-------|
| total rows | 11974 |
| observation days | **718** |
| ACTIVE | 7532 |
| COMPLETED | 4442 |
| gate | `PASS` |

## Dump / independent anchor

| Metric | Value |
|--------|-------|
| format | CSV package |
| dump SHA | `566ffa1d74e20cc5efcea65b60d3bf874c3567da70b0e24e08ffe28049f0adb5` |
| identities distinct | `True` |
| pre == post hash | `True` |
| gate | `PASS` |

## Registry

| Metric | Value |
|--------|-------|
| frozen universe | 5640 |
| operational resolution | 1.0 |
| official coverage | 0.05319148936170213 (300/5640) |
| official universe gate | `BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE` |

## E2E

| Metric | Value |
|--------|-------|
| n_universe | **5640** |
| frozen | 5640 |
| status | `PASS` |

## Corpus + human packages

| Metric | Value |
|--------|-------|
| real corpus | 500 (dev 340 / val 60 / holdout 100) |
| provenance gate | `PASS` |
| packages ready | `True` |
| top20 aligned to E2E | `True` |
| intersection | 20/20 |
| human labels filled | 0 |
| packages gate | `PACKAGES_READY_BLOCKED_REAL_HOLDOUT_NOT_REVIEWED` |

Required fields present: contract_id, object_original, agency, uf, publication_date, snapshot_id, source_row_hash, stratum (labels empty).

## 12 closure questions

1. Snapshot ≥365 days? **True**
2. Active + closed real? **True**
3. Official full-universe registry? **False**
4. Operational enrichment 100%? **True**
5. Restorable dump? **True**
6. Distinct DB restore? **True**
7. Pre-restore hash? **True**
8. Full-universe E2E? **True**
9. Corpus ≥500 with provenance? **True**
10. Human packages ready? **True**
11. Execution matches freeze? **True** (re-checked after re-freeze if code changed)
12. Technical blockers beyond CI/human? **['BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE']**

## MACHINE / HUMAN / CI

### MACHINE blockers
- `BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE`

### HUMAN PENDING
- `BLOCKED_REAL_HOLDOUT_NOT_REVIEWED`
- `BLOCKED_INSUFFICIENT_HUMAN_LABELS`
- `BLOCKED_PENDING_HUMAN_ACCEPTANCE`

### CI PENDING
- `BLOCKED_CI_ENVIRONMENT_EVIDENCE_PENDING`


## Live tip sync

- HEAD: `2eb139b576c11ad0bcac75edfb3fa610992c1777`
- FREEZE/EXECUTED: `2eb139b576c11ad0bcac75edfb3fa610992c1777`
- code_changed_after_execution: false (after re-freeze of package-builder fix)
