# Migration 059 proof (isolated DB)

**DSN:** `postgresql://test:***@127.0.0.1:5435/extra_national_intelligence_test`  
**Container:** `extra-national-intel-db`

## Applied

- Full upgrade via `scripts.ops.apply_migrations` for 001–057
- `058_dual_capability_coverage_views.sql` and `059_national_contracts_intelligence_layers.sql` applied via `psql -f` and ledger-registered

## Views present

- `v_intel_contracts_raw_national`
- `v_intel_contracts_geo_sc`
- `v_intel_supplier_geo`
- `v_intel_agency_profile`

## Non-actions

- No migration on port 5433 / `extra_test`
- No DROP of production tables
