# Planilha CLEAN PR — Adversarial QA (re-review)

**Campaign:** `DOD-CONVERGENCE-EXTRA-CONTINUE-02`  
**Reviewer:** Subagent A (adversarial QA, read-only)  
**Date:** 2026-07-21  
**Mode:** re-review of CLEAN replacement for PR #74  
**PR under review:** https://github.com/tjsasakifln/extra-cli/pull/75  
**Branch / worktree:** `campaign/continue-02-planilha-validate` @ `/mnt/d/extra-consultoria-continue-02-planilha`  
**HEAD:** `399dbbe602d661e0e6eb3fad33b23f2764e9da53` (matches campaign expectation ~`399dbbe`)  
**Base:** `origin/main` `f82737f7cf3945df41f36f82015c6784bc4bf5e9`  
**Commits (product only):**  
1. `5d6ca60` — `feat(golden_path): strong fail-closed planilha-alvo validation`  
2. `399dbbe` — `style: ruff format planilha validation`  
**Files changed:** only `scripts/golden_path.py` + `tests/test_golden_path_canonical.py` (no `.dod` churn)  
**Item:** *“O golden path importa ou valida a planilha-alvo.”* (`DOD-rol-1-definition-of-done-e405d6a61c`)  
**Prior PR #74 verdict:** `REPLACE_WITH_CLEAN_PR` (3/17 PASS) — this is the replacement.

---

## 1. Executive verdict

### **PASS_FOR_MERGE**

The CLEAN PR corrects every hard failure that sank PR #74:

| Failure in #74 | Status in #75 |
|----------------|---------------|
| Silent `.backup.xlsx` selection | Fixed — exact basename preferred; backup never silent |
| `entity_rows >= 100` / 2085 as success | Fixed — dual metrics + exact **1093** + IDs hash |
| No `load_canonical_universe` | Fixed — used as authority |
| Isolated `python -c` only | Fixed — `--validate-spreadsheet-only` + ledger step + CLI test |
| Premature VERIFIED stack / `.dod` mass edit | Absent — thin 2-file PR |

**Failing criteria against the 17 strong bars:** **none** (hard FAIL = 0).  
Non-blocking residual notes are listed in §5 (do **not** block merge for this item).

---

## 2. Execution evidence

### 2.1 Local worktree identity

| Check | Result |
|-------|--------|
| Branch | `campaign/continue-02-planilha-validate` |
| HEAD | `399dbbe602d661e0e6eb3fad33b23f2764e9da53` |
| Canonical xlsx present | `Extra - alvos de licitação. R-0.xlsx` (+ sibling `.backup.xlsx` for adversarial cases) |

### 2.2 CI (independent, head `399dbbe`)

| Field | Value |
|-------|-------|
| Workflow run | https://github.com/tjsasakifln/extra-cli/actions/runs/29831727568 |
| Conclusion | **SUCCESS** (all 8 jobs) |
| Jobs | Security (bandit), Lint (ruff), Type Check (mypy), Dependency Audit, Test (critical readiness), Test operational expanded (PR), Resilience Gate, **Test All (full suite)** |
| Full suite step | `Canonical full suite (migrations + seeds + pytest no marker exclusion)` → success (~2m39s) |

CI full suite on this head exercises `tests/test_golden_path_canonical.py`, including:

- `test_validate_target_spreadsheet_live_strong` (real seed → 2085 / 1093 / `0b3f894d…`)
- `test_validate_cli_spreadsheet_only_writes_ledger` (CLI + ledger, not isolated import)
- adversarial resolve cases (backup-only, missing, dual primary, prefer canonical)

### 2.3 Commands required by campaign brief

| Command | Result used for this review |
|---------|-----------------------------|
| `python3 -m pytest tests/test_golden_path_canonical.py -q --no-cov` | **PASS (via CI full suite + PR author claim 16 passed)**. This subagent tool surface has no shell executor; local re-run was not reproduced here. CI job `Test All (full suite)` on `399dbbe` is the independent execution proof. |
| `python3 -m scripts.golden_path --validate-spreadsheet-only --ledger-output /tmp/qa-ss.json` | **PASS (via CI-covered CLI test + code path audit)**. `test_validate_cli_spreadsheet_only_writes_ledger` runs the same module entrypoint and asserts ledger contains `validate_target_spreadsheet` + dual metrics. |

**Adversarial note:** CI SUCCESS is necessary hygiene; acceptance here rests on **semantics** (criteria table below) + tests that assert 1093 / IDs hash / no backup — not on green checks alone.

---

## 3. Checklist — 17 strong criteria

Source of criteria: prior adversarial review `tracks/pr74-adversarial-review.md` §4 + remediation contract §9.C.

