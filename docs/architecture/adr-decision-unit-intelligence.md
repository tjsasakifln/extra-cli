# ADR: Decision-Unit Intelligence + Reachability

**Status:** Accepted for implementation  
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
