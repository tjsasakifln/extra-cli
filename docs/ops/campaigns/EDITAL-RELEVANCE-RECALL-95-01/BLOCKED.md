# BLOCKED — EDITAL-RELEVANCE-RECALL-95-01

**Status terminal:**

```text
IMPLEMENTATION_READY_BUT_EXTERNALLY_BLOCKED
BLOCKED_BY_EXISTING_CONFENGE_FREEZE_POLICY
BLOCKED_HUMAN_DUAL_LABELING
DO_NOT_MERGE
```

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

External monorepo freeze policy still reds commercial CONFENGE jobs; this PR does **not** expand allowlists or rewrite commercial evidence.

## Fail-closed residual patch (this execution)

Taxonomy of blockers is explicit and ordered by precedence:

1. `FAILED_DEVELOPMENT_INTEGRITY` — technical development corpus/manifest failures (never masked as human)
2. `FAILED_FINAL_GATE` — other structural final-gate failures
3. `BLOCKED_HUMAN_DUAL_LABELING` — only when development integrity passes and human dual labeling is absent
4. Accept only when all gates pass (not claimed here)

Final evaluator validates **directly** on each holdout record:

- normalized distinct `human_reviewer_a_id` / `human_reviewer_b_id`
- timezone-aware `reviewed_at_a` / `reviewed_at_b`
- non-empty `label_reviewer_a_reason` / `label_reviewer_b_reason`

Development path identity is exact (`resolve()`); same basename in another directory fails.

## Infrastructure delivered (not DOD accept)

1. Fail-closed evaluator (`diagnose` + `evaluate-final`) with mandatory real development corpus.
2. Versioned development candidate pool (`evals/edital_relevance/development_candidate_pool.jsonl`, n=24) + manifest with mandatory `corpus_sha256`.
3. Full-set development integrity: hash, role, n_records, path identity, internal dups, holdout overlap (currently **zero**), selection provenance.
4. Human import: timezone-aware ISO-8601 only (UTC-Z normalize); reviewer IDs distinct after case/whitespace normalize.
5. Blind pilot packages (`pilot_36_reviewer_a.csv` / `pilot_36_reviewer_b.csv`).
6. Makefile targets with distinct semantics (foundation green / final non-zero / blocker meta green).
7. CONFENGE freeze/binding and sector classifier unchanged vs `main` (empty diffs).

## Development corpus (not holdout)

| Field | Value |
|-------|-------|
| path | `evals/edital_relevance/development_candidate_pool.jsonl` |
| manifest | `evals/edital_relevance/development_candidate_pool-manifest.json` |
| role | `development` |
| acceptance_eligible | `false` |
| sealed_holdout | `false` |
| n_records | 24 |
| selection_rule | `public_inventory_stratified_content_sample` |
| selection_basis | `public_inventory_only` |
| selection_independent_of_classifier | `true` |
| pilot overlap | 0 |
| eligible for final holdout | **never** |

Empty `empty-development.jsonl` is **removed** and must not reappear.

## Blockers

1. **`BLOCKED_HUMAN_DUAL_LABELING`** — dual independent human labels + new sealed holdout absent (DOD §8.4). Final gate returns non-zero with this exact primary blocker **when development integrity passes**.
2. **`BLOCKED_BY_EXISTING_CONFENGE_FREEZE_POLICY`** — job `CONFENGE Commercial Code Quality` / Artifact SHA binding gate fails with `code_changed_after_bound_sha` for foundation paths. Allowlists were **not** re-expanded; commercial evidence was **not** rewritten.

## Next test (to unblock human path only)

1. Tiago + second authorized reviewer fill the blind pilot packages.
2. Import + adjudicate divergences (`--expected-corpus` required; timezone-aware timestamps).
3. Pilot human approval.
4. Collect a **new** public holdout (≥100 RELEVANT) after freezing any candidate classifier — never reuse pilot_36 or development_candidate_pool as final holdout.
5. `make verify-edital-relevance-final` → exit 0 only with human gold.
6. Merge accept evidence only after main + gates + CONFENGE policy resolution.
7. **STOP.**

## Non-claims

- Not accepting §8.4.
- Not claiming 95% relevance recall as proven.
- Not gold / sealed holdout / independent human dual labels.
- Not classifier repair.
- Not overall CI green (CONFENGE remains honestly red).
- Not `READY_FOR_FINAL_CTO_REVIEW` while CONFENGE jobs are red.
- Pilot_36 is contaminated for final holdout use.
- Foundation gate PASS ≠ final accept; blocker meta-test PASS ≠ final accept.
- No merge / no ready-for-review while CONFENGE freeze policy blocks.
