# Independent Review — NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01 (PR #121 close)

**Reviewer:** Subagent I (INDEPENDENT FINAL REVIEWER; did **not** implement)  
**Date:** 2026-07-22  
**PR:** https://github.com/tjsasakifln/extra-cli/pull/121 (**draft — keep draft; do not merge**)  
**Branch:** `campaign/national-contracts-intelligence-architecture-01`  
**Worktree:** `/mnt/d/extra-consultoria-national-intelligence`  
**Isolated DSN:** `postgresql://test:***@127.0.0.1:5435/extra_national_intelligence_test`  
**Method:** Adversarial re-read of working tree + campaign artifacts; source verification of dual spine, facade, SQL hygiene, N+1 fix, anti-pattern grep; cross-check STATUS/SUMMARY/ADR vs code; pytest evidence from close log + test inventory count.

---

## Verdict

# **CONDITIONAL_PASS**

Prior P0 review defects that blocked confidence (vacuous asserts, missing NV-05, entry-point drift, S608 hygiene, agencies N+1, mock-psycopg2 false path, stale test counts) are **fixed in the current tree**. Isolation + dual non-contamination remain real. Residual class is **integration / production-scale / HC-dependency** — not broken campaign architecture.

**Not PASS (unconditional):** HC 3y incomplete; fixture-scale EXPLAIN only; FR-016 deliverable reuse still debt; soft 5433 CLI warning; optional `map_db` silent skip; git tip may lag uncommitted close-tree fixes; merge not authorized.  
**Not FAIL:** no table clones; dual engine not rewritten for false green; three products + lineage + claim classes; real `compute_dual_coverage` path; facade single-engine; Spec Kit 003 coherent; STATUS claim class matches this verdict.

**Campaign claim (STATUS):** `READY_FOR_INTEGRATION_WITH_CONDITIONS` — **coherent** with **CONDITIONAL_PASS**.

---

## Exact HEAD SHA reviewed

| Item | Value |
|------|--------|
| **Branch ref HEAD** | `8cd569cfb10fd575feeddb17bda2b724f3e27603` |
| **Short** | `8cd569c` |
| **Parent chain (worktree log)** | see below |
| **Review scope** | Working tree at PR #121 close (includes facade, `sql_filters`, NV-05, agencies CTE, STATUS 65, analyze-report) **in addition to** committed tip |

### `git log` (branch tip history, newest first)

From worktree ref log (`…/worktrees/extra-consultoria-national-intelligence/logs/HEAD` + `refs/heads/…`):

```text
8cd569cfb10fd575feeddb17bda2b724f3e27603 docs(evidence): version pytest log and independent review
2488b66ad9189dd23b3fd636e6a709935b25f3e7 chore(intel): ruff cleanups + pytest log evidence
9368cd89ef56bac9bf8382b0a5283cb844c4256e test(coverage): adversarial NV matrix on real dual spine
e8d6bc79d91a92484e337e2e639af58751ffc558 feat(intel): national contracts intelligence architecture (spec 003)
a38981bfa616b8f47363da6ff91b12a28bec218c  (branch base / origin/main family)
```

**Residual note (MEDIUM process):** branch ref still points at `8cd569c` while STATUS/analyze-report describe post-close fixes (facade, sql_filters, NV-05, 65-test claim). Operators must **commit remaining close-tree changes** before any merge narrative so “final HEAD” equals reviewed code. This does **not** reopen code-level FAIL if the working tree matches this review.

---

## Pytest count

### Command (as required)

```bash
export NATIONAL_INTEL_DSN=postgresql://test:test@127.0.0.1:5435/extra_national_intelligence_test
python3 -m pytest tests/national_intel/ tests/test_dual_capability_coverage.py -q --tb=no --no-cov
```

### Recorded result (close session artifact)

Source: `artifacts/campaigns/…/tests/pytest-pr121-close.log`

```text
collected 65 items

tests/national_intel/test_adversarial_nv_matrix.py .................     [ 26%]
tests/national_intel/test_coverage_isolation_national_volume.py .....    [ 33%]
tests/national_intel/test_products_fixture.py .....                      [ 41%]
tests/test_dual_capability_coverage.py ................................. [ 92%]
.....                                                                    [100%]

============================== 65 passed in 7.97s ==============================
```

### Count reconciliation (source inventory)

| Suite | Tests (def test_*) | Notes |
|-------|--------------------|-------|
| `tests/national_intel/` | **27** | 17 adversarial + 5 coverage-isolation + 5 products; log `pytest-national-intel.log` also **27 passed** |
| `tests/test_dual_capability_coverage.py` | **38** | production dual spine unit suite |
| **Total** | **65** | matches close log and STATUS |

