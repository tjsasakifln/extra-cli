# FINAL-REPORT — reajuste_14133 v2.1 rebind-export

**Tip HEAD / evidence SHA:** `f338eb1d366aa8b4523fd494b9d8359bdb17cec6`  
**git_sha == evidence_commit_sha:** yes  
**Generated:** 2026-08-05T04:02Z  
**Unit:** atomic rebind-export (classify_row ← official PDF → outreach → export + invariants)

## Terminal status

`BLOCKED_INSUFFICIENT_VERIFIED_OUTREACH_LEADS`

## Counts (nacional, post-rebind)

| Metric | n |
|--------|--:|
| contracts | 9360 |
| docs_processed_deep | 220 |
| official_pdf_text_extracted | 219 |
| regime_14133_proven | 191 |
| still_unknown_with_proven | 0 |
| STRONG_CANDIDATE | 35 |
| REVIEW_REQUIRED | 154 |
| LEGAL_REGIME_CONFLICT | 10 |
| DOCUMENT_REQUEST contracts | 189 |
| OUTREACH_READY contracts | 0 |
| DOCUMENT_REQUEST suppliers | 149 |
| OUTREACH_READY suppliers | 0 |
| READY_WITHOUT_VALUE suppliers | 0 |

## Human review

n=30 kind=`human_review_top30_suppliers`

## Reproduce

```bash
python3 -m scripts.commercial.reajuste_14133 rebind-export \
  --dir output/commercial/reajuste_14133/2026-08-04-v2/nacional \
  --as-of 2026-08-04 \
  --artifacts-dir artifacts/commercial/reajuste_14133/2026-08-04-v2
```

Full commercial suite under `output/commercial/reajuste_14133/2026-08-04-v2/nacional/` (gitignored).
