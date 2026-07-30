# PUBLIC-TENDER-CORPUS-VALIDATION-01 — STATUS

**Date:** 2026-07-30  
**Related:** PR `#133` (draft/blocked), issue corpus public

## Policy

Synthetic fixtures ≠ operational proof for recall, checklist, or bid readiness.

## Existing infrastructure

- `evals/edital_relevance/` development + pilot (machine draft; not sealed holdout)
- `scripts/coverage/edital_relevance_recall.py`
- Final gate blocked: `BLOCKED_HUMAN_DUAL_LABELING`
- Bid readiness PR remains draft until public corpus

## Blocker

```
BLOCKED_PUBLIC_CORPUS_NOT_PROVIDED
```

Need authorized public tender corpus (editais + anexos + outcomes) with manifest, license, hashes.

## Unblock

1. Deposit corpus under agreed path with `corpus-manifest.json` (ids, source, license, sha256).
2. Dual human labeling on sealed holdout.
3. Re-run foundation + final gates; only then promote recall DoD items.

## Claim

Infrastructure documented; **no operational corpus accept** in this execution.
