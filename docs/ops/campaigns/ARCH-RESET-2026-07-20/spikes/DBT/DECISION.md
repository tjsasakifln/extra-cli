# Spike E — dbt snapshots

**Decision:** `REJECTED_WITHOUT_EXPERIMENT`

**Honest statement:** No dbt project was installed or executed against a ≥200 opportunity temporal corpus in this campaign. Any prior synthetic 5-dict “benchmark” is **not** experimental evidence.

**Re-open criteria:**

1. Isolated Postgres schema (non-production authority)
2. Dataset ≥200 opportunities with gold status transitions
3. Measured concordance on corpus
4. ADR superseding this decision

**Production dependency added:** no

Evaluator: `scripts.architecture.spike_e_dbt_honest.evaluate_dbt_spike`
