# BLOCKED — EDITAL-RELEVANCE-RECALL-95-01

**Status:** `BLOCKED_HUMAN_DUAL_LABELING`  
**DOD item:** §8.4 — *Recall de editais relevantes >= 95% na amostra-ouro.* → remains **`[ ]`**

## Responsible

| Role | Who |
|------|-----|
| Human dual labelers (required) | Tiago Sasaki + second authorized Extra reviewer |
| Pilot human approver (required) | Tiago or authorized delegate |
| Accept authority on main | @devops after gates + human evidence |

## Cause

P1 unmet: dual independent **human** labels, adjudication, pilot approval, and a **new** sealed holdout (collected after classifier freeze, never the machine-seen pool) are absent.

Machine draft criteria engines are **not** human reviewers.

## What this foundation delivers (not DOD accept)

1. Fail-closed evaluator (`diagnose` + `evaluate-final`).
2. Public-inventory candidate selection helpers.
3. Blind pilot packages (`pilot_36_reviewer_a.csv` / `pilot_36_reviewer_b.csv`).
4. Human import validation (no auto-fill).
5. Automated integrity tests + Makefile/CI foundation targets.

## Explicit non-claims

- Not accepting §8.4.
- Not claiming 95% relevance recall as proven.
- Not gold / sealed holdout / independent human dual labels.
- Not classifier repair.
- Current machine-seen pool is contaminated for final holdout use.

## Next test (to unblock)

1. Tiago + second authorized reviewer fill the blind pilot packages.
2. Import + adjudicate divergences.
3. Pilot human approval.
4. Collect a **new** public holdout (≥100 RELEVANT) after freezing any candidate classifier — never reuse the machine-seen pool as final holdout.
5. `make verify-edital-relevance-final` → exit 0 only with human gold.
6. Merge accept evidence only after main + gates.
7. **STOP.**
