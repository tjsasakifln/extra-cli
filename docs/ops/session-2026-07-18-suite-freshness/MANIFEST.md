# Session — suite inventory + entity freshness

**Story:** `ROI-cand-dyn-slice-a53bdc0173af`  
**Cycle:** `cyc-2026-07-18T164226Z`  
**Candidate:** `cand-dyn-slice:a53bdc0173af`  
**Branch:** `extra-roi/cand-dyn-slice-a53bdc0173af`  
**Date:** 2026-07-18  
**Implementer:** delivery-engineer  

## Bound DoD items

| ID | Text (abbrev) | Recommendation |
|----|---------------|----------------|
| `dod:b06848ca7f90` | Suíte global completa verde | **LEAVE OPEN** — full suite not green; critical path green with 24 honest skips |
| `dod:925f2c0e059a` | Freshness coverage mensurável por entidade dentro dos SLAs | **FLIP after independent QA** — entity-level reporter + live PG proof |

## 1. Entity freshness (PRIMARY)

```bash
export LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/extra_test
python3 -m scripts.coverage.entity_freshness \
  --dsn "$LOCAL_DATALAKE_DSN" \
  --output docs/ops/session-2026-07-18-suite-freshness/
```

| Field | Value |
|-------|-------|
| exit (measure) | **0** |
| exit (`--gate --min-pct 95`) | **2** (fail-closed; pct below threshold) |
| denominator | **1093** (active `raio_200km`) |
| numerator | **0** |
| pct | **0.0** |
| sla_hours | **24** |
| measurement_status | **READY** |
| by_status | fresh=0, stale=0, never=1093 |

Artifacts:

- `entity-freshness-report.json`
- `entity-freshness-report.csv`
- `entity-freshness-gaps.csv`

### Claims allowed

- Entity-level freshness is **measurable** against a configured SLA on real PostgreSQL.
- Nominal gap list exists (1093 entities classified `never` when no `entity_coverage.last_seen_at`).
- Gate mode fails closed when pct < min (exit 2).

### Claims forbidden

- Freshness SLA met / operational freshness green
- Coverage operacional ≥95%
- Source-level freshness-gate green (use `scripts.freshness_gate` separately)
- LOCAL_READY / PRE_VPS_FINAL_READY
- Full suite green

## 2. Suite inventory (honest)

### Critical readiness (resilient-smoke subset)

```bash
python3 -m pytest -o addopts='' -q \
  tests/test_local_resilience.py \
  tests/test_resilience_vertical_slice.py \
  tests/test_fetch_result.py \
  tests/test_crawler_pncp.py \
  tests/test_sc_compras_crawler.py \
  tests/test_ciga_dom_publications.py \
  tests/test_dlq.py \
  tests/test_watermark.py \
  -m "not database and not slow" --tb=no
```

| Result | Value |
|--------|-------|
| exit | **0** |
| passed | **197** |
| skipped | **24** (visible; sc_compras API refactor debt) |
| full suite green? | **NO** |

Captured: `01-critical-readiness.txt`, `01-critical-readiness.exit`

### Full collect

```bash
python3 -m pytest -o addopts='' --collect-only -q tests/
```

| Result | Value |
|--------|-------|
| exit | **0** |
| tests collected | **2174** |
| full run green on every PR? | **NOT claimed** (CI test-all remains workflow_dispatch debt; see prior full-suite-debt pack) |

Captured: `collect.txt`

## 3. Unit tests (slice)

```bash
python3 -m pytest tests/test_entity_freshness.py -o addopts='' -q --tb=line
```

| Result | Value |
|--------|-------|
| exit | **0** |
| passed | **6** |

## 4. Seed prerequisite (session only)

Universe was empty on clean container; seed executed for measurement:

```bash
python3 db/seed/seed_sc_entities.py
# → 2085 entities; 1093 within 200km
```

## 5. Relation to prior debt pack

Prior: `docs/ops/session-2026-07-17-full-suite-debt/` — critical green + honest skips.  
This session **refreshes** critical counts and **adds** entity-level freshness capability. Does **not** close full-suite green.
