# ADR-027 — Document parser stack: deferred (no corpus)

- **Status:** ACCEPTED (`DEFERRED_NO_CORPUS`)  
- **Date:** 2026-07-20  
- **Campaign:** ARCH-RESET-2026-07-20  
- **Aligned with:** PR #60 tip ≥ `728ee82` and PR #62  

## Decision

**Do not claim KEEP_CURRENT_STACK** from synthetic microbench alone.

**Honest status:** **`DEFERRED_NO_CORPUS`**. Need ≥5 PDFs per stratum (simple / multicolumn / tables / scanned) before engine adoption.

Production keeps existing extractors with **no new parser dependency**. PyMuPDF remains AGPL-gated.

## Evidence

- `docs/ops/campaigns/ARCH-RESET-2026-07-20/spikes/DOCUMENTS/DECISION.md`  
- `scripts.architecture.spike_g_documents_honest.evaluate_document_parser_spike`  
