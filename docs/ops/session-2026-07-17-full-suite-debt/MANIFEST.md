# Full-suite / schema debt — honest MANIFEST

**Story:** `ROI-cand-full-suite-schema-debt`  
**Cycle:** `cyc-2026-07-17T224949Z`  
**Candidate:** `cand-full-suite-schema-debt` (ranking[0])  
**Branch:** `extra-roi/cand-full-suite-schema-debt`  
**Date:** 2026-07-17  
**Purpose:** Document critical path green vs remaining skips with reasons.  
**Do NOT claim:** full suite green in CI PR path, LOCAL_RESILIENCE_READY, PRE_VPS_FINAL_READY, 95% coverage.

---

## 1. Executive summary

| Path | Status | Notes |
|------|--------|-------|
| Critical readiness (`make resilient-smoke` / listed files, `not database and not slow`) | **GREEN** (exit 0) | Latest refresh: **197 passed, 24 skipped** (skips visible; see §3) |
| Default `make test` (`-m "not slow"`) | Partial / env-dependent | Collect ~1997 tests; full run not asserted as green here |
| Full suite `make test-all` / CI `test-all` job | **NOT on every PR** | CI job gated by `workflow_dispatch` only — intentional debt, not hidden |
| Schema/views integration (`REQUIRE_TEST_DB=1`) | **Debt open** | Migration/view tests skip without isolated PG; not fixed in this slice |

This slice **does not hide** the CI `test-all` skip: the condition remains explicit in `.github/workflows/ci.yml` and is copied in `ci-test-all-snippet.yml`.

---

## 2. Critical path — green evidence

**Command (Makefile `resilient-smoke` equivalent core):**

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
  -m "not database and not slow"
```

**Captured artifacts:**

| File | Content |
|------|---------|
| `01-critical-readiness.txt` | pytest console (197 passed, 24 skipped on refresh) |
| `01-critical-readiness.exit` | `CRITICAL_EXIT=0` |
| `02-critical-skip-reasons.txt` | short test summary of the 24 skips (4 reason groups) |

**Claims allowed from this evidence:**

- Critical resilience/crawler path without DB/slow markers ran and exited 0.
- Skips are visible with pytest reasons (not converted to pass).

**Claims forbidden:**

- "Full suite green"
- "Schema views validated on live PG" (not run with REQUIRE_TEST_DB=1 in this pack)
- "CI Test All runs on every PR"

---

## 3. Skips on critical path (honest, not hidden)

From latest `-rs` run on the resilient-smoke file set (`02-critical-skip-reasons.txt`):

**24 skipped — all in `tests/test_sc_compras_crawler.py` after API refactoring:**

| Count | Reason |
|------:|--------|
| 7 | `_extract_table_rows()` removed in API refactoring |
| 8 | `_extract_detail_fields()` removed in API refactoring |
| 5 | `sc_compras_crawler.diagnostic()` removed in API refactoring |
| 4 | `sc_compras_crawler._check_url()` removed in API refactoring |

**Other known suite debts (not in this critical file set, still open elsewhere):**

- `load_target_universe()` broken — consulting readiness tests skip when that path is collected
- Manifest join test needs active opportunity data in local datalake
- Schema/view migration tests need `REQUIRE_TEST_DB=1`

**Debt follow-up (NOT this cycle):** remove or rewrite obsolete sc_compras tests; fix `load_target_universe()`; provision CI for `test-all`. Re-rank must re-select if ROI elevates.

---

## 4. Full suite / CI Test All — intentional gate, not false green

### 4.1 Makefile

From `makefile-test-targets.txt`:

- `make test` → `pytest -m "not slow"` (default path)
- `make test-all` → `pytest` without slow exclusion (local full suite; may need DB/network)
- `make resilient-smoke` / `resilient-local-cycle` / `resilience-gate` — pre-VPS resilience paths

### 4.2 CI

From `.github/workflows/ci.yml` (snippet in `ci-test-all-snippet.yml`):

```yaml
test-all:
  name: Test All (full suite)
  if: github.event_name == 'workflow_dispatch'
```

**Interpretation for DoD §13:**

- On `push`/`pull_request`, **Test All does not run** — this is **documented debt**, not a silent skip of a required job on PR.
- Job has **no** `continue-on-error: true` and no `|| true` (CI comment line 10 asserts fail-closed policy for jobs that do run).
- Full suite remains runnable via `workflow_dispatch` or local `make test-all`.

**This slice deliberately does NOT remove the `workflow_dispatch` gate** without provisioning CI services for integration/slow/database tests (would be false green or flake).

---

## 5. Collection inventory (marker breakdown)

From `04-marker-breakdown.txt` (collect-only):

| Marker / filter | Collected (approx) |
|-----------------|-------------------|
| default `not slow` | 1997 / 2007 (10 deselected) |
| `slow` only | 10 |
| `database` only | 64 |
| `integration` only | 106 |
| `e2e` only | 1 |
| `smoke` only | 37 |
| total tests (nodeids listed in `03-full-suite-collect.txt` sample) | chaos + integration + monitoring + smoke samples |

**Schema-related debt surface (from collect / integration modules):**

- `tests/integration/test_migration_fresh_install.py` — canonical views, FKs, migrations; needs `REQUIRE_TEST_DB=1` + TEST_DSN
- `tests/integration/test_all_sql_references.py` — static SQL reference audit (can run without DB for code-vs-KNOWN list)
- Views expected include `v_entities_canonical`, `v_open_opportunities_canonical`, `v_contracts_canonical`, etc.

**Not fixed this cycle:** live PG view creation failures. Documented as remaining debt for a future ranking[0] if still highest ROI after re-rank.

---

## 6. Squad smoke

`05-squad-smoke.txt` — `squads/extra-dod-roi/tests/test_squad_smoke.py` exercises parse_dod / score_roi / rank plumbing (partial capture in pack; re-run after test additions).

---

## 7. Acceptance mapping

| AC | Result |
|----|--------|
| AC1 — Critical full-suite path documented green **or** remaining skips justified | **MET** — critical path GREEN (exit 0) + skips listed with reasons + full suite CI gate justified |
| AC2 — No hiding skipped critical tests | **MET** — skips remain SKIPPED with messages; CI test-all condition remains visible |

---

## 8. DoD checkbox authority (post independent QA only)

Evidence steward **may** consider (only after @qa PASS and only if sample evidence matches):

- §13.4 items that map to: critical suite not depending on unstable external without mock/mark; slow markers exist; QA not sole implementer (process).

Evidence steward **must not** mark:

- Full global suite green
- Schema/view integrity on real PG without REQUIRE_TEST_DB run
- Any READY seal (LOCAL_RESILIENCE / PRE_VPS_FINAL)

---

## 9. Artifact index

| Path | Role |
|------|------|
| `MANIFEST.md` | This document |
| `01-critical-readiness.txt` / `.exit` | Critical path run |
| `02-critical-skip-reasons.txt` | Skip honesty |
| `03-full-suite-collect.txt` | Nodeid sample of heavier suite |
| `04-marker-breakdown.txt` | Marker inventory |
| `05-squad-smoke.txt` | Squad smoke console |
| `ci-test-all-snippet.yml` | CI test-all condition copy |
| `makefile-test-targets.txt` | Make test targets copy |
| `pytest.ini.snapshot` | Markers / default addopts |

---

*Generated for ROI-cand-full-suite-schema-debt — implementer evidence; QA must re-verify independently.*
