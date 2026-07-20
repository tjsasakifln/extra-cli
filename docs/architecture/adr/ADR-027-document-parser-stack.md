# ADR-027 — Document parser stack: deferred (no corpus)

- **Status:** ACCEPTED (`DEFERRED_NO_CORPUS`)  
- **Date:** 2026-07-20  
- **Campaign:** ARCH-RESET-2026-07-20  
- **Supersedes:** any prior wording of this ADR that claimed `KEEP_CURRENT_STACK` based only on synthetic microbench  

## Decision

**Do not claim KEEP_CURRENT_STACK as a proven adoption decision** from this spike alone.

**Honest status:** **`DEFERRED_NO_CORPUS`**. Three synthetic ReportLab PDFs are **not** a valid basis for parser adoption or “keep current” performance claims across multi-column, table, and scanned editais.

## What is already true (without new claim)

- Production continues to use existing extractors; **no new production parser dependency is added**.  
- PyMuPDF / PyMuPDF4LLM remain **blocked** by AGPL/commercial license until a separate license ADR.  
- pdfplumber / pypdf may be used in isolated spikes only until corpus criteria are met.

## Re-open criteria (engine comparison)

Minimum versionable/regenerable corpus (no private secrets in Git):

| Stratum | Minimum |
|---------|--------:|
| digital_simple | 5 |
| multicolumn | 5 |
| tables | 5 |
| scanned | 5 |

Then compare engines with page-order, money, date, table metrics. Only then may ADR choose KEEP_CURRENT, ADOPT_X, or REJECT_X.

## Evidence

- `docs/ops/campaigns/ARCH-RESET-2026-07-20/spikes/DOCUMENTS/DECISION.md`  
- Synthetic microbench (`benchmark.json`) is **exploratory only**, not adoption proof  
- Evaluator (remediation): `scripts.architecture.spike_g_documents_honest` when present on branch #62  
