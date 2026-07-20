# Spike E — dbt-core snapshots

**Decision:** `REJECTED_SPIKE`

**Reason:** No net reduction of operational SQL yet; dual truth risk with PG migrations; SCD2 snapshots do not solve juridical event time or missed intermediate states.

**Production dependency added:** False

Evidence: `benchmark.json`
