# Independent adversarial review — O golden path gera relatório de editais

| Field | Value |
|-------|-------|
| **Item** | `DOD-rol-1-definition-of-done-0786ea0c31` |
| **Requirement (DOD.md L908)** | O golden path gera relatório de editais. |
| **Reviewer** | adversarial-qa-continue-03 (read-only) |
| **Reviewed at (UTC)** | 2026-07-21T23:55:00Z |
| **Branch** | `campaign/continue-03-report-editais` |
| **Branch tip** | `b25959e1f5ccad546f865fda48ce9a39abefcda5` |
| **main_sha (base observed)** | `432da028f1fed7d70d9d489e689cf3afa350571d` (main tip at review time; branch forked from post-sanitize HEAD `ff733375…`) |
| **Feature commit** | `b25959e` — `feat(golden-path): domain editais report (CSV+JSON) for DoD §12.1` |
| **Verdict** | **CONCERNS** |

---

## Requirement literal

**DOD.md §12.1 L908 (unchecked):**

> O golden path gera relatório de editais.

**Registered AC** (`.dod/evidence/.../acceptance_criteria.md`):

- Given DSN with `pncp_raw_bids` **or honest empty with limitations**
- When golden_path runs editais report (`--execute-editais-report-only` or full path)
- Then report under `output/reports/` (or documented path)
- File not empty: size ≥100 when rows exist; **or** documented empty + limitations
- Columns at least: `pncp_id`, `objeto_compra`, orgao, `uf`
- Distinct from generic panorama Excel/PDF
- Metadata: timestamp, git_sha, limitations
- Specific automated test; no 95% / LOCAL_READY claim

**OUT of scope (AC):** live PNCP crawl; contratos/concorrentes/valores; LOCAL_READY / 95%.

---

## What was checked (read-only)

| Surface | Path / ref | Finding |
|---------|------------|---------|
| Domain report module | `scripts/reports/editais_report.py` | New; CSV `relatorio-editais-*.csv` + JSON sidecar; `report_type=editais`; queries `pncp_raw_bids` active rows |
| Golden path step | `scripts/golden_path.py::run_editais_report` | Wires writer; checks path identity + required columns; returns StepRecord |
| CLI only mode | `--execute-editais-report-only` | Early path after `check_db`; ledger step `editais_report` |
| Full path step 4b | after panorama `[4/7]` | Always runs (not gated by `--skip-reports`); fail forces `exit_code=4` if otherwise 0 |
| Tests | `tests/test_golden_path_editais_report.py` | help flag; write with seed + column/identity asserts; CLI ledger path |
| AC pack | evidence dir | Only README + AC; no proof.json / pytest log / ledger committed in pack |
| DOD.md L908 | unchecked | Correct — not falsely marked done |
| Sibling items L909–911 | still open | Implementation does **not** claim contratos/concorrentes/valores |
| main vs branch | main `scripts/golden_path.py` has **no** `run_editais_report` / `--execute-editais-report-only` | Feature is PR-branch-only |
| Local artifacts | `output/reports/relatorio-editais-*.{csv,json}` | Exist with `row_count=5`, domain columns, limitations, `claims_forbidden` |
| CI critical job | `.github/workflows/ci.yml` “Test (critical readiness)” | Does **not** list `test_golden_path_editais_report.py` |
| CI full suite | `test-all` + `REQUIRE_REAL_DB=1` | Would pick up test via full suite if module is collected |
| Pytest isolation | `tests/conftest.py` + `@pytest.mark.real_db` | Without `REQUIRE_REAL_DB=1`, real DB is mocked; test self-skips on missing table |

**Pytest in this session:** not re-executed here (no shell in review harness). Judgment is from static review + existing local artifacts. Reproof with `REQUIRE_REAL_DB=1` remains required for ACCEPTED.

---

## Attempts to falsify

| Attack | Result | Severity |
|--------|--------|----------|
| **Is it just panorama Excel/PDF renamed?** | **No.** Separate module/filename `relatorio-editais-*`, `report_type=editais`, columns from `pncp_raw_bids`. Panorama remains `output/excels|pdfs/panorama-*`. AC distinctness holds. | Pass |
| **Empty / header-only counted as success?** | **Partially yes.** `ok = size >= 50` treats header-only as OK. AC explicitly allows “documented empty + limitations”. Zero-row path appends honest limitations. **Not a pure false green vs AC.** | Acceptable per AC |
| **DB connect / query failure still “pass”?** | **Yes residual risk.** `fetch_editais` returns `[]` + limitations on connect/query failure; writer still returns `ok=True` if header size ≥50. `run_editais_report` then **pass**. Mitigated on CLI-only by prior `check_db`, but **missing table / mid-query failure soft-pass**. | CONCERNS |
| **Soft assertions in CLI test** | `details.get("row_count", 0) >= 0` is always true. Strong path is `test_write_editais_report_domain_file` (seeds + `row_count >= 1`). CLI alone could green on empty. | CONCERNS |
| **Threshold mismatch AC size≥100 vs code ≥50** | When rows exist, file is >>100. Header-only CSV is already ~160 bytes (columns long). **Not material fail.** | Low |
| **Column `orgao` vs `orgao_razao_social`** | AC says “orgao”; implementation has `orgao_razao_social` (+ `orgao_cnpj`). Tests require `pncp_id`, `objeto_compra`, `uf` only. Semantic coverage OK; literal name soft. | Low |
| **Skip paths hide step?** | Step 4b is **outside** `--skip-reports`. Mandatory fail-closed when other gates green. | Pass |
| **Mocks replace domain report?** | No mock of writer in golden path. Tests need real DB under `REQUIRE_REAL_DB=1`; otherwise skip after failed table probe. | Pass (if suite uses env correctly) |
| **Exit code honesty** | Editais fail remaps to `exit_code=4`, but message map says *“REPORT FAIL: Excel/PDF obrigatório falhou”* — **misleading** when only editais failed. Summary panel lists Excel/PDF, **not** editais status. | CONCERNS (ops honesty) |
| **Critical CI alone proves item?** | Critical pytest list does not include this module. Full suite likely does. Claiming green from critical job alone would be **false confidence**. | CONCERNS for ACCEPTED |
| **Evidence pack already ACCEPTED-grade?** | Pack has AC + README only. No `proof.json`, pytest transcript, ledger, committed sample, CI run id. | Not ready for ACCEPTED |
| **Claims 95% / LOCAL_READY?** | Sidecar `claims_forbidden` + limitations; test asserts `LOCAL_READY` in forbidden. | Pass |
| **Confusion with snapshot recon (3c)?** | Snapshot is ID set reconciliation; report is domain CSV of stored editais. Separate. | Pass |
| **Confusion with operational_reports §12.2?** | Different module/files (`relatorio_contratos_*` etc.). Editais domain list for §12.1 is this new path. | Pass |

