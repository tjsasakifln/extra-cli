# ADR-026 — dbt snapshots: rejected without experiment

- **Status:** ACCEPTED (`REJECTED_WITHOUT_EXPERIMENT`)  
- **Date:** 2026-07-20  
- **Campaign:** ARCH-RESET-2026-07-20  
- **Aligned with:** PR #60 tip ≥ `728ee82` and PR #62  

## Decision

**Do not adopt dbt-core / dbt snapshots** in the operational Extra weekly pipeline.

**Honest status:** **`REJECTED_WITHOUT_EXPERIMENT`**. No dbt project was executed against a ≥200 opportunity temporal corpus. Synthetic status-path sketches are design notes only.

## Re-open criteria

Isolated schema + ≥200 gold transitions + measured concordance + superseding ADR.

## Evidence

- `docs/ops/campaigns/ARCH-RESET-2026-07-20/spikes/DBT/DECISION.md`  
- `scripts.architecture.spike_e_dbt_honest.evaluate_dbt_spike`  
