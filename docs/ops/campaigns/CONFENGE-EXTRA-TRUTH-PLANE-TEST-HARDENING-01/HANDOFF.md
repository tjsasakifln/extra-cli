# HANDOFF — CONFENGE-EXTRA-TRUTH-PLANE-TEST-HARDENING-01

## What landed in-repo

1. **PNCP live probe** shares `scripts.crawl.pncp_contract` as the only
   page-size source. The crawler still **clamps**. The probe **fails
   before HTTP** on an explicit illegal size.
2. Self-inflicted illegal requests classify as `INTERNAL_DEFECT` or
   `CONFIGURATION_ERROR`. A legal external 403/429/5xx/timeout keeps the
   existing taxonomy. Empty live body is not a schema pass.
3. **real_db admission** names exactly one of `DB_UNAVAILABLE`,
   `DB_REACHABLE_SCHEMA_MISSING`, `DB_READY` before product SQL.
   `REQUIRE_REAL_DB=1` + explicit DSN never skips and never installs
   MagicMock. Optional mode skips fast with the named reason.
4. Canonical suites (concorrentes, valores, idempotência, opportunity
   integration) and `national_intel` go through that admission.
   `tests/national_intel/conftest.py` no longer refuses canonical `:5433`
   when `DATABASE_URL` / `LOCAL_DATALAKE_DSN` is set.

## What this host did not prove

- Live PNCP **200 + envelope/pagination**. This run classified a public
  503 as `http_5xx_server_error` on a URL with `tamanhoPagina=50`.
- Fully migrated PostgreSQL. No listener on 5432–5436 here. Unit
  preflight with injected openers is the bar that passed.

Do **not** close #351 / #285 / #341 / #343 on this PR.

## How to re-prove on a host with Postgres

```bash
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"
python3 -m scripts.ops.apply_migrations --dsn "$LOCAL_DATALAKE_DSN"
export REQUIRE_REAL_DB=1
python3 -m pytest tests/ -m real_db -q --tb=short
python3 -m pytest tests/test_golden_path_concorrentes_report.py \
  tests/test_golden_path_valores_report.py \
  tests/test_golden_path_idempotency.py \
  tests/test_opportunity_integration.py \
  tests/national_intel/ -q --tb=short
python3 -m scripts.ops.source_contract_tests --live --json
```

Never log the DSN. Never treat skip as pass.
