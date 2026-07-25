# ADR-031 — Edital Case Evidence Model

**Status:** Proposed (campaign branch; not yet indexed on main)  
**Date:** 2026-07-24  
**Campaign:** EDITAL-TECHNICAL-TRIAGE-CASE-PACK-01  

## Context

The workspace command `edital analyze` only scaffolds a checklist with `PENDING`
items and optional PDF text dump. Operational triage of engineering tenders
requires immutable source objects, page/cell locators, cross-document checks,
missing-annex detection, and fail-closed recommendation — without colliding with
PostgreSQL migrations or parallel campaigns.

## Decision

1. Introduce an **independent** package `scripts/edital_case/` with CLI:
   `python3 -m scripts.edital_case`.
2. Store each case as a **content-addressed file tree** (SHA-256 objects).
   No PostgreSQL, no migrations, no SQLite canonical store in this campaign.
3. Every non-pending checklist item and finding must carry:
   `document_id`, `document_sha256`, locator (page/paragraph/cell), excerpt,
   rule_id, confidence, analysis.
4. Recommendation enum: `GO | REVIEW | NO_GO` with fail-closed rules:
   incomplete Extra profile blocks GO; expired critical dates → NO_GO;
   interpretive legal items stay `NEEDS_HUMAN`.
5. Reports (MD/HTML/XLSX/PDF) are pure projections of the same JSON model;
   quantitative divergence fails reconciliation.
6. Hot shared files (`scripts/workspace/*`, `Makefile`, `DOD.md`, ADR INDEX)
   are **not** modified in this branch; integration snippets live under
   `integration-handoff/EDITAL-TECHNICAL-TRIAGE-CASE-PACK-01/`.

## Consequences

- Positive: parallel-safe, auditável, reproducible offline case packs.
- Positive: citations are verifiable against stored extractions.
- Negative: no national search UI integration until handoff is merged.
- Negative: OCR not automatic; scanned PDFs mark `OCR_REQUIRED` / `EXTRACTION_FAILED`.

## Alternatives considered

- Extend `scaffold_edital` in place → rejected (touches hot files; incomplete model).
- PostgreSQL case tables now → rejected (migration collision with #129/#130).