**Anti-pattern grep** (`tests/national_intel`): `or True` | `except:\s*pass` | `assert True` → **no matches**.

---

## Findings resolved (prior independent / close checklist)

| Prior finding | Status now | Evidence |
|---------------|------------|----------|
| **`or True` vacuous assert (NV-07)** | **RESOLVED** | `test_NV07_legacy_is_covered_ignored` asserts `r.legacy_metric is None` + covered=0 + limitations mention is_covered/any_row/forbidden — **no** `or True` |
| **Missing NV-05** | **RESOLVED** | `test_NV05_shared_cnpj8_does_not_double_cover_without_evidence` exists; uses `_report` → **`compute_dual_coverage`**; presence alone → `covered_numerator==0` |
| **Old test count (10 / 26 drift)** | **RESOLVED in STATUS** | STATUS documents **65 passed** (27 national_intel + dual suite); close log confirms 65. SUMMARY still says “26+” (mild doc lag, not gate fail) |
| **Ruff S608 f-string SQL** | **RESOLVED / mitigated** | `scripts/national_intel/sql_filters.py` allowlisted fragments + bound `%s`; products use `build_contract_filters`; agencies keeps `# noqa: S608` only on allowlisted concatenation; analyze-report: CI S608/S607 fixed. STATUS claims `ruff check scripts/national_intel … → clean` |
| **Agencies N+1** | **RESOLVED** | `agencies.py` docstring + single CTE (`base` / `supplier_counts` / `top_share` / `ranked`) — **one** `fetch_all` |
| **Entrypoint / FR-010 proliferation** | **RESOLVED (accepted design)** | ADR-entry-point-boundary.md: engine=`national_intel`; facade `contract_intel national-{competitors,benchmarks,agencies}` delegates only — **no second SQL**; verified in `scripts/contract_intel/cli.py` `_cmd_national_facade` |
| **Mock psycopg2 blocks real PG** | **RESOLVED** | `tests/conftest.py` autouse skips mock when path contains `tests/national_intel` **and** `NATIONAL_INTEL_DSN` (or REQUIRE_REAL_DB) set — products/views tests can hit 5435 |
| **Bare `except: pass` hiding dual path** | **MOSTLY RESOLVED** | No bare `except: pass` on primary dual asserts; residual optional `map_db_entities` block still `except Exception: pass` (see open residuals LOW) |
| **False coverage / SC contamination** | **Still held** | No `coverage_pct` / LOCAL_READY / 95% in `scripts/national_intel`; products force `scope_label=intel_product` |
| **Table clones / MV on writer** | **Still held** | 059 = `CREATE OR REPLACE VIEW` only over `pncp_supplier_contracts` |

### NV-05 dual path confirmation (adversarial)

```text
tests/national_intel/test_adversarial_nv_matrix.py
  imports: compute_dual_coverage, load_canonical_universe, …
  _report() → compute_dual_coverage(...)
  test_NV05_shared_cnpj8_does_not_double_cover_without_evidence:
    two entities same cnpj8; presence {root-a, root-b};
    assert covered_numerator == 0; never_checked_count == 2
```

This is **not** a hand-rolled aggregate and **not** a mock dual engine.

---

## Axis re-check (current tree)

| # | Axis | Call | Notes |
|---|------|------|-------|
| 1 | Overengineering / clones | **PASS** | Views only; no fact-table clone |
| 2 | False coverage / SC contamination | **PASS** | Dual real path; presence ≠ coverage |
| 3 | HC conflict (5433 / PID / checkpoints) | **PASS (isolation design)** | 5435 default; conftest refuse 5433; isolation proofs; no HC path writes claimed |
| 4 | Spec Kit 003 | **PASS (with residual debt)** | Entry ADR + facade; FR-016 still doc-only reuse |
| 5 | Real dual spine tests | **PASS** | 27 national_intel + 38 dual suite |
| 6 | Three products reproducible | **PASS (fixture)** | competitors / benchmarks / agencies + examples + fixture tests |
| 7 | EXPLAIN honesty | **PASS (honesty)** | Fixture-scale only; non-claims intact |
| 8 | Integration plan honesty | **PASS** | READY_FOR_INTEGRATION **with conditions**; no execute while HC live |
| 9 | STATUS ↔ review coherence | **PASS** | Both **CONDITIONAL_PASS** / READY_FOR_INTEGRATION_WITH_CONDITIONS |

---

## Open residuals (with severity)

