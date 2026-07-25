# Sector Classifier — Hybrid Recall + LLM Arbiter

## Status

`BLOCKED_INVALID_EVALUATION_CORPUS`

Active blockers: `BLOCKED_EMBEDDING_OPERATIONAL_VALIDATION, BLOCKED_FULL_SUITE_VALIDATION, BLOCKED_INSUFFICIENT_REAL_GOLD_CORPUS, BLOCKED_INSUFFICIENT_RECALL, BLOCKED_INSUFFICIENT_STATISTICAL_POWER, BLOCKED_INVALID_EVALUATION_CORPUS, BLOCKED_LLM_OPERATIONAL_VALIDATION, BLOCKED_REVIEW_CAPACITY`

PR #131 remains **CHANGES_REQUESTED_RECALL_ASSURANCE**. This stacked work does not accept or merge #131 and does not produce RC v3.

## Pipeline

```
RAW UNIVERSE
  → hybrid multi-channel retrieval (lexical, semantic, metadata, organ_history, zero_match)
  → union merge + RRF ranking only
  → deterministic selective (CLEAR_POSITIVE | GRAY_ZONE | CLEAR_NEGATIVE)
  → selective LLM arbitration (fail → REVIEW)
  → MATCH | REVIEW | NO_MATCH
```

## Evaluation levels

- **A** unit fixtures
- **B** `SYNTHETIC_ADVERSARIAL_FIXTURE` (regression only)
- **C** real locked operational gold (only C sustains operational claims)

## Principles

1. Retrieval is not classification.
2. Absence of keyword ≠ absence of opportunity.
3. RRF ranks; it does not exclude before classification.
4. Client sees precision (MATCH only); operations preserve recall (REVIEW).
5. LLM errors never produce NO_MATCH.
6. Never blend synthetic and real rates into one headline.

## Entry

```bash
python -m scripts.ops.campaign_hybrid_sector_recall --fixtures
python -m scripts.ops.campaign_hybrid_sector_recall --synthetic \
  --corpus tests/fixtures/hybrid_sector/synthetic_adversarial_corpus.json
python -m scripts.ops.campaign_hybrid_sector_recall \
  --corpus tests/fixtures/hybrid_sector/real_operational_corpus.json \
  --split locked --out /tmp/hybrid-sector-locked
```

Default CI uses **fake LLM only**. Paid provider requires `--allow-paid-llm` (operational gate).

## Summary

- Universe: 0
- Candidates: 0
- MATCH: 0
- REVIEW: 0
- NO_MATCH: 0
- Level: C
- Corpus kind: REAL_OPERATIONAL_LOCKED_GOLD
