# Handoff — EDITAL-RELEVANCE-RECALL-95-01

## Campaign status

**`BLOCKED_HUMAN_DUAL_LABELING`**

DOD §8.4 remains **unchecked**. No accept claim.

## Claimed

- Infrastructure for fail-closed relevance recall evaluation.  
- Public inventory sampling pipeline and machine-draft corpus schema.  
- Honest blocker documentation for missing human dual labels.

## Not claimed

- DOD §8.4 accept  
- Human dual-independent gold labels  
- Pilot human approval  
- Pre-repair sealed holdout proof  
- 95% relevance recall on human gold  
- Any other DOD item  

## Commands

### Final accept (must fail on current machine drafts)

```bash
python3 -m scripts.coverage.edital_relevance_recall evaluate \
  --corpus evals/edital_relevance/locked_holdout.jsonl \
  --manifest evals/edital_relevance/locked_holdout-manifest.json \
  --profile config/client_profiles/extra.yaml \
  --development evals/edital_relevance/development.jsonl
# expected: exit != 0 until human dual labels + seal + pilot approval
```

### Diagnostic only (machine drafts — NOT accept)

```bash
python3 -m scripts.coverage.edital_relevance_recall evaluate \
  --corpus evals/edital_relevance/locked_holdout.jsonl \
  --manifest evals/edital_relevance/locked_holdout-manifest.json \
  --profile config/client_profiles/extra.yaml \
  --development evals/edital_relevance/development.jsonl \
  --allow-machine-labels \
  --no-holdout-floor
```

## Next action for humans

See `BLOCKED.md` — dual human labeling + pilot approval + re-freeze + final evaluate + main merge.

## Residual limitations

Machine criteria drafts share vocabulary with the classifier → circular risk.  
First wave integrated on one PR branch (ownership documented in Onda Zero).  
CONFENGE freeze allowlist expanded so monorepo work does not false-fail commercial bind gates.
