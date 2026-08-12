# ADR-035 — CONFENGE authoritative target-fit feed

**Status:** Proposed
**Date:** 2026-08-12

## Context

`confenge.outreach.v1` was generated from the send-ready/hot-set cohort. A
company that later became OUT, insufficient, stale, DNC or absent from the ICP
could disappear from the next feed. A stateful consumer could then retain the
older CONFIRMED authorization because it never received a revocation.

## Decision

1. The wire artifact is a full decision snapshot, not a send-ready selection.
2. Expensive intelligence and contact enrichment may remain hot-set bounded;
   target-fit decisions may not.
3. Every addressable supplier root is emitted once with non-null class,
   freshness, classifier version, computation timestamp, source watermark,
   evidence IDs, send tier and `email_send_ready`.
   Production resolves these decisions from the mode-aware published store;
   embedded universe decisions are restricted to offline fixture runs.
4. Valid-CNPJ exclusions and DNC remain in the decision universe. An omitted
   materialization becomes `TARGET_FIT_MISSING`, `target_fit_tombstone=true`
   and `email_send_ready=false`.
5. Freshness describes decision currency independently of eligibility. A fresh
   OUT/INSUFFICIENT decision is fresh but ineligible.
6. Records and cursors are ordered by source watermark, computation timestamp
   and CNPJ. Invalid or non-timezoned decision timestamps fail closed.
7. The manifest declares the reconciled universe cardinality and exposes
   coverage, monotonicity and omission-safety gates. Partial/smoke exports are
   not authoritative.
8. A pilot selection cannot be exported as this schema without also providing
   the full authoritative universe and target-fit snapshot.
9. The historical PREVENCAO alias `01489370000105` is emitted canonically as
   `14893700000105` (`14.893.700/0001-05`) without rewriting raw evidence.

## Consequences

- Feed volume follows decision-universe size rather than send capacity.
- OUT, insufficient and tombstone rows contain little or no contact/intelligence
  data but still revoke stale authorization explicitly.
- Operational raw chunks remain outside Git under ADR-020; small manifests,
  hashes and reproducible tests are the review evidence.
- No dispatch or campaign authorization is implied by successful export.
