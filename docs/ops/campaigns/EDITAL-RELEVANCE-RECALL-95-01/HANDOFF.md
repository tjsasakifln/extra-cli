# Handoff — EDITAL-RELEVANCE-RECALL-95-01 (fail-closed residual patch)

## Campaign status

```text
IMPLEMENTATION_READY_BUT_EXTERNALLY_BLOCKED
BLOCKED_BY_EXISTING_CONFENGE_FREEZE_POLICY
BLOCKED_HUMAN_DUAL_LABELING
DO_NOT_MERGE
```

DOD §8.4 remains **`[ ]`**. Merge of this foundation ≠ DOD accept.

## Isolation from CONFENGE

- `scripts/ops/confenge_code_freeze.py` — **byte-identical to `origin/main`**
- `scripts/ops/verify_confenge_artifact_binding.py` — **byte-identical to `origin/main`**
- `scripts/ops/sector_classifier.py` — **byte-identical to `origin/main`**
- No CONFENGE allowlist expansion, bypass, skip, or gate rewrite in this PR.

### Residual monorepo freeze collision

Existing CONFENGE commercial jobs reject this PR's edital paths because they are
outside the freeze allowlist. **Allowlists were not re-expanded** (forbidden).
**Commercial evidence was not rewritten** (forbidden).

## Fail-closed residual patch delivered

| Item | State |
|------|-------|
| `FAILED_DEVELOPMENT_INTEGRITY` taxonomy | technical ≠ human |
| Precedence (dev > structural > human > final) | enforced |
| Development integrity must pass for human blocker meta-test | yes |
| Final evaluator validates reviewer IDs (normalized) | direct, not importer-only |
| Final evaluator validates timezone-aware timestamps | direct |
| Final evaluator requires per-reviewer reasons | `label_reviewer_a_reason` / `label_reviewer_b_reason` |
| Path identity exact (no basename-only) | yes |
| Provenance `selection_rule` / `selection_basis` | standardized |
| Real non-empty development corpus | `development_candidate_pool.jsonl` (n=24) |
| Overlap development ∩ pilot | **0** |
| Three Makefile targets | semantics preserved + strengthened meta asserts |
| DOD §8.4 | still open `[ ]` |
| PR draft / no merge | required while CONFENGE red |

## Infrastructure

- Evaluator: `scripts/coverage/edital_relevance_recall.py`
  - `diagnose` → `DIAGNOSTIC_ONLY` (pilot machine drafts allowed; never accept)
  - `evaluate-final` → fail-closed human acceptance gate + mandatory development integrity
- Human workflow: `scripts/campaigns/edital_relevance/human_labeling.py`
- Development pool: `evals/edital_relevance/development_candidate_pool.jsonl` + manifest
- Diagnostic corpus: pilot of 36 only (`evals/edital_relevance/pilot_36.*`)
- Tests: `tests/coverage/test_edital_relevance_recall.py`, `tests/coverage/test_human_labeling.py`
- Makefile targets (distinct semantics):
  - `test-edital-relevance-foundation` → green when infrastructure is correct
  - `verify-edital-relevance-final` → real final gate with real development; **non-zero** while blocked
  - `test-edital-relevance-final-blocker` → meta-test; **zero** when block is correct **and** `development_integrity.pass is true`
- CI job: `Edital Relevance Foundation`

## Pilot contamination (not final holdout)

`evals/edital_relevance/pilot_36.*`:

| Field | Value |
|-------|-------|
| `role` | `pilot_candidate` |
| `label_authority` | `machine_criteria_draft` |
| `acceptance_eligible` | `false` |
| `sealed_holdout` | `false` |

Contaminated and **forbidden** as final holdout. Allowed: pilot source, process testing.

## Development candidate pool

| Field | Value |
|-------|-------|
| path | `evals/edital_relevance/development_candidate_pool.jsonl` |
| role | `development` |
| acceptance_eligible | `false` |
| sealed_holdout | `false` |
| selection_rule | `public_inventory_stratified_content_sample` |
| selection_basis | `public_inventory_only` |
| selection_independent_of_classifier | `true` |
| never reusable as final holdout | **yes** |

## Gate results (expected state)

| Target | Expected |
|--------|----------|
| `make test-edital-relevance-foundation` | **PASS** (exit 0) |
| `make verify-edital-relevance-final` | **NON-ZERO** + `BLOCKED_HUMAN_DUAL_LABELING` + `development_integrity.pass=true` |
| `make test-edital-relevance-final-blocker` | **PASS** (exit 0; meta proves human block only) |

## Human labels pending

- Owner to unlock: Tiago Sasaki + second authorized reviewer
- Packages: `evals/edital_relevance/pilot_36_reviewer_a.csv`, `pilot_36_reviewer_b.csv`
- Fields to fill: `label` ∈ {RELEVANT, IRRELEVANT, UNDECIDABLE}, `reason` (non-empty)
- Timestamps: ISO-8601 with timezone (`Z` or offset); naive rejected
- Immutable content must not be edited

## Commands

```bash
# Foundation (must pass)
make test-edital-relevance-foundation

# Diagnostic only (never accept) — pilot_36 only
python3 -m scripts.coverage.edital_relevance_recall diagnose \
  --corpus evals/edital_relevance/pilot_36.jsonl \
  --manifest evals/edital_relevance/pilot_36-manifest.json

# Real final gate (must be non-zero now)
python3 -m scripts.coverage.edital_relevance_recall evaluate-final \
  --corpus evals/edital_relevance/pilot_36.jsonl \
  --manifest evals/edital_relevance/pilot_36-manifest.json \
  --development evals/edital_relevance/development_candidate_pool.jsonl \
  --development-manifest evals/edital_relevance/development_candidate_pool-manifest.json \
  --output artifacts/campaigns/EDITAL-RELEVANCE-RECALL-95-01/final-gate-result.json

# Meta-test of blocker (must pass)
make test-edital-relevance-final-blocker
```

## Next test

Human dual labeling of pilot → import → adjudication → pilot approval → **new** sealed holdout after classifier freeze → `evaluate-final` exit 0 → only then consider §8.4. CONFENGE freeze policy remains a separate external unblock.

## Non-claims

- No DOD §8.4 accept
- No human gold
- No sealed final holdout
- No classifier repair in this PR
- No CONFENGE allowlist expansion
- No overall CI green claim
- No `READY_FOR_FINAL_CTO_REVIEW` while CONFENGE jobs red
- No independent-human claim from agents/scripts
- Merge ≠ accept
