# Independent adversarial review — O golden path gera relatório de contratos

| Field | Value |
|-------|-------|
| **Item** | `DOD-rol-1-definition-of-done-f8f4f1b0a9` |
| **Requirement (DOD.md L909)** | O golden path gera relatório de contratos. |
| **Reviewer** | adversarial-qa-continue-03 (read-only) |
| **Reviewed at (UTC)** | 2026-07-22T00:20:00Z |
| **Branch workspace** | `/mnt/d/extra-consultoria-continue-03` (`campaign/continue-03-report-contratos`) |
| **Local sample artifact** | `output/reports/relatorio-contratos-20260722T001319Z.{csv,json}` (git_sha `5fa09f7`, 1 ente + 1 fornecedor) |
| **Verdict** | **CONCERNS** |

---

## Requirement literal

**DOD.md §12.1 L909 (unchecked):**

> O golden path gera relatório de contratos.

**Registered AC** (`.dod/evidence/DOD-rol-1-definition-of-done-f8f4f1b0a9/acceptance_criteria.md`):

- Given DSN with `pncp_supplier_contracts` **or honest empty with limitations**
- When golden_path runs contratos report (`--execute-contratos-report-only` or full path)
- Then report under `output/reports/` (or documented path)
- File not empty: size ≥ 50; **header-only OK with limitations**
- Columns at least: `ente_id`, `n_contratos`, `valor_total`
- Distinct from generic panorama Excel/PDF **and from editais report**
- Metadata: generation timestamp, code version (`git_sha`), limitations
- Specific automated test; no 95% / LOCAL_READY claim

**OUT of scope (AC):** live PNCP crawl; editais/concorrentes/valores; LOCAL_READY / 95%.

---

## What was checked (read-only)

| Surface | Path / ref | Finding |
|---------|------------|---------|
| Domain report module | `scripts/reports/contratos_report.py` | CSV `relatorio-contratos-*.csv` + `relatorio-contratos-fornecedor-*.csv` + JSON sidecar; `report_type=contratos`; aggregates from `pncp_supplier_contracts` via operational helpers |
| Operational queries | `scripts/reports/operational_reports.py::report_contratos_por_ente/fornecedor` | GROUP BY ente/fornecedor; `WHERE is_active IS TRUE`; LIMIT 500; missing table → `[]` |
| Golden path step | `scripts/golden_path.py::run_contratos_report` | Wires writer; requires `ok`, file exists, name contains `relatorio-contratos`, columns `ente_id`/`n_contratos`/`valor_total` |
| CLI only mode | `--execute-contratos-report-only` | Early path after `check_db`; ledger step `contratos_report`; exit 0/1 |
| Full path step 4c | after panorama + 4b editais | Always runs (**not** gated by `--skip-reports`); fail forces `exit_code=4` if otherwise 0 |
| Exit messaging | `messages[4]` | Mentions domain editais/contratos (improved vs early editais wording) |
| Summary panel | full-path resume | Still lists Excel/PDF only — **not** contratos/editais status |
| Tests | `tests/test_golden_path_contratos_report.py` | help flag; write path; CLI ledger path (`@pytest.mark.real_db`) |
| AC pack | evidence dir | Only README + AC (+ this review). No `proof.json` / pytest log / ledger committed |
| DOD.md L909 | unchecked | Correct — not falsely marked done |
| Sibling L908 editais | checked | Separate module/filenames; no confusion |
| Sibling L910–911 | open | Implementation does **not** claim concorrentes/valores |
| Sibling Excel L912 | checked with disclaimer | Explicitly **does not** prove domain contratos |
| Local artifacts | `output/reports/relatorio-contratos-20260722T001319Z.*` | Real domain CSV with synthetic seed row; sidecar honest limitations + `claims_forbidden` |
| CI critical job | `.github/workflows/ci.yml` “Test (critical readiness)” | Does **not** list `test_golden_path_contratos_report.py` |
| CI full suite | `test-all` + `REQUIRE_REAL_DB=1` | Would collect module if present in tree |
| Pytest this session | optional | **Not re-executed here** (no shell in this harness). Judgment from static review + local artifacts. Reproof with `REQUIRE_REAL_DB=1` remains required for ACCEPTED |

---

## Attempts to falsify

