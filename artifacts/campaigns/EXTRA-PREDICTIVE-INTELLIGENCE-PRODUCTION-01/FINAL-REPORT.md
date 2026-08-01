# FINAL REPORT — EXTRA-PREDICTIVE-INTELLIGENCE-PRODUCTION-01

## 1. Initial state (factual)

- `bid_simulator` exposed `p_vitoria_pct` / “lance ótimo” without training, backtest, or calibration.
- Extra profile critical operational fields PENDING.
- Production corpus: ~4.48M contracts; no participant lists; no estimated↔adjudicated discount pairs in `opportunity_intel`.

## 2. What was implemented

- Honesty layer: heuristic reclassified (`method=UNVALIDATED_HEURISTIC`, `prediction_claim_allowed=false`).
- Claim registry (7 claims, gated states).
- Migration `068_predictive_intelligence.sql` (immutable predictions).
- PIT dataset builders (demand 30/60/90, P2A, P3) + leakage fail-closed.
- Baselines + HistGBM/logistic + walk-forward + Platt calibration.
- Facade CLI, workspace integration, profile calibration, shadow systemd unit templates.
- Campaign evidence pack under `artifacts/campaigns/EXTRA-PREDICTIVE-INTELLIGENCE-PRODUCTION-01/`.

## 3. Backtest results (120k AEC contract sample from production)

| Target | n | Best model | BSS | Gate |
|--------|---|------------|-----|------|
| demand_30d | 143,591 | hist_gbm_clf | ~0.052 | BACKTEST_FAILED |
| demand_60d | 137,118 | hist_gbm_clf | ~0.080 | BACKTEST_FAILED |
| demand_90d | 130,449 | logistic_l2 | ~0.096 | BACKTEST_FAILED |
| competitive_winner_p2a | 198840 | hist_gbm_clf | ~0.871 | HISTORICAL_BACKTEST_PROVEN |
| winning_discount_p3 | 0 | — | — | DATA_BLOCKED |
| participation P2B | — | — | — | DATA_BLOCKED |
| Extra win P4 / optimal bid P5 | — | — | — | DATA_BLOCKED |

Thresholds were **not** lowered.

## 4. Commercial recommendation

**PARTIAL_CLAIM_ALLOWED**

- Internal/shadow: competitive winner likelihood with explicit claim state.
- **Forbidden** externally: “inteligência preditiva comprovada”, Extra win probability, lance ótimo, demand forecast “available”, fully proven suite.

## 5. Prospective evidence

None. Historical walk-forward is backtest, not soak. See `prospective-evidence-status.json`.


## Skeptic fix (P2A)

- Candidate set is pre-result only; cold-start winners drop the outcome.
- Never-seen supplier `days_since_supplier_win=9999`.
- Claim stays `HISTORICAL_BACKTEST_PROVEN` (not SHADOW) until live scheduled emission.


## Skeptic fix (outcomes)

- Demand resolution: empty events without coverage → `rejected_invalid_negative` (not label 0).
- P2A: procurement_id → observed winner join; immature if missing; rejects outcome before as_of.
- Drift metrics ignore rejected non-scorable outcomes.
