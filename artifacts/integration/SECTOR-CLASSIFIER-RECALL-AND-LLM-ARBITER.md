# Sector Classifier — Hybrid Recall + LLM Arbiter

## Status

`BLOCKED_INSUFFICIENT_STATISTICAL_POWER`

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

## Principles

1. Retrieval is not classification.
2. Absence of keyword ≠ absence of opportunity.
3. RRF ranks; it does not exclude before classification.
4. Client sees precision (MATCH only); operations preserve recall (REVIEW).
5. LLM errors never produce NO_MATCH.

## Entry

```bash
python -m scripts.ops.campaign_hybrid_sector_recall --fixtures
python -m scripts.ops.campaign_hybrid_sector_recall --corpus tests/fixtures/hybrid_sector/gold_corpus.json
```

Default CI uses **fake LLM only**. Paid provider requires `--allow-paid-llm` (operational gate).

## Summary

- Universe: 5
- Candidates: 5
- MATCH: 3
- REVIEW: 0
- NO_MATCH: 2
