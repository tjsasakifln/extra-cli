# Spike E — dbt snapshots

**Decision:** `REJECTED_WITHOUT_EXPERIMENT`

**Honest statement:** No dbt project was installed or executed against a ≥200 opportunity temporal corpus in this campaign. The file `benchmark.json` records **design limitations and a tiny synthetic status-path sketch only** — it is **not** an SCD2 concordance experiment.

**Re-open criteria:**

1. Isolated Postgres schema (non-production authority)  
2. Dataset ≥200 opportunities with gold status transitions  
3. Measured concordance on corpus  
4. ADR superseding ADR-026 with experiment artifacts  

**Production dependency added:** no  

**ADR:** ADR-026 (rewritten for honesty; same file path)  
