# FINAL-REPORT — reajuste 14.133 v2.1 (honest PDF recovery)

**Terminal:** `BLOCKED_INSUFFICIENT_VERIFIED_OUTREACH_LEADS`  
**Tip HEAD at write:** `4beaf0b8ac2433ea6f10b91069dbc4546e7a66a3`  
**Updated:** 2026-08-05T03:21:16Z

## Documentary definition (fail-closed)

- Portal HTML / object_field / url_builder **never** set `docs_accessible` or `official_text_extracted`.
- Real path: PNCP contrato API → `numeroControlePncpCompra` → compra `/arquivos` → PDF download → PyPDF2 text + page markers.
- `docs_processed_deep` = contracts with PDF download work.
- `official_pdf_text_extracted` = PDF text successfully extracted.

## Etapa A — Sul (full prefilter)

| Metric | Value |
|--------|------:|
| Universe / read / complete | 27634 / 27634 / True |
| docs_processed_deep | **205** |
| official_pdf_text_extracted | **201** |
| OUTREACH_READY* | **0** |
| DOCUMENT_REQUEST suppliers | 39 |

## Etapa B — Nacional ≥ R$5M (v2.1 PDF recovery)

| Metric | Value |
|--------|------:|
| Universe / read / complete | 36423 / 36423 / True |
| docs_processed_deep | **220** |
| official_pdf_text_extracted | **219** |
| pdfs_downloaded | 309 |
| national_v21_pdf_recovery | True |
| OUTREACH_READY* | **0** |

National human_review_top30 is PDF-grounded (not AUTO_STUB): pages + pncp_pdf_* docs.

## Key hashes

| Artifact | Size | SHA-256 |
|----------|-----:|---------|
| Sul human_review | 175556 | `7bd043df8f6033b5c5a963a5f8f184a8eb965c77840b6439e01f73b0e3add5ff` |
| Nacional human_review | 152811 | `31464ea512f251cee347ac0bb77d504a6269b60c86bd3e204a3857148027d1d1` |
| Nacional document_evidence | 7121855 | `fb7a5c7341900d7272724ef8950b579a025a28a1cfc45037e796fc07fa62eef9` |
| Nacional run_manifest | 4382 | `f048c441d7757e2e2a2f6c918c931eb2eec2438796825266d2fd4f409b641551` |
| Nacional XLSX | 2761551 | `c0f0d829eedd9a7b1211333cfcea458e346f1dc33653f9fe4395b0066ceb8925` |

## Paths

- Full: `output/commercial/reajuste_14133/2026-08-04-v2/` (+ `nacional/`)
- PR-safe: `artifacts/commercial/reajuste_14133/2026-08-04-v2/`
