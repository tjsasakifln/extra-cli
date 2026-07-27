# Handoff — EDITAL-RELEVANCE-RECALL-95-01 (foundation)

## Campaign status

**`BLOCKED_HUMAN_DUAL_LABELING`**

DOD §8.4 remains **`[ ]`**. Merge of this foundation ≠ DOD accept.

## Isolation from CONFENGE

- `scripts/ops/confenge_code_freeze.py` — **byte-identical to `origin/main`**
- `scripts/ops/verify_confenge_artifact_binding.py` — **byte-identical to `origin/main`**
- `scripts/ops/sector_classifier.py` — **byte-identical to `origin/main`**
- No CONFENGE allowlist expansion, bypass, skip, or gate rewrite in this PR.

### Residual monorepo freeze collision

After restoring freeze/binding to `origin/main`, existing CONFENGE commercial jobs
(`CONFENGE Commercial Code Quality` → Artifact SHA binding gate) reject this PR's
edital paths because they are outside the freeze allowlist. **Allowlists were not
re-expanded** (forbidden). **Commercial evidence was not rewritten** (forbidden).

Campaign escalates as: **`BLOCKED_BY_EXISTING_CONFENGE_FREEZE_POLICY`**
(in addition to residual human dual-labeling blocker for §8.4).

## Infrastructure delivered

- Evaluator: `scripts/coverage/edital_relevance_recall.py`
  - `diagnose` → `DIAGNOSTIC_ONLY` (pilot machine drafts allowed; never accept)
  - `evaluate-final` → fail-closed human acceptance gate (both seal flags AND; mandatory `corpus_sha256`; non-omissible `--development`)
- Human workflow: `scripts/campaigns/edital_relevance/human_labeling.py`
  - blind package generation
  - import + validation (immutable fields; `--expected-corpus` required; no auto-fill)
- Public candidate helpers: `scripts/campaigns/edital_relevance/build_corpus.py`
- Diagnostic corpus: pilot of 36 only (`evals/edital_relevance/pilot_36.*`)
- Blind pilot CSVs for 36 IDs
- Tests: `tests/coverage/test_edital_relevance_recall.py`, `tests/coverage/test_human_labeling.py`
- Makefile targets (distinct semantics):
  - `test-edital-relevance-foundation` → green when infrastructure is correct
  - `verify-edital-relevance-final` → real final gate; **non-zero** while blocked
  - `test-edital-relevance-final-blocker` → meta-test; **zero** when block is correct
- CI job: `Edital Relevance Foundation`

## Pilot contamination (not final holdout)

`evals/edital_relevance/pilot_36.*`:

| Field | Value |
|-------|-------|
| `role` | `pilot_candidate` |
| `label_authority` | `machine_criteria_draft` |
| `acceptance_eligible` | `false` |
| `sealed_holdout` | `false` |

Contaminated and **forbidden** as final holdout. Allowed: pilot source, development, process testing.

## Gate results (expected state)

| Target | Expected |
|--------|----------|
| `make test-edital-relevance-foundation` | **PASS** (exit 0) |
| `make verify-edital-relevance-final` | **NON-ZERO** + `BLOCKED_HUMAN_DUAL_LABELING` |
| `make test-edital-relevance-final-blocker` | **PASS** (exit 0; meta proves block) |

## Human labels pending

- Owner to unlock: Tiago Sasaki + second authorized reviewer
- Packages: `evals/edital_relevance/pilot_36_reviewer_a.csv`, `pilot_36_reviewer_b.csv`
- Fields to fill: `label` ∈ {RELEVANT, IRRELEVANT, UNDECIDABLE}, `reason` (non-empty)
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
make verify-edital-relevance-final

# Meta-test of blocker (must pass)
make test-edital-relevance-final-blocker
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
- No CONFENGE allowlist expansion
- No independent-human claim from agents/scripts
- Merge ≠ accept
