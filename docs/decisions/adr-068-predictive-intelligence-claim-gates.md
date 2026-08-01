# ADR-068 — Predictive intelligence claim gates

**Status:** Accepted  
**Date:** 2026-08-01  
**Campaign:** EXTRA-PREDICTIVE-INTELLIGENCE-PRODUCTION-01

## Context

The legacy `bid_simulator` exposed `p_vitoria_pct` and “lance ótimo” language without
labeled training, temporal backtest, calibration, or prospective evidence. That blocked
defensible commercial claims of “inteligência preditiva”.

## Decision

1. Separate four capability families (demand, competitive, winning outcome, Extra personalization)
   with independent claim gates.
2. Maintain a canonical claim registry with explicit states; only `PRODUCTION_AVAILABLE`
   authorizes external availability language.
3. Point-in-time datasets with fail-closed leakage checks are mandatory.
4. Walk-forward validation and calibration on held-out data are mandatory for probabilistic claims.
5. Shadow mode and prospective soak are required before production claims; historical replay
   is never sold as prospective evidence.
6. Legacy heuristic outputs are reclassified as `method=UNVALIDATED_HEURISTIC` with
   `prediction_claim_allowed=false` and honest vocabulary.

## Consequences

- Metric thresholds are not silently lowered; insufficient n → `DATA_BLOCKED`.
- Extra win probability and optimal bid remain blocked while profile PENDING fields and
  participant-level labels are missing.
- P2B participation remains `DATA_BLOCKED` without real participant lists.

## Alternatives considered

- Keep heuristic scores labeled as probabilities — rejected (commercially indefensible).
- Deep learning without baselines — rejected (complexity without auditability).
- LLM-generated probabilities — rejected (not statistical models with PIT guarantees).
