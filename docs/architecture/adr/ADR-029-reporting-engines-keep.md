# ADR-029 — Reporting engines: keep openpyxl + ReportLab

- **Status:** ACCEPTED  
- **Date:** 2026-07-20  

## Decision

**KEEP_OPENPYXL_REPORTLAB** for production weekly/decision packs.  
XlsxWriter and fpdf2 remain **REFERENCE_ONLY** until pack-level parity on real Extra packs (same run_id, aggregates, editability needs).

## Rationale

openpyxl already supports read/edit paths; XlsxWriter is write-only. ReportLab already generates executive PDFs. Switching engines without regression on real packs increases risk without proven utility.