| Attack | Result | Severity |
|--------|--------|----------|
| **Is it just panorama Excel/PDF renamed?** | **No.** Separate module, `report_type=contratos`, filename `relatorio-contratos-*`, columns ente/n_contratos/valor_total from `pncp_supplier_contracts`. Panorama remains `panorama-*` Excel/PDF. | Pass |
| **Is it the editais report renamed?** | **No.** Different table (`pncp_supplier_contracts` vs `pncp_raw_bids`), different columns, different CLI flag/step (`contratos_report` vs `editais_report`), different stamp prefix. | Pass |
| **Is it only §12.2 operational_reports filenames?** | **No rebrand alone.** Writer produces golden-path domain files `relatorio-contratos-{stamp}.csv` (+ fornecedor + JSON). It **reuses** query helpers from `operational_reports` (reasonable REUSE), but golden-path identity is distinct from static `relatorio_contratos_por_ente.csv` names. | Pass (with coupling note) |
| **Empty / header-only counted as success?** | **Yes by design.** `ok = (not hard_fail) and size >= 50`. Header-only ~58 bytes passes size. AC explicitly allows header-only with limitations. Zero-row path appends “zero active contracts…”. **Not pure false green vs AC.** | Acceptable per AC |
| **DB connect failure still “pass”?** | **Mostly no.** `db_connect_failed:` is hard-fail prefix → `ok=False`. CLI-only also fails closed on `check_db`. | Pass |
| **Query / missing-table soft-pass?** | **Yes — residual.** `report_contratos_por_*` returns `[]` when table missing **or** when `_q` returns `_error` (error swallowed to empty). `fetch_contratos` then labels this as **zero active contracts**, not `query_failed:` / table missing. Dead-code branch checks `_error` on rows that never contain `_error`. **Missing schema or SQL failure can soft-pass as honest empty.** Editais path hard-fails `table pncp_raw_bids missing`; contratos does **not** mirror that. | **CONCERNS** (high within residual) |
| **Soft assertions in tests** | Write test asserts columns + size≥50 + `ok` but **does not** assert `row_count >= 1` or any data row (unlike editais sibling which asserts both). Seed is best-effort; silent seed failure still greens on header-only. CLI test asserts path/status/ok/size, **not** non-empty data. | CONCERNS |
| **`is_active IS TRUE` vs COALESCE** | Queries exclude `is_active IS NULL`. Test seed count uses `COALESCE(is_active,true)`. Can report empty while rows with NULL flag exist — honest empty, not coverage claim, but brittle. | Low |
| **Skip paths hide step?** | Step 4c is **outside** `--skip-reports`. Mandatory fail-closed when other gates green (`exit_code=4`). | Pass |
| **Mocks replace domain report?** | No mock of writer in golden path. Tests need real DB under `REQUIRE_REAL_DB=1`; otherwise skip after connect probe. | Pass (if suite uses env correctly) |
| **Exit code honesty** | Domain fail remaps to exit 4 when previous exit was 0. Message now covers domain reports. If earlier gate already non-zero, contratos fail does not further remap (ledger still records step). Summary omits contratos line. | Low / CONCERNS (ops UX) |
| **Critical CI alone proves item?** | Critical pytest list does **not** include this module. Claiming green from critical job alone = **false confidence**. | CONCERNS for ACCEPTED |
| **Evidence pack already ACCEPTED-grade?** | Pack has AC + README only (plus this review). No `proof.json`, pytest transcript, ledger, committed sample, CI run id. | Not ready for ACCEPTED |
| **Claims 95% / LOCAL_READY?** | Sidecar `claims_forbidden` + limitations; test asserts `LOCAL_READY` in forbidden. Local sample does not claim coverage. | Pass |
| **Confusion with Excel item (d5c6584cb7)?** | Excel evidence explicitly excludes domain contratos. Separate unchecked L909. | Pass |
| **Confusion with Deliverable C / expiring contracts?** | Different scripts (`deliverable_c_expiring.py` etc.). This item is golden-path domain report generation only. | Pass |

---

## Requirement vs implementation (mapping)

| AC element | Implementation | Met? |
|------------|----------------|------|
| Golden path generates contratos report | Step 4c + `--execute-contratos-report-only` → `write_contratos_report` | Yes |
| Path under output/reports | Default `output/reports/relatorio-contratos-{stamp}.csv` (+ fornecedor) | Yes |
| Not empty / honest empty | Header always written; limitations on zero | Mostly yes (error/table-missing mislabeled as zero — concern) |
| Domain columns | `ente_id`, `n_contratos`, `valor_total` (+ `ente_nome`, `valor_semantica`) | Yes |
| ≠ panorama | Separate type/name/path | Yes |
| ≠ editais | Separate module/table/columns/CLI | Yes |
| Metadata as_of, git_sha, limitations | JSON sidecar | Yes |
| Automated test | `tests/test_golden_path_contratos_report.py` | Yes (weaker than editais: no row_count≥1) |
| No 95%/LOCAL_READY | `claims_forbidden` + limitations | Yes |

