# DOC-DEEP-ANALYSIS-DECISION-INTEL-01 — Final report

## Thesis

**Baixar PDF é coleta. Consultoria começa quando o conteúdo vira decisão.**

Each published document in a multi-doc case pack is classified, extracted with locators (page / sheet!cell), checklisted, cross-checked for conflicts, and folded into a human-gated recommendation — with independent `verify PASS`.

## What was proven (fixture / deterministic)

| Pipeline | Verify | Decision output | Locators |
|----------|--------|-----------------|----------|
| `edital_case` multi-doc pack (5 files) | **PASS** | **REVIEW** + disclaimer + 36-point checklist | `page:N` + **`sheet:Orçamento!A1`…** on planilha |
| `budget_audit` golden workbook | **PASS** + reconciliation **PASS** | items / BDI / arithmetic findings | sheet!cell |

### Planilha in the multi-doc case (not a separate entrypoint)

| Field | Value |
|-------|--------|
| `sample_planilha.xlsx` type | `PLANILHA_ORCAMENTARIA` |
| `extraction_status` | **OK** |
| `quality_status` | **OK** |
| blocks / tables | 7 / 2 (Orçamento + BDI sheets) |
| cell samples | `sheet:Orçamento!A1`, `sheet:BDI!A1`, … |

### Root cause (not “text path limit”)

Objects are content-addressed as **bare SHA-256 paths** (no `.xlsx` suffix). `openpyxl.load_workbook(str(path))` rejects extension-less paths → `EXTRACTION_FAILED` for every planilha in `edital_case`.

**Fix:** load via `BytesIO(path.read_bytes())` in `extract_xlsx`.

Also: filename `*planilha*.xlsx` must not be reclassified as pure `BDI` merely because a BDI sheet exists.

### Suite

- `tests/edital_case/` — extensionless xlsx + put_object path + classify planilha + citation regression
- `tests/budget_audit/` — golden e2e verify PASS

## DoD §2.6

Fixture-proven capability for triage + deep analysis + planilha cells in the **same** case pack.  
Not: 95% coverage, live ente, parecer jurídico, BDI legal/abusivo.

## Artifacts

See `acceptance-manifest.json` and `evidence/` (MD + JSON only; no campaign HTML).
