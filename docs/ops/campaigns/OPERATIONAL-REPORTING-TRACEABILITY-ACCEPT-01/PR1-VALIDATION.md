# PR1 validation — OPERATIONAL-REPORTING-TRACEABILITY-ACCEPT-01

## Scope

- Fail-closed SQL/`_error` propagation in `scripts/reports/operational_outputs.py`
- Unified operational metadata via `scripts/reports/run_metadata.py`
- Eight operational lists with SUCCESS_ZERO / NOT_READY for legitimate empty
- Campaign freeze + premortem (no DOD promotion)

## Manual checks (2026-07-28)

1. **SQL error → non-zero exit**
   - Unit: `test_q_fail_closed_raises_on_sql_error`, `test_main_sql_error_nonzero_exit`, `test_live_sql_error_propagates_nonzero`
   - `_write_csv` refuses `_error` rows

2. **Zero rows → SUCCESS_ZERO**
   - Live: `python3 -m scripts.reports.operational_outputs --dsn $LOCAL_DATALAKE_DSN --out …/live/lists --json`
   - Result: `status=SUCCESS_ZERO`, `reliability=NOT_READY`, limitations documented, 8 CSV headers present, 0 data rows

3. **GO / REVIEW / NO_GO honesty**
   - Empty DB does not invent GO; ranking counts all 0 with limitations

4. **Manifest fields**
   - `run_id`, `generated_at`, `code_sha`, `schema_version`, `dataset_hash`, `source`, `capability`, `period`, `parameters`, `reliability`, `limitations`, `errors`, `duration_seconds`, `artifact_hashes`

5. **Tests**
   - `REQUIRE_REAL_DB=1 pytest tests/test_operational_outputs.py` → 12 passed
   - Related suite (deliverable + weekly + golden fail-closed) → 53 passed

## Not in this PR

- Analytic reports, real PDF/Excel package, golden path valores wiring, DOD promotion (PR2/PR3)
