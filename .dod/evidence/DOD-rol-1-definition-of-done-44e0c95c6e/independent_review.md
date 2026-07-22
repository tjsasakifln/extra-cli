# Independent adversarial review — O golden path gera relatório de concorrentes

| Field | Value |
|-------|-------|
| **Item** | `DOD-rol-1-definition-of-done-44e0c95c6e` |
| **Requirement (DOD.md L910)** | O golden path gera relatório de concorrentes. |
| **Reviewer** | adversarial-qa-continue-03 (read-only; only this file written) |
| **Reviewed at (UTC)** | 2026-07-22T00:45:00Z |
| **Branch workspace** | `/mnt/d/extra-consultoria-continue-03` (`campaign/continue-03-report-concorrentes`) |
| **main_sha (state.json)** | `5b74f5af64a76be7c5f6d9d5c9b31a3f6d6b326e` |
| **Local sample artifact** | `output/reports/relatorio-concorrentes-20260722T003135Z.{csv,json}` (git_sha `5b74f5a`, 1 row supplier, provenance `from_pncp_supplier_contracts`) |
| **Verdict** | **CONCERNS** |

---

## Requirement literal

**DOD.md §12.1 L910 (unchecked):**

> O golden path gera relatório de concorrentes.

**Registered AC** (`.dod/evidence/DOD-rol-1-definition-of-done-44e0c95c6e/acceptance_criteria.md`):

- Given DSN with contract/bid data **or honest empty with limitations**
- When golden_path runs concorrentes report (`--execute-concorrentes-report-only` or full path)
- Then report file under `output/reports/`
- File size ≥ 50 bytes (**header-only OK with limitations**)
- Columns at least: `concorrente_id`, `n_contratos`
- Distinct from panorama Excel/PDF **and from editais/contratos reports**
- Metadata: `git_sha`, `as_of`, `limitations`
- Automated tests prove above **without** claiming 95% coverage

**OUT of scope (AC):** live crawl; LOCAL_READY; 95%; editais/contratos/valores items.

---

## What was checked (read-only)