| # | Residual | Severity | Why still open |
|---|----------|----------|----------------|
| 1 | **HC 3y incomplete / writer live** | **HIGH (merge blocker)** | National richness + prod cutover blocked; PID/supervisor may still run on 5433 |
| 2 | **Branch not rebased on post-HC main** | **HIGH (merge blocker)** | Drift vs HC campaign tip; integration plan requires rebase after HC lands |
| 3 | **Fixture ≠ national multi-million EXPLAIN** | **MEDIUM** | `explain-competitors-fixture.txt` is tiny scale; indexes deferred |
| 4 | **FR-016 deliverable reuse debt** | **MEDIUM** | Ranking/percentiles not imported from deliverable_a/b/d — dual truth risk if numbers diverge |
| 5 | **Soft 5433 CLI warning only** | **MEDIUM** | `resolve_dsn` warns, does not hard-refuse product runs on HC port |
| 6 | **Optional map_db `except Exception: pass`** | **LOW** | After pure dual asserts; presence DB path may skip without failing isolation claim |
| 7 | **Git tip vs close working tree** | **MEDIUM (process)** | Ref `8cd569c` may not include all close fixes until committed |
| 8 | **SUMMARY.md “26+” lag** | **LOW** | STATUS correct at 65; SUMMARY not fully reconciled |
| 9 | **P0 matrix not 100% (SZ suite partial in national package)** | **LOW** | SZ-01 smoke + dual suite cover validators; full SZ-02..11 not all re-locked under national_intel only |
| 10 | **CI green after push not proven here** | **MEDIUM** | STATUS targets CI_GREEN after push; pre-close note had Lint FAIL — close claims fixed, not re-audited on remote CI |
| 11 | **No production merge / no DOD / no SC ≥95%** | **NON-CLAIM (must stay)** | Correctly excluded |

### Conditions for future merge (aligned with STATUS)

1. HC campaign finishes and lands on accepted `main`  
2. Rebase/update PR #121 against that `main`  
3. Resolve migration/schema conflicts consciously  
4. Re-apply 059 on staging restore; full suite green  
5. Integration review after HC data available (optional national EXPLAIN at scale)  
6. Commit all close-tree code so reviewed SHA == merge tip  

---

## Ruff (`scripts/national_intel`)

- **STATUS claim:** `ruff check scripts/national_intel scripts/contract_intel/cli.py → clean`  
- **Code review:** dynamic WHERE only via allowlisted constants in `sql_filters.py`; user values bound; agencies `noqa: S608` documented for allowlisted concat; lineage avoids shell git (`git_sha` reads `.git` files).  
- **Independent re-exec:** not re-invoked in this reviewer shell surface; no residual S608 pattern of interpolating user strings into SQL found under `scripts/national_intel/`.

---

## Entry point boundary (confirmed)

| Surface | Role | SQL engine |
|---------|------|------------|
| `python -m scripts.national_intel {competitors,benchmarks,agencies}` | Supported alias | `scripts.national_intel.*` |
| `python -m scripts.contract_intel national-{competitors,benchmarks,agencies}` | Operator facade | **same** via `_cmd_national_facade` |
| Dual coverage | Exclusive | `scripts.coverage.dual_capability_coverage` only |

ADR: `artifacts/.../architecture/ADR-entry-point-boundary.md` (Accepted).

---

## STATUS.md coherence

| Claim | Independent judgment |
|-------|----------------------|
| Final claim `READY_FOR_INTEGRATION_WITH_CONDITIONS` | **OK** — matches CONDITIONAL_PASS |
| Independent review CONDITIONAL_PASS | **OK** — this document |
| Non-claims (no SC 95%, LOCAL_READY, VPS, DOD complete, no merge) | **OK** |
| Tests 65 passed | **OK** vs close log + inventory |
| PR remains draft | **OK** — must stay draft |

---

## Gate mapping (independent)

| Campaign gate | Independent call |
|---------------|------------------|
| PARALLEL_ISOLATION_PASS | **PASS** |
| SPEC_KIT_PASS | **PASS** (FR-016 residual debt noted) |
| BASELINE_INVENTORY_PASS | **PASS** (artifacts present) |
| ARCHITECTURE_DECISION_PASS | **PASS** (layers + entrypoint ADR) |
| ISOLATED_IMPLEMENTATION_PASS | **PASS (fixture/5435)** |
| STRATEGIC_PRODUCTS_PASS | **PASS (fixture only)** |
| SC_COVERAGE_ISOLATION_PASS | **PASS** (real dual; NV-05 present) |
| INDEPENDENT_REVIEW | **CONDITIONAL_PASS** (this document) |
| Production / DOD / ≥95% SC / merge | **NOT CLAIMED — NOT PASS** |

---

## Final one-liner

**CONDITIONAL_PASS on working tree for PR #121 close:** prior adversarial holes (vacuous asserts, missing NV-05, entrypoint, S608 hygiene, N+1, mock PG, test-count drift) are fixed; **65** pytest items green in close evidence; merge and production national claims remain **blocked** on HC completion, rebase, and honest scale proof — **keep PR draft**.
