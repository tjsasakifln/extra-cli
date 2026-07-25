# ADR-034 — CONFENGE commercial lead evidence model

**Status:** Accepted (campaign branch)  
**Date:** 2026-07-25  
**Campaign:** CONFENGE-COMMERCIAL-READY-01

## Context

DOD §2.7 requires a commercial queue for CONFENGE based on observable contract signals. Prior modules (`national_intel`, `linkage`, consulting packs) provide foundations but not a human-operable lead queue with explainable scoring and feedback ledger.

## Decision

1. **Unit of lead:** pessoa jurídica com CNPJ14 válido (não órgão, não PF).
2. **Signal model:** each signal is FIRED | NOT_FIRED | NOT_COMPUTABLE. Missing data never becomes zero pain or silent penalty.
3. **Score:** weighted sum of FIRED strengths after correlation dampening; fully decomposable.
4. **Language:** prioritization / observed need-fit only — never purchase propensity.
5. **Evidence:** every FIRED signal carries contract/event provenance (id, organ, object, value+semantics, date, source).
6. **Persistence:** migration 062 adds run/lead/override/ledger/exclusion tables without altering contract facts.
7. **Snapshot gate:** real authenticated dump with sha256; fixtures cannot satisfy the real-data gate.
8. **Human review:** export template leaves decisions empty; Tiago acceptance is external to technical PASS.

## Consequences

- `CONFENGE_COMMERCIAL_READY` remains a DOD human gate even if campaign technical PASS.
- Official acts may be empty → related signals stay NOT_COMPUTABLE.
- Ranking may be empty or <20 if few companies match profile — system must declare insufficiency, not pad.

## Non-decisions

- No change to dual coverage denominators.
- No production/soak access.
- No auto-merge of filiais into grupos econômicos without explicit future rule.
