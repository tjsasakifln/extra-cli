## Summary

Implements the EXTRA-PREDICTIVE-INTELLIGENCE-PRODUCTION-01 campaign:

- **Honesty:** `bid_simulator` no longer publishes calibrated probability language; outputs are `heuristic_scenario_score` with `method=UNVALIDATED_HEURISTIC` / `prediction_claim_allowed=false`. Static honesty tests included.
- **Claim registry:** 7 canonical claims with gated states; only `PRODUCTION_AVAILABLE` authorizes external availability language.
- **PIT + leakage:** Point-in-time datasets for demand (30/60/90d), competitive winner (P2A), discount (P3); fail-closed leakage audits.
- **Backtests (real production sample, 120k AEC contracts):**
  - Demand: **BACKTEST_FAILED** (BSS under 0.10; thresholds not lowered)
  - P2A competitive: **HISTORICAL_BACKTEST_PROVEN → SHADOW_OPERATIONAL**
  - P3 / P2B / Extra win / optimal bid: **DATA_BLOCKED** (honest blockers)
- **Ops:** facade `python -m scripts.predictive`, workspace `predictive-status`/`forecast`, migration **069** (`069_predictive_intelligence.sql` — immutable predictions + evaluation projection), shadow systemd templates, campaign evidence pack.
- **Migration ownership (post-merge on main):**
  - **068** = Decision & Outcome Memory (`068_decision_outcome_memory.sql`, PR #198) — canonical commercial facts in `dm_*` / `dm_outcome_events`.
  - **069** = Predictive intelligence (`069_predictive_intelligence.sql`, this PR) — model datasets, immutable predictions, outcomes projection.
  - Integration: `predictive_outcomes.dm_outcome_event_id` → `dm_outcome_events.event_id` (optional FK; commercial ground truth remains Decision Memory only).
- **Commercial recommendation:** `PARTIAL_CLAIM_ALLOWED` — **not** `CLAIM_ALLOWED`. No “inteligência preditiva comprovada”.

## Campaign artifacts

`artifacts/campaigns/EXTRA-PREDICTIVE-INTELLIGENCE-PRODUCTION-01/` (`FINAL-REPORT.md`, `result.json`, `claim-state.json`, backtest/calibration/DQ packs).

## Test plan

- [x] `pytest tests/predictive/ -q` (27 passed pre-merge; post-merge revalidated on final main)
- [x] Migration **069** + immutability trigger on local DSN (after **068** Decision Memory)
- [x] Dual entrypoints: `python -m scripts.predictive claims`, `python -m scripts.workspace predictive-status --json`
- [x] Production sample walk-forward backtests (see campaign `backtest-summary.json`)
- [x] Decision Memory link columns on `predictive_outcomes` (`dm_outcome_event_id`, `link_status`)

## Explicit non-claims

- No prospective soak completed (calendar blocker).
- Extra profile PENDING fields block P4/P5.
- Heuristic bid scores are **not** win probabilities.
- No “inteligência preditiva comprovada” / full commercial claim authorization.
- Predictive timers remain shadow / not production-enabled by default.
- `predictive_outcomes` is an evaluation projection, **not** a second commercial outcomes ledger.

