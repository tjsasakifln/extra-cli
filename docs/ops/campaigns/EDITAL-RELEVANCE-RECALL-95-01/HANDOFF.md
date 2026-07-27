# Handoff — EDITAL-RELEVANCE-RECALL-95-01 (foundation)

## Campaign status

**`BLOCKED_HUMAN_DUAL_LABELING`**

DOD §8.4 remains **`[ ]`**. Merge of this foundation ≠ DOD accept.

## Infrastructure delivered

- Evaluator: `scripts/coverage/edital_relevance_recall.py`
  - `diagnose` → `DIAGNOSTIC_ONLY` (machine drafts allowed; never accept)
  - `evaluate-final` → fail-closed human acceptance gate
- Human workflow: `scripts/campaigns/edital_relevance/human_labeling.py`
  - blind package generation
  - import + validation (no auto-fill)
- Public candidate helpers: `scripts/campaigns/edital_relevance/build_corpus.py`
- Machine draft candidate pool (diagnostic only; contaminated for final holdout)
- Blind pilot CSVs for 36 IDs
- Tests: `tests/coverage/test_edital_relevance_recall.py`, `tests/coverage/test_human_labeling.py`
- Makefile: `test-edital-relevance-foundation`, `verify-edital-relevance-final`
- CI job: `Edital Relevance Foundation`

## Corpus contamination

`evals/edital_relevance/machine_draft_candidate_pool.*` is **machine draft** (`role=diagnostic_machine_draft`, `label_authority=machine_criteria_draft`, `acceptance_eligible=false`, `sealed_holdout=false`).

It was exposed during repair exploration. **Never reuse as final DOD holdout**, even after human labels. Allowed: pilot source, development, process testing.

Any residual diagnostic recall figure against machine labels is **not** accept evidence.

## Human labels pending

- Owner to unlock: Tiago Sasaki + second authorized reviewer
- Packages: `evals/edital_relevance/pilot_36_reviewer_a.csv`, `pilot_36_reviewer_b.csv`
- Fields to fill: `label` ∈ {RELEVANT, IRRELEVANT, UNDECIDABLE}, `reason`

## Commands

```bash
# Foundation (must pass)
make test-edital-relevance-foundation

# Diagnostic only (never accept)
python3 -m scripts.coverage.edital_relevance_recall diagnose \
  --corpus evals/edital_relevance/machine_draft_candidate_pool.jsonl \
  --manifest evals/edital_relevance/machine_draft_candidate_pool-manifest.json

# Final gate (must fail now with BLOCKED_HUMAN_DUAL_LABELING)
make verify-edital-relevance-final
```

## Blocker

`BLOCKED_HUMAN_DUAL_LABELING`

## Next test

Human dual labeling of pilot → import → adjudication → pilot approval → **new** sealed holdout after classifier freeze → `evaluate-final` exit 0 → only then consider §8.4.

## Non-claims

- No DOD §8.4 accept
- No human gold
- No sealed final holdout
- No classifier repair in this PR
- No CONFENGE freeze/binding weaken
- No independent-human claim from agents/scripts

## Monorepo note (CONFENGE freeze)

CONFENGE post-freeze allowlists include **foundation-only** prefixes so monorepo work can land without path-drift false fails:

- `evals/edital_relevance/`, `scripts/campaigns/`, `scripts/coverage/edital_relevance_recall.py`, `tests/coverage/`, `DOD.md`, `Makefile`, `.github/workflows/ci.yml`, EDITAL campaign artifacts
- allowlist files themselves (maintenance only)

**Still NOT allowlisted (intentional):** `scripts/ops/sector_classifier.py`, classifier adversarial tests — classifier repair requires human labels + separate PR.

This is monorepo coexistence, **not** CONFENGE commercial accept and **not** classifier freeze weaken for 2.3.1 repair.

