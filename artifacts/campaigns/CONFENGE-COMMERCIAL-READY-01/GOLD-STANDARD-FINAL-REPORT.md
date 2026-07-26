# CONFENGE Gold Standard — Final Report

**Terminal status:** `BLOCKED` — `BLOCKED_INSUFFICIENT_HUMAN_LABELS`

## SHAs / run

| Field | Value |
|-------|-------|
| PR HEAD | `3eddf6f9c325cc81c739461674bdd197727eaaa3` |
| main | `8344254942ec48978566317df16d7b3e3caabd89` |
| executed run | `cl-20260726T001934Z-fbd4ddeb` |
| run git sha | `3eddf6f9c325cc81c739461674bdd197727eaaa3` |
| dataset rows | 60000 |
| full-history contracts | 19328 |
| candidates | 7091 |
| published leads | 20 |

## Modes

- discovery: `PREFILTERED_CANDIDATE_DISCOVERY`
- history: `FULL_CANDIDATE_HISTORY` (complete=True)
- ranking: `FULL_ELIGIBLE_CANDIDATES`

## Sector distribution (full history)

```json
{
  "CONFIRMED_ENGINEERING": 86,
  "OUT_OF_SCOPE": 474,
  "POSSIBLE_ENGINEERING_FIT": 5898,
  "CONFLICTING": 338,
  "STRONG_ENGINEERING_FIT": 295
}
```

Baseline had **4791 STRONG** on contaminated denominator. Now **295 STRONG** + **86 CONFIRMED**.

## Gates

```json
{
  "denominator_integrity": "PASS",
  "full_candidate_history": "PASS",
  "supplier_registry_top20_coverage": "PASS",
  "contract_relevance_holdout": "PASS",
  "prefilter_recall": "PASS",
  "prefilter_recall_value": 0.9909,
  "top10_out_of_scope": 0,
  "snapshot_binding": "BOUND",
  "persistence": "PASS",
  "migrations": "PASS"
}
```

## Explicit answers

1. Full-history concentration? **YES**
2. Single contract → STRONG? **NO**
3. CNAE in pipeline? **YES** (top20 100% BrasilAPI)
4. Precision metrics human? **NO** (null / PENDING)
5. Snapshot matches DB? **True**
6. Beats baselines? **NOT_COMPUTABLE without human labels**
7. Top-20 usable? **PENDING human review** (machine: 0 OOS, all CONFIRMED)
8. Claim > evidence? **NO** — status remains BLOCKED for humans

## Blockers remaining

- BLOCKED_INSUFFICIENT_HUMAN_LABELS (dual review ≥200)
- BLOCKED_PENDING_HUMAN_ACCEPTANCE