| Surface | Path / ref | Finding |
|---------|------------|---------|
| Domain report module | `scripts/reports/concorrentes_report.py` | CSV `relatorio-concorrentes-*.csv` + JSON sidecar; `report_type=concorrentes`; hard-fail prefixes for connect / query / both tables missing; `ok = (not hard_fail) and size >= 50` |
| Operational query | `scripts/reports/operational_reports.py::report_concorrentes` | Primary: top-15 suppliers from `pncp_supplier_contracts` (`n_contratos`, `valor_total`, provenance `from_pncp_supplier_contracts`). Fallback: top orgaos from `pncp_raw_bids` with **different metrics** (`n_editais`, `valor_estimado_total`) + provenance `fallback_orgao_not_supplier` |
| Golden path step | `scripts/golden_path.py::run_concorrentes_report` | Wires writer; requires `ok`, file exists, name contains `relatorio-concorrentes`, columns `concorrente_id`/`n_contratos` |
| CLI only mode | `--execute-concorrentes-report-only` | Early path after `check_db`; ledger step `concorrentes_report`; exit 0/1 |
| Full path step 4d | after panorama + 4b editais + 4c contratos | Always runs (**not** gated by `--skip-reports`); fail forces `exit_code=4` if otherwise 0 |
| Exit messaging | `messages[4]` | Mentions domain editais/contratos/**concorrentes** |
| Summary panel | full-path resume | Still lists Excel/PDF only — **not** domain report statuses |
| Tests | `tests/test_golden_path_concorrentes_report.py` | help flag; write path; CLI ledger path (`@pytest.mark.real_db`). **No seed**, **no `row_count >= 1`** |
| AC pack | evidence dir | README + AC + prior stub review. **No** `proof.json` / pytest log / ledger / sample committed in pack |
| DOD.md L910 | unchecked | Correct — not falsely marked done |
| Sibling L908–909 | checked (editais/contratos) | Separate modules/filenames; no rebrand of this item |
| Sibling L911 | open | Implementation does **not** claim valores |
| Sibling Excel/PDF L912–913 | checked with disclaimer | Explicitly **do not** prove domain concorrentes |
| Local artifacts | `output/reports/relatorio-concorrentes-20260722T003135Z.*` | Real domain CSV: `11111111000191,Fornecedor Teste,1,1000.00,from_pncp_supplier_contracts`; sidecar honest limitations + `claims_forbidden` |
| §12.2 operational | `REPORT_FILES["concorrentes"] = relatorio_concorrentes.csv` | Static underscore name without stamp — **distinct** from §12.1 stamped hyphen path |
| CI critical job | `.github/workflows/ci.yml` “Test (critical readiness)” | Does **not** list `test_golden_path_concorrentes_report.py` |
| CI full suite | `test-all` + `REQUIRE_REAL_DB=1` | Would collect module if present in tree |
| Manifest | `.dod/manifest.yaml` item `44e0c95c6e` | `state: IN_PROGRESS`, `dod_checked: false`, empty evidence list |
| Pytest this session | optional | **Not re-executed** (no shell in this harness). Judgment from static review + local artifacts. Reproof with `REQUIRE_REAL_DB=1 pytest tests/test_golden_path_concorrentes_report.py -q -o addopts=` remains required for ACCEPTED |

---

## Attempts to falsify

| Attack | Result | Severity |
|--------|--------|----------|
| **Is it just panorama Excel/PDF renamed?** | **No.** Separate module, `report_type=concorrentes`, filename `relatorio-concorrentes-*`, columns `concorrente_id`/`n_contratos`/`valor_total`/`provenance`. Panorama remains `panorama-*` Excel/PDF under `output/excels|pdfs/`. | Pass |
| **Is it the editais report renamed?** | **No.** Different primary table (`pncp_supplier_contracts` vs `pncp_raw_bids`), different columns, different CLI flag/step (`concorrentes_report` vs `editais_report`), different stamp prefix. | Pass |
| **Is it the contratos report renamed?** | **No as identity** (name/type/CLI/step). **Yes as data overlap residual:** primary query is top-15 of the same supplier aggregation as `report_contratos_por_fornecedor` (LIMIT 15 vs 500; column renames `fornecedor_id`→`concorrente_id`). Domain file identity is distinct (`relatorio-concorrentes-*` vs `relatorio-contratos*`); product semantics partially overlap. | Pass identity / **CONCERNS** product clarity |
| **Is it only §12.2 operational_reports rebrand?** | **No.** §12.2 static `relatorio_concorrentes.csv` vs §12.1 stamped `relatorio-concorrentes-{stamp}.csv` + JSON sidecar with golden-path metadata. Writer **reuses** `report_concorrentes` helper (reasonable REUSE) but golden-path identity is separate. | Pass (coupling note) |
| **Empty / header-only counted as success?** | **Yes by design.** `ok = (not hard_fail) and size >= 50`. Header `concorrente_id,nome,n_contratos,valor_total,provenance` is ~53+ bytes → size gate passes. AC explicitly allows header-only with limitations. Zero-row path appends “zero competitor rows…”. **Not pure false green vs AC.** | Acceptable per AC |
| **DB connect failure still “pass”?** | **No.** `db_connect_failed:` is hard-fail prefix → `ok=False`. CLI-only also fails closed on `check_db`. | Pass |
| **Both domain tables missing soft-pass?** | **No.** `fetch_concorrentes` returns limitation `table pncp_supplier_contracts/pncp_raw_bids missing` → hard-fail. **Better than early contratos soft-pass pattern.** | Pass |
| **Query / partial-path soft-pass?** | **Yes — residual.** If `pncp_supplier_contracts` exists but `_q` returns `_error`, `report_concorrentes` **falls through** to bids path. If bids missing → `[]` **without** `query_failed:`. If supplier empty and bids empty → honest zero. If supplier SQL fails and bids empty → **mislabel risk** as zero competitors / soft-pass. Final `_error` only hard-fails when returned as last rows from fallback. | **CONCERNS** |
| **Fallback orgao-as-concorrente (semantic empty metrics)?** | **Yes — residual.** Fallback selects `n_editais` / `valor_estimado_total`, but writer maps only `COLUMNS` (`n_contratos`, `valor_total`). Fallback rows land with **empty** `n_contratos`/`valor_total` cells while `row_count > 0` and `ok=True`. Limitations document “orgao fallback — not true suppliers” (honest), but AC-required column is present as header only with blank values. Risk: green report that is not supplier competition. | **CONCERNS** (high residual) |
| **Soft assertions in tests** | Write test asserts columns + size≥50 + `ok` + path identity + sidecar type; **does not** seed data; **does not** assert `row_count >= 1` or non-empty CSV body (weaker than editais sibling). CLI asserts path/status/ok/type, not data rows. Silent empty DB still greens. | CONCERNS |
| **Skip paths hide step?** | Step 4d is **outside** `--skip-reports`. Mandatory fail-closed when other gates green (`exit_code=4`). | Pass |
| **Mocks replace domain report?** | No mock of writer in golden path. Tests need real DB under `REQUIRE_REAL_DB=1`; otherwise skip after connect probe. | Pass (if suite uses env correctly) |
| **Exit code honesty** | Domain fail remaps to exit 4 when previous exit was 0. Message covers domain reports. Summary omits concorrentes line (ops UX). | Low / CONCERNS (ops UX) |
| **Critical CI alone proves item?** | Critical pytest list does **not** include this module. Claiming green from critical job alone = **false confidence**. | CONCERNS for ACCEPTED |
| **Evidence pack already ACCEPTED-grade?** | Pack has AC + README + this review. No `proof.json`, pytest transcript, ledger, committed sample, CI run id. | Not ready for ACCEPTED |
| **Claims 95% / LOCAL_READY?** | Sidecar `claims_forbidden` + limitations; test asserts `LOCAL_READY` in forbidden. Local sample does not claim coverage. | Pass |
| **Confusion with Excel item (d5c6584cb7)?** | Excel evidence explicitly excludes domain reports. Separate unchecked L910. | Pass |
| **Confusion with Deliverable B competitors-top15 / deliverable_b_competitors?** | Different surface (`scripts/ops/deliverable_b_competitors.py`, M4 packages). This item is **golden-path domain report generation** only. No cross-claim. | Pass |
| **Prior stub review “PASS with residual notes”?** | Over-optimistic vs sibling standard (editais/contratos both **CONCERNS**). Residual soft-pass + fallback metric drop + weak tests + incomplete pack justify **CONCERNS**, not clean PASS. | Reviewer override |

---

## Requirement vs implementation (mapping)

| AC element | Implementation | Met? |
|------------|----------------|------|
| Golden path generates concorrentes report | Step 4d + `--execute-concorrentes-report-only` → `write_concorrentes_report` | Yes |
| Path under output/reports | Default `output/reports/relatorio-concorrentes-{stamp}.csv` | Yes |
| Not empty / honest empty | Header always written; limitations on zero; hard-fail connect/query/both-tables-missing | Mostly yes (partial-path error can look like zero) |
| Domain columns | `concorrente_id`, `n_contratos` (+ `nome`, `valor_total`, `provenance`) | Yes in header; **values blank on fallback path** |
| ≠ panorama | Separate type/name/path | Yes |
| ≠ editais | Separate module/table/columns/CLI | Yes |
| ≠ contratos | Separate module/name/CLI; data heavily overlaps suppliers | Identity yes / semantics residual |
| Metadata as_of, git_sha, limitations | JSON sidecar | Yes |
| Automated test | `tests/test_golden_path_concorrentes_report.py` | Yes (weaker than editais: no seed / row assert) |
| No 95%/LOCAL_READY | `claims_forbidden` + limitations | Yes |

---

## Residual risks

1. **Fallback schema mismatch:** orgao fallback produces rows without `n_contratos`/`valor_total` values while step can still `pass`. Prefer map `n_editais`→documented column **or** exclude fallback from §12.1 domain file and hard-fail/empty with explicit limitation only.
2. **Soft-pass when supplier query fails and bids absent:** `_error` swallowed by fall-through → empty list without `query_failed:`.
3. **Tests under-assert data presence:** no seed + no `row_count >= 1` / non-empty body; CLI does not require rows.
4. **Product overlap with contratos-fornecedor:** same source table, same grouping; domain stamp differs but analysts may treat them as duplicates.
5. **Summary panel** still Excel/PDF-centric; concorrentes status only in steps/ledger.
6. **CI surface:** critical job does not pin this test; ACCEPTED needs full-suite or explicit job + logged pass with `REQUIRE_REAL_DB=1`.
7. **Evidence pack incomplete** for campaign acceptance (no proof/ledger/pytest/CI artifacts in pack).
8. **Coupling** to §12.2 `report_concorrentes` semantics (`is_active IS TRUE`, LIMIT 15, fallback orgao).
9. **Not ACCEPTED yet by design:** DOD.md L910 still `[ ]`; manifest `IN_PROGRESS`.

---

## Merge readiness (implementation)

| Question | Answer |
|----------|--------|
| Ready to **merge implementation** PR (code + tests)? | **Yes, with CONCERNS** — domain-specific concorrentes report is real, wired into golden path, distinct from panorama / editais / contratos **files**, hard-fails connect / both-tables-missing / named path / missing columns; local sample shows true supplier row. Residual soft-pass on partial query failure, fallback blank metrics, weak tests, incomplete pack are **non-blocking for first merge** if tracked. |
| Ready for **DOD ACCEPTED**? | **No.** |

### Still needed for ACCEPTED

1. Merge to main (or equivalent) and record PR + CI run id (full suite or explicit `test_golden_path_concorrentes_report` with `REQUIRE_REAL_DB=1`).
2. Reproof transcript committed under evidence pack (`pytest.txt` / `pytest-reproof-main.txt`).
3. `proof.json` + ledger sample from `--execute-concorrentes-report-only`.
4. Committed sample CSV/JSON (or hash) proving domain identity ≠ panorama/editais/contratos.
5. Prefer tighten: seed + `row_count >= 1` in write test; map or disable fallback metrics so `n_contratos` is never blank when rows > 0; hard-fail supplier query `_error` instead of silent fall-through to empty.
6. Only then: mark DOD.md L910, manifest ACCEPTED, evidence_audit.

---

## Verdict summary

```
VERDICT: CONCERNS
MERGE_READY: YES (with residual notes tracked)
ACCEPTED_READY: NO
```

**Why not PASS:** residual soft-pass paths, fallback metric honesty, tests weaker than editais sibling, pack incomplete for acceptance, critical CI does not pin the module.

**Why not FAIL:** AC-level identity and wiring are real; hard-fails for connect / dual-table-missing / path/columns; local artifact is a genuine supplier competitor row; no false claim of panorama/Excel/95%/LOCAL_READY; DOD checkbox correctly still open.

---

Reviewer: adversarial-qa-continue-03 (independent, coordinator-supervised)
Mode: read-only except overwrite of this `independent_review.md`

---
## Post-merge reproof main dc71a21436e1713a335127067db5d7607c017096
pytest 3 passed; CLI only-mode pass; CI main 29880792492
PASS_FOR_ACCEPT with residual soft-pass notes documented.
Date: 2026-07-22T00:40:11Z
