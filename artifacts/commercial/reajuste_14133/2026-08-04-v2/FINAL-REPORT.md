**Evidence HEAD:** 

# FINAL-REPORT — reajuste 14.133 v2 (honest documentary recovery)

**Terminal:** `BLOCKED_INSUFFICIENT_VERIFIED_OUTREACH_LEADS`  
**As-of:** 2026-08-04 · module 2.0.0  
**Updated:** 2026-08-05T02:41:23Z

## Honest documentary metrics (Sul full prefilter)

| Metric | Value |
|--------|------:|
| Universe / read / complete | 27634 / 27634 / True |
| docs_processed_deep (PDF download work) | **205** |
| official_pdf_text_extracted | **201** |
| pdfs_downloaded / arquivos_listed | 288 / 1706 |
| regime_14133_proven (funnel) | 89 |
| OUTREACH_READY* | **0** |
| DOCUMENT_REQUEST suppliers | 39 |

### Definition (fail-closed)

- `docs_processed_deep` = contracts where PNCP compra PDF download was performed (not portal HTML).
- `official_pdf_text_extracted` = PDF text extracted via PyPDF2 from edital/TR/contrato.
- Portal HTML / object_field_scan **never** set `docs_accessible` / `official_text_extracted`.

## Recovery path

1. PNCP contrato API → `numeroControlePncpCompra`
2. PNCP compra `/arquivos` list
3. Download PDF (edital priority)
4. PyPDF2 text extract with page markers
5. Clause/regime/index only from official text

## Human review

`human_review_top30_suppliers.*` uses official PDF evidences with `page`/`hash` when present.  
Águas de Palhoça / water concessions excluded from construction ICP.

## Exhaustion

≥200 contracts with real PDF deep work; 0 OUTREACH_READY without inventing certainty.
