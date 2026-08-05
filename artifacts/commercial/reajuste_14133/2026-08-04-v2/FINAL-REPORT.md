# FINAL-REPORT — reajuste_14133 v2.1 rebind-export (nacional)

**Generated:** 2026-08-05T03:55Z  
**Code/evidence SHA (rebind HEAD):** `919328501acd315abec433b5e562492b86aa6cb8`  
**evidence_commit_sha:** `919328501acd315abec433b5e562492b86aa6cb8`  
**Atomic unit:** rebind-export (classify_row ← official PDF → outreach → export + invariants)

## Terminal

- **terminal_status:** `BLOCKED_INSUFFICIENT_VERIFIED_OUTREACH_LEADS`
- **OUTREACH_READY suppliers:** 0 (honest — no invented certainty)
- **DOCUMENT_REQUEST suppliers:** 149
- **regime_14133_proven contracts:** 191
- **still_unknown_with_proven:** 0

## Documentary

- docs_processed_deep: 220
- official_pdf_text_extracted: 219
- path: pncp_compra_pdf_pypdf2

## Funnel (post-rebind)

| status | n |
|--------|---|
| STRONG_CANDIDATE | 35 |
| REVIEW_REQUIRED | 154 |
| LEGAL_REGIME_UNKNOWN | 4023 |
| LEGAL_REGIME_CONFLICT | 10 |
| NOT_ELIGIBLE | 5138 |
| DOCUMENT_REQUEST_CANDIDATE | 189 |

## Human review

- n=30 suppliers with official PDF
- kind=`human_review_top30_suppliers`

## Reproduce

```bash
python3 -m scripts.commercial.reajuste_14133 rebind-export \
  --dir output/commercial/reajuste_14133/2026-08-04-v2/nacional \
  --as-of 2026-08-04 \
  --artifacts-dir artifacts/commercial/reajuste_14133/2026-08-04-v2
```
