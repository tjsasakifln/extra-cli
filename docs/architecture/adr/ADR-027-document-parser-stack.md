# ADR-027 — Document parser stack (keep current)

- **Status:** ACCEPTED  
- **Date:** 2026-07-20  

## Decision

**KEEP_CURRENT_STACK** for production: existing extractors + optional pypdf paths.  
**Do not adopt PyMuPDF/PyMuPDF4LLM** without explicit AGPL/commercial license ADR.  
**Do not add pdfplumber** to production until private multi-column/scanned corpus proves net gain.

## Evidence

Synthetic digital PDF microbench in spike G (`spikes/DOCUMENTS/benchmark.json`).
