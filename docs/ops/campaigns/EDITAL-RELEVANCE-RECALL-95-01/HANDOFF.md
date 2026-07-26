# Handoff — EDITAL-RELEVANCE-RECALL-95-01

## Claimed

- DOD §8.4: **Recall de editais relevantes >= 95% na amostra-ouro** proved on sealed `locked_holdout` with fail-closed evaluator.

## Evidence pointers

| Artifact | Path |
|----------|------|
| Onda zero ownership | `docs/ops/campaigns/EDITAL-RELEVANCE-RECALL-95-01/ONDA-ZERO-OWNERSHIP-MANIFEST.md` |
| Sampling plan | `docs/ops/campaigns/EDITAL-RELEVANCE-RECALL-95-01/corpus-sampling-plan.json` + `evals/edital_relevance/sampling_plan.json` |
| Pilot 36 | `evals/edital_relevance/pilot_36.jsonl` |
| Development | `evals/edital_relevance/development.jsonl` |
| Locked holdout + manifest | `evals/edital_relevance/locked_holdout.jsonl`, `locked_holdout-manifest.json` |
| Evaluator | `scripts/coverage/edital_relevance_recall.py` |
| Unit tests | `tests/coverage/test_edital_relevance_recall.py` |
| Final result | `artifacts/campaigns/EDITAL-RELEVANCE-RECALL-95-01/edital-relevance-recall-result.json` |
| Independent review | `docs/ops/campaigns/EDITAL-RELEVANCE-RECALL-95-01/review/INDEPENDENT-REVIEW.md` |
| Makefile gate | `make campaign-gate-edital-relevance-recall` |

## Canonical command

```bash
python3 -m scripts.coverage.edital_relevance_recall evaluate \
  --corpus evals/edital_relevance/locked_holdout.jsonl \
  --manifest evals/edital_relevance/locked_holdout-manifest.json \
  --profile config/client_profiles/extra.yaml \
  --development evals/edital_relevance/development.jsonl \
  --output artifacts/campaigns/EDITAL-RELEVANCE-RECALL-95-01/edital-relevance-recall-result.json
```

## Not claimed

- Capture recall / STRATIFIED-RECALL-SOURCE-RESILIENCE-01 substitute  
- Operational coverage ≥95%  
- VPS_OPERATIONAL / LOCAL_READY / PROJECT_DONE  
- PR #139 full hybrid architecture  
- PR #133 automated proposal  
- Commercial queue human accept (PR #144)  
- Any other DOD checkbox  

## Residual limitations

- 5 nominal FN on sealed holdout (listed in result JSON).  
- Dual-label reviewers are independent criteria engines, not two live human panels.  
- Holdout frozen for this accept; do not retune classifier on this same sealed set for a second final claim.
