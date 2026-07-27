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

P1 unmet: dual independent **human** labels, adjudication, pilot approval, and a **new** sealed holdout (collected after classifier freeze, never the pilot/machine-seen pool) are absent.

Machine draft criteria engines are **not** human reviewers.

## Infrastructure delivered (not DOD accept)

1. Fail-closed evaluator (`diagnose` + `evaluate-final`).
2. Public-inventory candidate selection helpers.
3. Blind pilot packages (`pilot_36_reviewer_a.csv` / `pilot_36_reviewer_b.csv`).
4. Human import validation (immutable fields; no auto-fill).
5. Automated integrity tests + Makefile/CI foundation targets.
6. CONFENGE freeze/binding and sector classifier unchanged vs `main`.

## Blockers

1. **`BLOCKED_HUMAN_DUAL_LABELING`** — dual independent human labels + new sealed holdout absent (DOD §8.4).
2. **`BLOCKED_BY_EXISTING_CONFENGE_FREEZE_POLICY`** — after restoring freeze/binding scripts to `origin/main`, job `CONFENGE Commercial Code Quality` / step `Artifact SHA binding gate` fails with `code_changed_after_bound_sha` for foundation paths. Allowlists were **not** re-expanded; commercial evidence was **not** rewritten. Unblock requires monorepo-level re-freeze or a separate authorized coexistence story — not this PR.

## Next test (to unblock)

1. Tiago + second authorized reviewer fill the blind pilot packages.
2. Import + adjudicate divergences (`--expected-corpus` required).
3. Pilot human approval.
4. Collect a **new** public holdout (≥100 RELEVANT) after freezing any candidate classifier — never reuse pilot_36 as final holdout.
5. `make verify-edital-relevance-final` → exit 0 only with human gold.
6. Merge accept evidence only after main + gates.
7. **STOP.**

## Non-claims

- Not accepting §8.4.
- Not claiming 95% relevance recall as proven.
- Not gold / sealed holdout / independent human dual labels.
- Not classifier repair.
- Pilot_36 is contaminated for final holdout use.
- Foundation gate PASS ≠ final accept; blocker meta-test PASS ≠ final accept.
