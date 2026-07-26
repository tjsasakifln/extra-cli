# CONFENGE Gold Standard — Final Report (skeptic fixes)

**Terminal status:** `BLOCKED` — `BLOCKED_INSUFFICIENT_HUMAN_LABELS`

## SHAs / run
| Field | Value |
|-------|-------|
| PR HEAD (pre-commit) | `691878853160b85ab7736d36f8265ed427f64d88` |
| main | `8344254942ec48978566317df16d7b3e3caabd89` |
| executed run | `cl-20260726T003820Z-f8e90e36` |
| dataset rows | 60000 |
| full-history contracts | 19328 |
| candidates | 7091 |
| published leads | 20 |
| canonical_table_hash | `c22cff3b72ed09f696d3f42721d5977e1ed5622f7ed8a4a4651580677bdc3157` |
| rows_hashed | 60000 |

## Modes (explicit; FULL_POPULATION is legacy flag only)
- discovery: `PREFILTERED_CANDIDATE_DISCOVERY`
- history: `FULL_CANDIDATE_HISTORY`
- ranking: `FULL_ELIGIBLE_CANDIDATES`
- claims_full_snapshot_scan: **false**

## Sector distribution (full history, STRONG requires 180d or CNAE)
```json
{
  "CONFIRMED_ENGINEERING": 86,
  "OUT_OF_SCOPE": 474,
  "POSSIBLE_ENGINEERING_FIT": 6193,
  "CONFLICTING": 338
}
```
Note: STRONG without CNAE is rare/impossible on ~160d snapshot window because **STRONG_MIN_TIME_SPAN_DAYS=180** (restored). Publishable path is **CONFIRMED via CNAE**.

## Gates
```json
{
  "denominator_integrity": "PASS",
  "full_candidate_history": "PASS",
  "supplier_registry_top20_coverage": "PASS",
  "contract_relevance_holdout": "PASS",
  "prefilter_recall": "PASS",
  "prefilter_recall_value": 0.9909,
  "snapshot_content_binding": "BOUND",
  "canonical_table_hash": "c22cff3b72ed09f696d3f42721d5977e1ed5622f7ed8a4a4651580677bdc3157",
  "top10_out_of_scope": 0,
  "persistence": "PASS",
  "migrations": "PASS",
  "strong_min_time_span_days": 180
}
```

## Evaluation sample
- n=200 real suppliers
- strata={"published_or_strong": 50, "possible": 50, "conflicting_or_unknown": 50, "out_of_scope": 50}
- dual review labels: **empty (PENDING)**

## Answers
1. Full-history concentration? **YES**
2. Single contract → STRONG? **NO**
3. CNAE in pipeline? **YES** (top20 100%)
4. Precision metrics human? **NO** (null)
5. Snapshot content-bound to DB? **YES** (canonical_table_hash 60000 rows)
6. Beats baselines? **NOT_COMPUTABLE** without human labels
7. Top-20 usable? **PENDING human review**
8. Claim > evidence? **NO**
9. STRONG time span threshold? **180 days**

## Remaining blockers
- BLOCKED_INSUFFICIENT_HUMAN_LABELS
- BLOCKED_PENDING_HUMAN_ACCEPTANCE
