# CONFENGE-EXTRA-TRUTH-PLANE-TEST-HARDENING-01

Surgical truth-plane hardening. Green and red must mean something true:
the PNCP live probe never sends illegal `tamanhoPagina`, and `real_db`
tests never treat MagicMock or a late `UndefinedTable` as product truth.

Issues #351 / #285 / #341 / #343 stay **open**. Host live execution is
still required for their remaining ACs.

## Stamp

```
CAMPAIGN=CONFENGE-EXTRA-TRUTH-PLANE-TEST-HARDENING-01
BASE_SHA=9c5e7d47f99902d9d97cf479aefbba8cd391a14d
PNCP_PAGE_SIZE_SOURCE=scripts.crawl.pncp_contract.require_legal_pncp_page_size
PNCP_MIN_PAGE_SIZE=10
INVALID_REQUEST_CLASS=INTERNAL_DEFECT|CONFIGURATION_ERROR
REAL_DB_POLICY=REQUIRE_REAL_DB=1+explicit DSN => real psycopg2 or named preflight fail; optional => skip with reason code
REAL_DB_MOCK_ALLOWED=false
DB_UNAVAILABLE_BEHAVIOR=fail under REQUIRE_REAL_DB=1; skip with DB_UNAVAILABLE without opt-in
DB_SCHEMA_MISSING_BEHAVIOR=DB_REACHABLE_SCHEMA_MISSING before product SQL (fail if required, skip if optional)
DB_READY_TESTS=named preflight admits; MagicMock refused
LATE_UNDEFINED_TABLE_FAILURES=0
MERGED=false
DEPLOYED=false
FINAL_VERDICT=TRUTH_PLANE_TEST_HARNESS_PROVEN
EXACT_RESIDUALS=#351 live PNCP envelope/pagination on a 200 body (this host: HTTP 503 http_5xx_server_error with tamanhoPagina=50); #285/#341/#343 execution on a fully migrated ephemeral PostgreSQL (this host: no listener on 5432-5436)
```

HEAD SHA, PR number, test/gate counts are filled in `STAMP.txt` after
commit and PR open.

## Policy (same as docs/DEVELOPMENT.md)

- Crawler keeps clamping `PNCP_PAGE_SIZE` to `[10, 50]` via `legal_pncp_page_size()`.
- Probe uses `require_legal_pncp_page_size()`: illegal env is
  `CONFIGURATION_ERROR`, illegal constructed `tamanhoPagina` is
  `INTERNAL_DEFECT`. Neither hits the network. Neither is
  `EXTERNAL_TRANSIENT` / SUCCESS / ZERO.
- Empty live body is not schema proof.
- Canonical DSN: `LOCAL_DATALAKE_DSN` or `DATABASE_URL`. Port 5436 is not exclusive.
- `REAL_DB_MOCK_ALLOWED=false` under opt-in.

## Out of scope (unchanged)

Coverage thresholds, national denominator, domain migrations,
`public_integrity`, adapters/fontes, crawler production loop semantics
beyond sharing the legal page-size default.
