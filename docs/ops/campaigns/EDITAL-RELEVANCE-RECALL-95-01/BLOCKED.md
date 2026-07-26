# BLOCKED — EDITAL-RELEVANCE-RECALL-95-01

**Status:** `BLOCKED_HUMAN_DUAL_LABELING`  
**Date:** 2026-07-26  
**DOD item (unchanged acceptance):** §8.4 — *Recall de editais relevantes >= 95% na amostra-ouro.* → remains **`[ ]`**

## Responsible

| Role | Who |
|------|-----|
| Campaign executor | CTO agent session (PR #145) |
| Human dual labelers (required) | Tiago Sasaki + second authorized Extra reviewer |
| Pilot human approver (required) | Tiago or authorized delegate |
| Accept authority on main | @devops after gates + human evidence |

## Cause (P1 unmet)

Objective P1 requires a **public real gold corpus with dual independent human labels and adjudication**.

What shipped is **not** that:

| Required | Shipped | Gap |
|----------|---------|-----|
| Two independent **human** reviewers | Two **machine criteria engines** (`criteria_A` / `criteria_B`) | Label authority = `machine_criteria_draft` |
| Human adjudication of disagreements | Machine adjudicate() only | No human adjudicator log |
| Pilot approval by Tiago/authorized | None | `pilot_human_approved_at` is null |
| Freeze holdout **before** classifier edits | Same wave as classifier repair; seal self-attested | `sealed_before_classifier_edits: false` (honest) |
| Independent human QA of corpus | Campaign self-review on same PR | Not independent human |
| Accept on **main** | PR #145 open; main still `[ ]` | No main integration of accept |

Additionally: machine draft labels share engineering vocabulary with `sector_classifier`, creating circular optimism risk (development machine-draft recall can approach 1.0 after repair without proving human relevance recall).

## What *is* delivered (infrastructure only — not DOD accept)

1. Fail-closed evaluator `scripts/coverage/edital_relevance_recall.py` with integrity gates including **final-gate rejection of machine labels**.
2. Public inventory sampling (PNCP live API, SC Compras live_fetch snapshot, CIGA DOM official zips).
3. Corpus schema + pilot/development/holdout **machine draft** sets under `evals/edital_relevance/`.
4. Unit tests for evaluator gates (incl. human-label requirement).
5. Incremental classifier repair notes (rule_version 2.3.1) — diagnostic only vs machine draft.
6. CI-green path for infrastructure PR (does **not** authorize §8.4 accept).

## Diagnostic metric (NOT accept evidence)

With `--allow-machine-labels --no-holdout-floor` (or machine drafts + allow flag), a diagnostic relevance score against **machine** labels may be computed.  
**That score is explicitly forbidden as DOD accept evidence.**

Final command **without** `--allow-machine-labels` on current holdout must **exit non-zero** (integrity: human dual labels missing + seal false + no pilot approval).

## Next test (to unblock)

1. Two authorized humans independently label each pilot (36) then full holdout (≥100 RELEVANT) as RELEVANT / IRRELEVANT / UNDECIDABLE.  
2. Adjudicate all disagreements; never silent UNDECIDABLE→IRRELEVANT.  
3. Record `human_reviewer_a_id`, `human_reviewer_b_id`, `label_authority=human_dual_independent`, adjudication log.  
4. Human pilot approval timestamp on manifest.  
5. **Re-freeze** holdout manifest/hashes **before** any further classifier change (`sealed_before_classifier_edits: true`, `classifier_first_edit_at` ≥ `frozen_at` or null).  
6. Single final evaluate (no `--allow-machine-labels`) → exit 0 only if recall ≥95% and integrity.  
7. Independent human review of corpus + result.  
8. CI green on exact SHA.  
9. Merge to **main**.  
10. Serial DOD §8.4 `[x]` only after main.  
11. **STOP.**

## Explicit non-claims

- Not accepting §8.4 on main.  
- Not claiming 95% relevance recall as proven.  
- Not substituting capture recall / DB presence / success_zero.  
- Not claiming human dual labels from criteria engines.

## Evidence pointers

- This file  
- `HANDOFF.md`  
- `review/INDEPENDENT-REVIEW.md` (revised: infrastructure review only)  
- `evals/edital_relevance/*-manifest.json` (`campaign_status`, `label_authority`)  
- PR https://github.com/tjsasakifln/extra-cli/pull/145  
