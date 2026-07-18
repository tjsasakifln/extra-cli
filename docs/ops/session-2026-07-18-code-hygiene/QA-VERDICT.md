# QA Verdict — ROI-cand-dyn-slice-e845e4e64aba (DoD §27 code hygiene)

**Date:** 2026-07-18  
**Reviewer:** Quinn (@qa) — independent (not implementer)  
**Story:** `ROI-cand-dyn-slice-e845e4e64aba`  
**Candidate:** `cand-dyn-slice:e845e4e64aba`  
**Risk:** HIGH-RISK  
**Verdict:** **CONCERNS**

---

## Executive decision

| Field | Value |
|-------|-------|
| Gate decision | **CONCERNS** |
| Blocks merge? | No (residual risks documented; no CRITICAL fail on scoped ACs) |
| DoD §27 flip to [x]? | **Not authorized by this verdict alone** for the PARTIAL item; PO may close story with residual debt |
| Forbidden claims | Do **not** claim `LOCAL_READY`, “all TODOs eliminated”, or “comments proven globally consistent” |

---

## Commands re-run by independent QA (2026-07-18)

| Command | Result |
|---------|--------|
| `python3 -m pytest tests/test_code_hygiene_gate.py -q --no-cov -o addopts=` | **3 passed** (exit 0) |
| `python3 -m scripts.ops.code_hygiene_gate --json` | **summary.ok=true** (exit 0) |
| `python3 -m scripts.ops.golden_clean_env --dry-run` | **ok=true**, plan only (exit 0) |
| `python3 -m scripts.ops.golden_clean_env` (no flags) | **REFUSING** without `--confirm-drop` (**exit 3**) |

Evidence artifacts: `gate.json`, `pytest.log`, this file.

---

## Per-item status (DoD §27 scope)

| # | Item | Status | Evidence / notes |
|---|------|--------|------------------|
| 1 | Metric changes require definition update (policy + catalog) | **DONE** | `docs/ops/METRIC-DEFINITION-POLICY.md` present; `METRIC_DEFINITIONS` n=6 all `required_fields_present()`; `validate_indicator_catalog()` → `ok=true`; gate block `metric_definitions.ok=true` |
| 2 | Legacy removal plan exists | **DONE** | `docs/ops/LEGACY-REMOVAL-PLAN.md` with L1–L6, substitute, removal criteria, risk; gate `legacy_removal_plan.ok=true` |
| 3 | Critical TODOs have story/issue (FIXME/XXX/HACK untracked = 0) | **DONE** | Gate: `n_fixme_untracked=0`, `n_todo_like=4`, all tracked (`datalake-step5` / story id). **Falsify zero-TODO claim:** `n_todo_like=4` ⇒ claim “zero TODOs” is **FALSE**; gate correctly lists it under `claims.forbidden` |
| 4 | Comments do not contradict code (heuristic) | **DONE** | Gate heuristic: `n_hits=0`. Explicit limitation: does **not** prove global comment accuracy |
| 5 | Operational scripts support `--dry-run` when applicable | **DONE** | All 8 inventory paths expose argparse `--dry-run` (substring + flag check). **Falsify missing dry-run:** not observed on inventory set. `golden_clean_env --dry-run` functional |
| 6 | Destructive scripts require confirm flag + rollback doc | **DONE** (primary) / residual weakness | **Primary path PASS:** `golden_clean_env` refuses DROP without `--confirm-drop` (exit 3); rollback path documented in gate metadata (`backups/local-proof/*.dump`). **Residual:** gate marks `backup-database.sh` and `local_backup_restore_proof.py` ok via soft/`True`-by-default checks; `local_backup_restore_proof` can `DROP DATABASE` with only `--dsn` (no confirm flag). See Concerns |
| 7 | Logs do not replace error handling (fail-closed) | **PARTIAL** | Gate status `PARTIAL_capability_documented`. Fail-closed scripts exist (`golden_path`, `coverage_gate`, `freshness_gate`, `enforce_aiox_path`) with non-zero exits. Does **not** prove every log path rethrows |

**Counts:** DONE=6 · PARTIAL=1 · FAIL=0

---

## Falsification attempts

| Claim under attack | Result |
|--------------------|--------|
| “Zero TODOs in codebase” | **Falsified** — 4 tracked TODO-like comments under `scripts/` |
| “dry-run missing on operational CLIs” | **Not falsified** for inventory of 8 — all have `--dry-run` |
| “DROP without confirm succeeds” | **Falsified attempt fails** — refuse message + exit 3 |

---

## Concerns (non-blocking)

1. **C1 — Destructive safety gate self-referential (MEDIUM)**  
   In `scripts/ops/code_hygiene_gate.py` → `check_destructive_safety`:  
   - `rollback_documented = bool(item.get("rollback"))` is always true if the constant list has a string (does not verify doc/script body).  
   - Non-`--` `require_flag` values force `has_require_flag=True`.  
   - `local_backup_restore_proof.py` lacks an explicit confirm before DROP.  
   **Recommendation:** require real flag string presence + rollback mention in script or linked doc; add `--confirm-drop` (or equivalent) to restore-proof if it remains in the destructive inventory.

2. **C2 — TODO scan scope (LOW)**  
   Scanner only inspects `scripts/**/*.py` comment lines. Debt outside `scripts/` is invisible to this gate.

3. **C3 — logs_vs_errors PARTIAL (expected)**  
   Acceptable for this slice; do not mark full DoD §27 “logs never replace errors” as closed without deeper audit.

---

## AC traceability

| AC | Result |
|----|--------|
| 1. Each of 7 dod_item_ids proven with evidence or left open | **Met** — 6 DONE + 1 PARTIAL (open residual), none silent-green without note |
| 2. No NOT_APPLICABLE used to hit campaign meta | **Met** — no N/A used |
| 3. Independent QA before [x] flip | **Met** — this review; implementer did not self-approve |

---

## Allowed vs forbidden claims (post-review)

**Allowed (with evidence):**

- Metric definitions complete in `METRIC_DEFINITIONS` + policy doc  
- FIXME/XXX/HACK **untracked** count is zero under `scripts/`  
- Inventory operational CLIs expose `--dry-run`  
- `golden_clean_env` requires `--confirm-drop` for destructive path  
- Legacy removal plan exists  

**Forbidden:**

- `LOCAL_READY` / invented readiness seals  
- “all TODOs eliminated”  
- “comments proven globally consistent”  
- Full green on logs-vs-errors without deeper proof  

---

## Decision

**CONCERNS**

Story may proceed to @po close with residual debt C1–C3 tracked.  
Do **not** flip DoD §27 item “logs do not replace error handling” to complete solely on this evidence (PARTIAL).  
Primary hygiene gate + tests green; adversarial checks on dry-run / confirm-drop / zero-TODO claim behave as required.

**Next:** @po close → @devops publish path (no auto-merge).

---

*Independent QA — Quinn. No application source modified.*
