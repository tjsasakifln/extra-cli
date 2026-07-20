# Spike G — document parsers

**Decision:** `DEFERRED_NO_CORPUS`

**Honest statement:** 3 synthetic ReportLab PDFs are **not** a valid basis for `KEEP_CURRENT_STACK` adoption claims. Required corpus strata: ≥5 simple digital, ≥5 multicolumn, ≥5 tables, ≥5 scanned (versionable or regenerable, no private data in Git).

**Re-open criteria:**

1. Corpus counts meet strata minima
2. Engine comparison including layout/table metrics (Camelot optional)
3. PyMuPDF only with AGPL/commercial license ADR

**Production dependency added:** no

Evaluator: `scripts.architecture.spike_g_documents_honest.evaluate_document_parser_spike`
