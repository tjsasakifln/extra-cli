# Independent Review — EDITAL-RELEVANCE-RECALL-95-01

**Date:** 2026-07-26  
**Item:** DOD §8.4 — “Recall de editais relevantes >= 95% na amostra-ouro.”  
**Reviewer role:** Squad QA/Aceite Independente (track WT4)

## Verdict

**ACCEPT** for the exact §8.4 relevance-recall line, contingent on CI green on the evaluated SHA.

## Corpus integrity

| Check | Result |
|-------|--------|
| Public inventory selection (PNCP API, SC Compras live_fetch snapshot, CIGA DOM official zips) | PASS |
| Dual independent labels + adjudication | PASS (agreement holdout ~0.92) |
| UNDECIDABLE excluded from denominator | PASS |
| No silent UNDECIDABLE→IRRELEVANT | PASS (evaluator gate) |
| Holdout ≥100 RELEVANT | PASS (140) |
| Strata source / município_bucket / natureza | PASS (≥10 each) |
| Zero duplicate IDs | PASS |
| Development leakage into holdout | PASS (evaluator gate) |
| Synthetic cannot final-pass | PASS (evaluator gate) |
| Forbidden proxies (classifier selection, DB, success_zero) | PASS |

## Metric honesty

| Claim | Allowed? |
|-------|----------|
| Relevance recall on locked_holdout | YES — sole accept metric |
| Capture/identity/URL/hash recall (PR #128 style) | NO — not claimed |
| Development recall as final proof | NO — not claimed |
| DB volume / presence | NO — not used |

## Result under review

- **relevance_recall:** 0.9642857142857143 (135/140)  
- **threshold:** 0.95  
- **informative precision:** see result JSON  
- **rule_version:** `extra-sector-classifier/2.3.1`  
- **profile_hash:** recorded in result JSON  
- **False negatives (nominal):** 5 residual (distribution-line Celesc, legislative sanitation plan text, plenary lighting, homologation shell, appliance install/maintenance) — listed in result artifact; not hidden.

## Limitations (non-claimed)

- Does **not** accept operational coverage ≥95%, VPS_OPERATIONAL, LOCAL_READY, PROJECT_DONE.
- Does **not** activate PR #139 hybrid/LLM architecture.
- Dual labels are criteria-based independent reviewers (inclusion-first vs exclusion-first), not two human Tiago sessions; adjudication log is in corpus fields.
- Residual FN are acceptable under ≥95% gate; future calibration may address without reopening this sealed holdout as a second “final”.

## Stop

Only §8.4 recall line may change acceptance state. Campaign stops after DOD + handoff + CI green merge path.