---

## Residual risks

1. **Soft-pass on data-path failure via operational helpers:** missing `pncp_supplier_contracts` or SQL error inside `_q` becomes empty list → limitation “zero active contracts” → `ok=True` if header size ≥50 → step `pass`. Prefer: hard-fail (or explicit non-ok) for table missing / query_failed; stop swallowing `_error` in `report_contratos_por_*` **or** re-check table/query in `fetch_contratos` like editais.
2. **Tests under-assert data presence:** no `row_count >= 1` / non-empty CSV body; CLI does not require rows.
3. **Summary panel** still Excel/PDF-centric; contratos status only in steps/ledger.
4. **CI surface:** critical job does not pin this test; ACCEPTED needs full-suite or explicit job + logged pass with `REQUIRE_REAL_DB=1`.
5. **Evidence pack incomplete** for campaign acceptance (no proof/ledger/pytest/CI artifacts committed in pack).
6. **Coupling:** domain §12.1 writer depends on §12.2 operational query semantics (`is_active IS TRUE`, LIMIT 500, silent empty on error) — residual honesty risk.
7. **Not ACCEPTED yet by design:** DOD.md L909 still `[ ]`; manifest `IN_PROGRESS`.

---

## Merge readiness (implementation)

| Question | Answer |
|----------|--------|
| Ready to **merge implementation** PR (code + tests)? | **Yes, with CONCERNS** — domain-specific contratos report is real, wired into golden path, distinct from panorama and editais, fail-closed when artifact missing/misnamed or connect hard-fails, not a rebrand of Excel/PDF. Soft-pass on missing table/query swallow and weak row asserts are non-blocking for first merge if tracked. |
| Ready for **DOD ACCEPTED**? | **No.** |

### Still needed for ACCEPTED

1. Merge to main (or equivalent) and record PR + CI run id (full suite or explicit `test_golden_path_contratos_report` with `REQUIRE_REAL_DB=1`).
2. Reproof on clean/main HEAD:  
   `python3 -m scripts.golden_path --execute-contratos-report-only --dsn … --ledger-output …`  
   + `REQUIRE_REAL_DB=1 pytest tests/test_golden_path_contratos_report.py -q -o addopts=`.
3. Evidence pack: ledger JSON, sample CSV/JSON (or sha256), pytest transcript, `proof.json`, link to commit SHA of generation.
4. Independent review file retained (this document).
5. Prefer hardening before accept (recommended):  
   - hard-fail when table missing / query fails (mirror editais);  
   - stop converting `_error` to empty in the path used by golden path;  
   - strengthen tests: `row_count_ente + row_count_fornecedor >= 1` (or at least one data row after seed);  
   - show contratos (and editais) status in full-path summary.
6. Only then mark DOD.md L909 and promote manifest state — without inventing LOCAL_READY / 95%.

---

## Decision

**CONCERNS** — The claim *“O golden path gera relatório de contratos”* is **substantially implemented** as a **domain-specific** CSV+JSON report of stored contracts (aggregated by ente/fornecedor), **not** panorama Excel/PDF and **not** the editais report, with metadata honesty, forbidden-claims, and a real golden-path step (4c) + CLI-only mode.

It is **not** a clean **PASS** for accept because:

- soft-pass path when table is missing or query errors are swallowed by `operational_reports`;
- automated tests do not require non-empty data rows (weaker than editais sibling);
- critical CI does not pin the test;
- evidence pack is incomplete for ACCEPTED.

**Not FAIL:** falsification attempts did not show that the report is a fake panorama/editais alias, empty-byte success without documentation, mock-only green under proper `REQUIRE_REAL_DB` usage, or a false 95%/LOCAL_READY claim. Local artifact shows a domain file with real contract-shaped columns and one seeded aggregate row.

**Recommendation:** merge implementation OK; **do not ACCEPTED** until reproof + evidence pack + preferably soft-pass hardening (table/query fail-closed + stronger tests).

---

## Scope of this review

- Read-only on production code (`scripts/`, `tests/`, `DOD.md`, `.dod/manifest.yaml`, `.dod/state.json` **not** modified).
- Only written artifact: this file under `.dod/evidence/DOD-rol-1-definition-of-done-f8f4f1b0a9/`.

---
## Post-merge reproof (main 8c794ff00d14fde0e7a2757006074352e78c279a)
- Pytest 3 passed REQUIRE_REAL_DB=1
- CLI --execute-contratos-report-only pass
- Soft-pass table missing fixed
- Verdict ACCEPTED: **PASS_FOR_ACCEPT**
- Date: 2026-07-22T00:25:18Z
