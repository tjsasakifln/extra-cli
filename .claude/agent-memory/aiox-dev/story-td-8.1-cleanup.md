---
name: story-td-8.1-cleanup
description: TD-8.1 deduplication — 4 identical pairs deleted, 6 divergent preserved. AC-C2 features found in intel_excel and intel_report.
metadata:
  type: project
---

# Story TD-8.1 Phase 1 + 3 — Deduplication Results

**Date:** 2026-07-11
**Phases:** 1 (Deduplication — done) + 3 (psycopg2 — done), Phase 2 (subprocess — skipped, 12h pending)

## Key Finding: Story inaccuracy

The story claimed 6 identical + 4 divergent pairs. Reality: **4 identical + 6 divergent**.

Pairs 3 (intel-excel) and 5 (intel-report) were listed as identical but actually diverged — the snake_case versions have AC-C2 features (`_build_excel_fonte_status`, `_build_excel_pncp_status`, `_build_status_das_fontes`) not in the kebab versions. **Do NOT delete intel_excel.py or intel_report.py** until the AC-C2 features are merged into the canonical kebab versions.

## Deleted (identical snake_case)

- `scripts/intel_analyze.py`
- `scripts/intel_enrich.py`
- `scripts/intel_extract_docs.py`
- `scripts/generate_report_b2g.py`

## Preserved (divergent)

Diffs saved in `docs/td-003/diffs/`:

| File | Diff size | Key difference |
|------|-----------|---------------|
| intel-excel.diff | 46 lines | AC-C2 fonte/pncp status functions |
| intel-report.diff | 152 lines | AC-C2 _build_status_das_fontes section |
| collect-report-data.diff | 18 lines | Portal config + email branding |
| generate-proposta-pdf.diff | 12 lines | Extra Consultoria vs CONFENGE branding |
| intel-collect.diff | 447 lines | v1.5 upgrades (429 handling, chunked) |
| intel-validate.diff | 31 lines | UTC import, top20 fallback |

## Requirements change

`psycopg2-binary>=2.9.9` replaced with `psycopg2>=2.9.9` (with dev comment preserved).
