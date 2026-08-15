# ADR: Decision-Unit Intelligence + Reachability

**Status:** Accepted and incrementally implemented
**Date:** 2026-08-14  
**Branch:** `feat/decision-unit-intelligence`

## Decision

The extra-cli answers, per account and per CONFENGE offer:

> Who probably participates in the buying decision, which real people match
> those roles, and by which defensible routes can we reach that unit now?

It does **not** treat “named email explicitly published” as success.

## Consequences

- Decision-Unit and Reachability are separate models.
- `INFERRED` is never labeled `OBSERVED`, and is not treated as useless.
- Company switchboard + named person = `R3` / `ROUTES_TO_NAMED_PERSON`.
- QSA cadastre is identity/authority, not automatic economic buyer.
- `#370` remains the email-safe Warmbly canary. This epic does not close it.
- Work stays off PR `#371`.
- There is no `AUTO_SEND`.
- Public web search is a first-class bounded provider, not an untracked fallback.
- Search, crawl, domain resolution, and verification remain replaceable adapters.
- SearXNG is allowed only across an HTTP service boundary; its AGPL code is not embedded.
- The local canary may use the MIT-licensed DDGS adapter. Static HTML crawling reuses existing dependencies.
- extra-cli remains the identity/reachability truth plane; Warmbly remains the activation/outcome plane.

Operational contract: [`../commercial-intelligence/contact-resolution.md`](../commercial-intelligence/contact-resolution.md).
