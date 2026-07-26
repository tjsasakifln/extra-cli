# FINAL-EVIDENCE-CLOSURE — CONFENGE-COMMERCIAL-READY-01 (PR #144)

Generated: `2026-07-26T15:23:11Z`

## Terminal status

| Field | Value |
|-------|-------|
| status | `BLOCKED` |
| technical_status | `BLOCKED` |
| terminal_reason | `BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE` |

## SHAs

| Field | Value |
|-------|-------|
| PR HEAD | `4dc1ef995672605caec9cf30b885b47fe5bf0e5a` |
| main SHA | `8344254942ec48978566317df16d7b3e3caabd89` |
| final code freeze SHA | `4dc1ef995672605caec9cf30b885b47fe5bf0e5a` |
| executed code SHA | `4dc1ef995672605caec9cf30b885b47fe5bf0e5a` |
| code changed after execution | `False` |

## Snapshot (historical)

| Metric | Value |
|--------|-------|
| source | pncp_datalake → confenge_commercial |
| total rows | 11974 |
| observation days | **718** (min 365) |
| min/max date | 2024-08-07 → 2026-07-26 |
| ACTIVE | 7532 |
| COMPLETED (closed) | 4442 |
| UNKNOWN | 0 |
| suppliers | 6046 |
| lifecycle gate | `PASS` |

Status normalization uses explicit rules (`data_fim_before_as_of_v1` / `data_fim_null_or_future_v1`). No fabricated CANCELLED/TERMINATED.

## Restorable dump / independent anchor

| Metric | Value |
|--------|-------|
| format | CSV package (`restorable-dump/`) |
| dump SHA256 | `566ffa1d74e20cc5efcea65b60d3bf874c3567da70b0e24e08ffe28049f0adb5` |
| source DB identity | `a86b9307a5384c4a6ab0e181` |
| restored DB identity | `ddca7d60a3330ffebe9a6796` |
| identities distinct | `True` |
| pre-restore canonical hash | `2a4d690e7249b450891a2ec43454fef18709bb9662897064cec91c16a64b937f` |
| post-restore canonical hash | `2a4d690e7249b450891a2ec43454fef18709bb9662897064cec91c16a64b937f` |
| gate | `PASS` |

Not a metadata-only `integrity_padding` theater file.

## Registry

| Metric | Value |
|--------|-------|
| frozen candidate universe | 5640 |
| universe hash | `222d78ecb14935e16a1b30340699ba359de76318eb5092725f76b3f4eeeacddd` |
| operational resolution | 1.0 |
| official RFB-via-OpenCNPJ rows | 300 |
| official coverage of universe | 0.05319148936170213 |
| fallback usage rate | 0.9468085106382979 |
| official file provenance | `PASS` |
| official universe resolution | `BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE` |

**Honest blocker:** full-universe official RFB-authority resolution is partial (300/5640). OpenCNPJ was rate-limited (HTTP 429); RFB multi-GB bulk zip was not staged. Operational fallback (MinhaReceita/BrasilAPI) fills the rest with per-source labels — **not renamed official**.

## Full-universe E2E

| Metric | Value |
|--------|-------|
| n_universe | **5640** |
| frozen_candidate_count | 5640 |
| n == frozen | True |
| all hashes equal | True |
| top20 equal | True |
| status | `PASS` |

Sampled runs are labeled `SAMPLED_E2E_TEST` only (never full PASS).

## Real corpus + human review

| Metric | Value |
|--------|-------|
| real corpus total | 500 |
| development / validation / holdout | 340 / 60 / 100 |
| human labels filled | 0 |
| packages ready | True |

Packages (labels empty):

- `contract-relevance-human-review.xlsx` / `.html`
- `commercial-top20-human-review.xlsx`
- `commercial-evaluation-200-human-review.xlsx`

## Offer intelligence

| Metric | Value |
|--------|-------|
| distribution | {'acompanhamento_contratual': 20} |
| dominant rate | 1.0 |
| mean margin | 1.84799 |
| ablation change rates | {'near_expiry': 0.55, 'concurrent_portfolio': 0.05, 'agency_concentration': 0.75, 'contract_concentration': 0.05} |
| uniform justified individually | True |
| status | `PASS` |

## 12 closure questions

1. Snapshot ≥365 days? **True**
2. Active + closed real contracts? **True**
3. Registry uses verifiable official source for full universe? **False**
4. All candidates enriched (operational) before ranking? **True**
5. Restorable dump exists? **True**
6. Restore on distinct DB? **True**
7. Hash existed before restore? **True**
8. Reproducibility used full universe? **True**
9. Real corpus ≥500? **True**
10. Human review packages ready? **True**
11. Execution matches code freeze? **True**
12. Remaining technical blockers beyond CI/human? **['BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE']**

## Allowed remaining blockers

### MACHINE (if any)
- `BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE`

### HUMAN PENDING
- `BLOCKED_REAL_HOLDOUT_NOT_REVIEWED`
- `BLOCKED_INSUFFICIENT_HUMAN_LABELS`
- `BLOCKED_PENDING_HUMAN_ACCEPTANCE`

### CI PENDING
- `BLOCKED_CI_ENVIRONMENT_EVIDENCE_PENDING` (local execution; `workflow_run_id=null` expected)

## What is NOT claimed

- Official RFB bulk dataset fully covering 5640 CNPJs (only 300 RFB-via-OpenCNPJ)
- Human precision/recall (labels empty)
- CI green / GitHub Actions run id
- 160-day window or n=400 E2E as population PASS