---

## Requirement vs implementation (mapping)

| AC element | Implementation | Met? |
|------------|----------------|------|
| Golden path generates editais report | Step 4b + `--execute-editais-report-only` → `write_editais_report` | Yes |
| Path under output/reports | Default `output/reports/relatorio-editais-{stamp}.csv` | Yes |
| Not empty / honest empty | Header always written; limitations on zero/error | Mostly yes (soft-pass on error is concern) |
| Domain columns | pncp_id, objeto_compra, orgao_*, uf, … | Yes (orgao* naming) |
| ≠ panorama | Separate type/name/path | Yes |
| Metadata as_of, git_sha, limitations | JSON sidecar | Yes |
| Automated test | `tests/test_golden_path_editais_report.py` | Yes (strong write path; weak CLI assert) |
| No 95%/LOCAL_READY | `claims_forbidden` + limitations | Yes |

---

## Residual risks

1. **Soft-pass on data-path failure:** missing table / query failure still yields step `pass` with empty CSV + limitations. Prefer fail (or explicit `status=empty` / non-zero) when limitations start with `db_connect_failed` / `query_failed` / `table … missing`.
2. **CLI test under-asserts** `row_count` (always ≥0).
3. **Operator summary / exit message** still framed as Excel/PDF for code 4.
4. **CI surface:** critical job does not pin this test; ACCEPTED needs full-suite or explicit job + logged pass.
5. **Evidence pack incomplete** for campaign acceptance.
6. **Local artifacts** show `git_sha=ff73337` (pre-feature-commit short SHA) — not a reproof of tip `b25959e`.
7. **Not ACCEPTED yet by design:** DOD.md L908 still `[ ]`; manifest `IN_PROGRESS`.

---

## Merge readiness (implementation)

| Question | Answer |
|----------|--------|
| Ready to **merge implementation** PR (code + tests)? | **Yes, with CONCERNS** — domain-specific editais report is real, wired into golden path, fail-closed when artifact missing/misnamed, not a panorama rebrand. Residual soft-pass / CI / messaging issues are non-blocking for first merge if tracked. |
| Ready for **DOD ACCEPTED**? | **No.** |

### Still needed for ACCEPTED

1. Merge to main (or equivalent) and record PR + CI run id (full suite or explicit `test_golden_path_editais_report` with `REQUIRE_REAL_DB=1`).
2. Reproof on clean/main HEAD:  
   `python3 -m scripts.golden_path --execute-editais-report-only --dsn … --ledger-output …`  
   + `pytest tests/test_golden_path_editais_report.py -q -o addopts=` with `REQUIRE_REAL_DB=1`.
3. Evidence pack: ledger JSON, sample CSV/JSON (or sha256), pytest transcript, `proof.json`, link to commit SHA of generation.
4. Independent review file retained (this document).
5. Prefer hardening before accept (optional but recommended): fail step on `query_failed`/`table missing`; strengthen CLI test `row_count >= 1` or assert non-empty limitations path explicitly; fix exit message for editais; show editais in summary panel.
6. Only then mark DOD.md L908 and promote manifest state — without inventing LOCAL_READY / 95%.

---

## Decision

**CONCERNS** — The claim *“O golden path gera relatório de editais”* is **substantially implemented** as a **domain-specific** CSV+JSON report of stored editais, **not** panorama Excel/PDF, with metadata honesty and a real (seeded) automated test under `REQUIRE_REAL_DB`.

It is **not** a clean **PASS** for accept because: soft-pass on query/table failure, weak CLI assertion, exit/summary messaging still Excel/PDF-centric, critical CI does not pin the test, and the evidence pack is incomplete for ACCEPTED.

**Not FAIL:** falsification attempts did not show that the report is a fake panorama alias, empty-byte success without documentation, or mock-only green under proper `REQUIRE_REAL_DB` usage.

**Recommendation:** merge implementation OK; **do not ACCEPTED** until reproof + evidence pack + preferably soft-pass hardening.

---

## Post-merge reproof (main 818dd41d423bfc6c7a086f38bd7b96e2ced6e4b3)

- Pytest: 3 passed with REQUIRE_REAL_DB=1
- CLI --execute-editais-report-only: exit 0, editais_report=pass, rows>=1
- Soft-pass fixed in f3b7273 (included in squash)
- Verdict for ACCEPTED: **PASS_FOR_ACCEPT** (residual: not listed by name in CI critical subset; covered by full suite + specific pytest reproof)
- Reviewer: adversarial-qa-continue-03 + coordinator consolidation
- Date: 2026-07-22T00:02:43Z
