# ADR-069 — Predictive intelligence claim gates

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


## Relationship to Decision Memory (migration 068)

Commercial operational facts (human decisions, participation, win/loss, contract,
margin) are owned by **Decision & Outcome Memory** (`dm_*` / migration `068`).

`predictive_outcomes` is an **evaluation projection** for model metrics (Brier, drift).
It may reference `dm_outcome_events.event_id` via `dm_outcome_event_id` when a
commercial fact is the ground truth. Link states:

| link_status | Meaning |
|-------------|---------|
| `LINKED_DM` | Reconciled to a Decision Memory outcome event |
| `UNLINKED_LEGACY` | Observed label from lake/procurement without DM row |
| `HISTORICAL_UNVERIFIED` | Imported/historical without prospective DM write |
| `NOT_APPLICABLE_MODEL_ONLY` | Model evaluation label (e.g. demand coverage) not a commercial DM fact |

Never invent DM rows solely to complete predictive metrics.
