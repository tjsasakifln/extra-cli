# Database Isolation Plan

**Campaign:** `NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01`  
**Gate contribution:** `PARALLEL_ISOLATION_PASS`

## 1. Active campaign database (FORBIDDEN for writes)

| Field | Value |
|-------|--------|
| Port | 5433 |
| Database | `extra_test` |
| Container | `extraconsultoria-test-db-1` |
| Writer | `run_contracts_90d_pilot` PID 27115 |
| Volume snapshot | `pncp_supplier_contracts` ~2.27M rows / ~2.5 GB |

### Allowed access

- **Default:** none
- **If indispensable:** read-only `SELECT` / `EXPLAIN` only, short queries, no locks, no DDL, no vacuum, no `ANALYZE` on hot tables during peak write
- Never set `LOCAL_DATALAKE_DSN` to this DSN in campaign scripts by default

## 2. This campaign isolated database (ALLOWED)

| Field | Value |
|-------|--------|
| Port | **5435** |
| Database | `extra_national_intelligence_test` |
| Container | `extra-national-intel-db` (postgres:16-alpine) |
| User | `test` |
| DSN (masked) | `postgresql://test:***@127.0.0.1:5435/extra_national_intelligence_test` |
| Env var for this campaign | `NATIONAL_INTEL_DSN` (preferred) or local `.env.campaign` gitignored |

## 3. Schema strategy on isolated DB

1. Apply project migrations additively via `python3 -m scripts.ops.apply_migrations --dsn "$NATIONAL_INTEL_DSN"`
2. Load **fixtures only** for unit/integration tests (no 3y backfill)
3. Optional later: read-only dump/sample from active DB **after** HC campaign completes — never during live backfill
4. Analytical layer (views/marts) lives in schema `intel` (proposed) or `public` views with explicit `v_intel_*` prefix — final decision in ADR after inventory

## 4. Port matrix

| Port | Service | Campaign ownership |
|------|---------|-------------------|
| 5432 | recuperador-postgres | unrelated — do not use |
| 5433 | extra_test | HC backfill — protected |
| 5435 | extra_national_intelligence_test | **this campaign** |
| 54399 | smartlic-datalake | SmartLic — do not use |

## 5. Temporary directories

| Path | Purpose |
|------|---------|
| `artifacts/campaigns/NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01/` | Campaign evidence |
| `tmp/national-intel/` (gitignored if created) | Scratch only |
| Never | `data/contracts_checkpoints/hc_closure_*` |

## 6. Verification commands

```bash
# Isolated DB healthy
docker exec extra-national-intel-db pg_isready -U test -d extra_national_intelligence_test

# Confirm distinct ports
ss -tlnp | grep -E '5433|5435'

# Never run migrations against 5433 from this campaign
echo "$NATIONAL_INTEL_DSN" | grep -q ':5435/' && echo OK || echo FAIL
```