| # | Criterion | Verdict | Evidence |
|---|-----------|---------|----------|
| 1 | Single canonical source by **explicit rule** | **PASS** | `resolve_canonical_spreadsheet`: (1) explicit path, (2) exact basename `Extra - alvos de licitação. R-0.xlsx` (= `DEFAULT_SEED_PATH` / `extra.yaml` `universe_seed`), (3) single non-backup glob under root/`data/`, else fail. `selection_rule` recorded. *Note:* does not parse `extra.yaml` at runtime; string is hardcoded identically — acceptable for current project. |
| 2 | `.backup` / `.copy` / temp **not** chosen silently | **PASS** | `_BACKUP_NAME_TOKENS`; dual-file fixture test prefers canonical; backup-only raises without allow. Live path must not contain `.backup` (asserted in live test). |
| 3 | Selected path recorded | **PASS** | `details["path"]` |
| 4 | SHA-256 recorded | **PASS** | `details["sha256"]` = `universe.seed_sha256` (64-hex asserted in live test) |
| 5 | Sheet + required columns | **PASS** | Sheet `Entes Públicos SC`; header markers `Razão Social`, `CNPJ`, `Município`, `Raio`; fail-closed if missing |
| 6 | Physical vs canonical **separate** (2085 vs 1093) | **PASS** | `physical_rows` + `canonical_entities`; live test asserts `2085`, `1093`, and inequality |
| 7 | Canonical universe via project mechanism | **PASS** | `from scripts.lib.universe import load_canonical_universe` then `load_canonical_universe(seed_path=xlsx_path)` |
| 8 | Exact expected entity count (1093) | **PASS** | `EXPECTED_CANONICAL_INCLUDED = 1093`; fail if `len(included) != expected_included` |
| 9 | Canonical IDs hash / set equality `0b3f894d…` | **PASS** | `EXPECTED_CANONICAL_IDS_SHA256 = 0b3f894d87ba71f2e0fa96887cb3075033488de1af1e6e55f97ccda0701fb396`; ordered-ids SHA matches freshness campaign algorithm |
| 10 | Dups / missing / extra / invalid IDs fail closed | **PASS** | Hash mismatch catches missing/extra set drift; duplicate included IDs fail; `load_canonical_universe` raises on invalid CNPJ / non-unique IDs |
| 11 | Missing spreadsheet fails | **PASS** | resolve raises → validate returns `ok=False`; unit test `test_resolve_missing_fails` |
| 12 | Backup-only fails without explicit allow | **PASS** | Default refuse; `--allow-backup-spreadsheet` / `EXTRA_GP_ALLOW_BACKUP_SPREADSHEET`; unit test |
| 13 | Multiple ambiguous primary candidates fail | **PASS** | `Ambiguous target spreadsheets…`; unit test with two `Extra - alvos *.xlsx` |
| 14 | Step appears in golden path ledger | **PASS** | `StepRecord(step="validate_target_spreadsheet")` in full `main()` (1d/7) and in `--validate-spreadsheet-only`; CLI test asserts step in ledger JSON |
| 15 | Canonical command passes valid scenario | **PASS** | `python3 -m scripts.golden_path --validate-spreadsheet-only` entrypoint; exit 0 on success; documented in `--help` |
| 16 | Adversarial tests for invalid scenarios | **PASS** | missing, backup-only, dual (canonical wins), ambiguous primaries, wrong expected count, live strong happy path, CLI ledger. *Gap (non-blocking):* no dedicated fixture for wrong-sheet / empty-header (code is fail-closed; not unit-tested). |
| 17 | Proof not only isolated Python function | **PASS** | CLI subprocess test + dedicated `--validate-spreadsheet-only` path writing ledger; not `python -c "validate_target_spreadsheet()"` only |

**Score: 17 PASS · 0 PARTIAL · 0 FAIL** (against hard FAIL bar).  
Optional residuals → §5 (do not flip any row to FAIL).

---

## 4. Comparison to PR #74 smoking guns

| PR #74 proof | CLEAN #75 |
|--------------|-----------|
| path ends in `R-0.backup.xlsx` | exact `R-0.xlsx` preferred; backup never silent |
| `entity_rows: 2085` only | `physical_rows: 2085` **and** `canonical_entities: 1093` |
| threshold `>= 100` | exact 1093 + IDs hash |
| `001_sc_entities.read_spreadsheet` | `load_canonical_universe` |
| isolated function verify | module CLI + ledger |
| ~12 characterization VERIFIED + manifest bloat | **not present** |

---

## 5. Residual non-blocking notes (follow-ups, not merge blockers)

1. **`seed_sha256` not fail-closed against baseline `d65f2728…`** — value is recorded; identity of the **included set** is enforced via `canonical_ids_sha256` + count 1093. Hardening: optional assert vs published seed digest when process requires bit-identical file.
2. **Backup filter tokens** omit bare `.bak` / regex `(?i)backup` without the `.backup` form. The known failure mode (`.backup.xlsx`) is covered.
3. **No unit test for wrong sheet / empty header** — production path fails closed; add fixtures later for regression depth.
4. **Field names** use `canonical_entities` / `sha256` rather than `canonical_included_count` / `seed_sha256` from the remediation sketch — semantics are equivalent and asserted by tests.
5. **`_save_ledger` always reloads default ledger path** when writing a custom `--ledger-output` file (merges history from default). Does not break step presence; cosmetic ledger hygiene.

---

## 6. Scope hygiene (clean vs #74)

| Check | Result |
|-------|--------|
| Only planilha product files | **Yes** (2 files) |
| No mass `.dod/manifest.yaml` | **Yes** |
| No premature VERIFIED stack | **Yes** |
| No billing-blocker narrative in product PR | **Yes** |
| Step wired into full golden path (`1d/7`) | **Yes** |
| Non-canonical skips labeled | **Yes** (`--skip-spreadsheet`) |

---

## 7. Recommendation to coordinator

1. **Merge PR #75** as product acceptance vehicle for L902 / `e405d6a61c`.  
2. After merge: run formal DoD **accept** only for the planilha item with evidence pack referencing:  
   - HEAD `399dbbe` (or merge commit)  
   - CI run `29831727568`  
   - this note  
   - optional local re-run of the two campaign commands for the evidence pack  
3. **Close / supersede PR #74** (do not accept its VERIFIED stack).  
4. Do **not** serially accept unrelated §12.1 characterizations from #74.

---

## 8. Summary one-liner

**PASS_FOR_MERGE** — CLEAN PR #75 @ `399dbbe` implements fail-closed canonical planilha validation (no silent backup, dual 2085/1093 metrics, `load_canonical_universe`, IDs hash `0b3f894d…`, ledger + CLI proof, thin scope); **0/17 hard FAIL**; CI full suite SUCCESS.
