# Harness Hardening Report — DOD-CONVERGENCE-EXTRA-CONTINUE-02

**Track:** harness (Subagent B)  
**Branch:** `campaign/continue-02-harness`  
**Base:** `origin/main` @ `f82737f`  
**Date:** 2026-07-21  
**Scope (exclusive):** `tools/dod_controller.py`, `tests/test_dod_controller.py`,  
`.specify/workflows/dod-convergence/workflow.yml`, `docs/ops/dod-convergence.md`

---

## Executive summary

The DOD convergence harness could report **false green** progress: checkboxes and
directory existence were treated as acceptance, verify accepted no-op commands,
accept gates were incomplete, and the Spec Kit workflow swallowed failures with
`|| true`. This track hardens those paths to **fail-closed** without mass-unchecking
DOD items or declaring VERIFIED/ACCEPTED for product work.

---

## False-green gates found

### FG-1 — Scan auto-ACCEPT from checkbox (CRITICAL)

**Where:** `default_item_dict()` — checked items started as `state=ACCEPTED`.

**Effect:** First `scan` inflated `acceptance_pct` and `metrics.accepted` to match
`[x]` count. A previously checked item was treated as audited/accepted without
evidence location, reproduction, or independent review.

**Fix:** New items always start `OPEN`. `dod_checked` remains a **claim** signal.
Only explicit `accept` (after gates) may set `ACCEPTED`. Category
`ACCEPTED_EXISTING` may still classify checked legacy items for prioritization,
but does **not** imply audited acceptance.

### FG-2 — Metrics conflate claim vs audit (HIGH)

**Where:** `metrics_from_items()` — single `accepted` / `acceptance_pct` based on
manifest state alone (which was auto-set from checkboxes).

**Effect:** Operators and workflow reports looked “done” when only declarations
existed.

**Fix:** Distinct metrics:

| Metric | Meaning |
|--------|---------|
| `claimed_checked` | DOD checkbox `[x]` (`dod_checked`) |
| `audited_accepted` | `state==ACCEPTED` **and** evidence audit not weak |
| `evidence_located` | Path refs exist on disk |
| `evidence_reproduced` | `verify_result.json` with `ok=true` after current gates |
| `proof_debt` | Claimed checked but not audited_accepted, or ACCEPTED with weak evidence |

`acceptance_pct` is redefined over **`audited_accepted / total`** (not claimed).

### FG-3 — Verify accepts trivial / empty runs (CRITICAL)

**Where:** `cmd_verify()` — ran any shell command including `true`; empty
command/test lists only failed without `--mark-if-empty`.

**Effect:** Unit test and workflow could mark `VERIFIED` with zero substantive
proof. Tests encoded `acceptance_commands = ["true"]`.

**Fix:**

- Reject trivial commands (`true`, `:`, bare `echo`, `/bin/true`, `exit 0`, help/version-only).
- Reject empty verify (no non-trivial commands and no tests) — always fail-closed
  (remove success path for empty).
- Require `acceptance_criteria.md` (unchanged default).
- Record per-command: full cmd, exit code, duration_s, env snapshot, stdout/stderr tails;
  for pytest: attempt parse of passed/failed/skipped/deselected counts.
- Reject **stale** prior `verify_result.json` reused for accept unless
  `immutability_justification.md` exists in the pack (checked at accept).

### FG-4 — Accept only checked pack directory (CRITICAL)

**Where:** `cmd_accept()` — gates were: state∈{VERIFIED,ACCEPTED}, branch main
(or bypass), pack **directory** exists.

**Effect:** `ACCEPTED` possible because `start` created an empty evidence dir.
Missing: criteria file, green test, CI status, divergence, independent review,
full-suite when required, mandatory jobs, pending review requests.

**Fix:** Fail-closed gates (each may have an explicit narrow bypass for harness
unit tests only):

1. `state == VERIFIED` (not already ACCEPTED unless re-accept force)
2. Branch is `main`/`master` (or `--allow-non-main`)
3. Commit identified (`git rev-parse HEAD` non-null)
4. Complete pack: `acceptance_criteria.md` + `verify_result.json` with `ok=true`
5. Specific green test: at least one non-trivial command **or** pytest entry with exit 0
6. CI of commit green via `ci_status.json` in pack (`conclusion=success`, `head_sha` match)
   — or `--skip-ci-gate` (logged)
7. Full suite when item text/category implies suite/CI impact — requires
   `full_suite_status.json` with `ok=true` unless `--skip-full-suite-gate`
8. No mandatory job skipped (`ci_status.json.mandatory_jobs_skipped` must be empty/false)
9. No pending requested changes (`review_status.json.pending_changes_requested` false)
10. No DOD/manifest checkbox divergence for this item
11. Independent review artifact: `independent_review.md` with non-empty body
12. `--update-dod` only applied after all gates pass (unchanged order, reinforced)

`--allow-missing-evidence` **no longer** accepts on directory alone; it only skips
the “pack root must exist” pre-check when combined with other harness bypasses for
legacy callers — complete-pack checks remain.

### FG-5 — Workflow fail-open (HIGH)

**Where:** `.specify/workflows/dod-convergence/workflow.yml`

| Pattern | Risk |
|---------|------|
| `audit ... \|\| true` | Audit divergences never fail the run |
| `verify ... \|\| true` | Failed verify continues to “converge” |
| `converge-loop` `condition: "false"` | Loop never runs; dead step |
| `max_items` unused | Cannot batch/advance when one item blocked |
| Only `tests/test_dod_controller.py` | Product regressions invisible in first wave |
| No push/PR/CI/merge/refresh automation | Operators assumed automation that does not exist |

**Fix:**

- Remove all `|| true`; failures interrupt (exit non-zero).
- On verify/audit failure: write structured blocker via `dod_controller block` and
  attempt `next` for another eligible item when `max_items` allows.
- Replace dead converge loop with objective signal file
  `.dod/state.converge_continue` (`true`/`false`) written by converge step docs.
- Persist `next_step` / `resume_step` in state after each phase.
- Document honest non-automation: push/PR/merge remain human/@devops; provide
  shell steps that **check** readiness, not silent success.
- First-wave tests: harness + a small always-safe set; item tests from manifest.

### FG-6 — `next` selection keyword+line only (MEDIUM)

**Where:** `score_item()` / `select_next()`.

**Effect:** No dependency satisfaction, no unlock breadth, weak phase/cost/impact.

**Fix (minimal planner):**

- Skip items whose `dependencies` are not all `ACCEPTED`.
- Prefer items that unlock more dependents (`unlock_count`).
- Prefer current phase-compatible categories from `state.phase`.
- Prefer lower rough cost (fewer registered commands/tests; shorter text).
- Prefer higher expected DOD impact (critical keywords + unlock).
- Still skip blocked / ACCEPTED / orphans.

### FG-7 — Audit does not demote weak ACCEPTED (MEDIUM)

**Where:** `cmd_audit()` reported `accepted_weak_evidence` but left state ACCEPTED.

**Policy this track:** Do **not** mass-uncheck or auto-demote ACCEPTED → OPEN
(coordinator/product authority). Report as **proof debt** in metrics and
divergences. Demotion remains explicit operator action if desired later.

### FG-8 — Tests encoded false-green path (HIGH)

**Where:** `tests/test_dod_controller.py` used `true` + `--allow-missing-evidence`.

**Fix:** Tests assert rejection of trivial verify; accept path builds a complete
minimal evidence pack with non-trivial command (e.g. `python3 -c "import sys; sys.exit(0)"`
is still borderline — prefer a tiny real check like `python3 -c "assert 1+1==2"`)
and required gate files.

---

## Implementation checklist

- [x] Metrics split + proof debt
- [x] Scan no auto-ACCEPT
- [x] Verify trivial/empty/stale hardening + result schema
- [x] Accept complete gates
- [x] Next dependency/unlock/phase/cost
- [x] Workflow fail-closed + max_items + honest push/PR notes
- [x] Docs update
- [x] Tests updated and green

---

## Remaining known gaps (not in this track)

1. **No live GitHub CI client** inside controller — CI gate is file-based
   (`ci_status.json`); operators/scripts must populate it from `gh run`.
2. **No auto-demotion of historical ACCEPTED** rows already in production manifests
   (merge preserves state); audit flags proof debt only.
3. **Dependency graph** is manual (`dependencies: []` in manifest); no NLP edge
   extraction from DOD text.
4. **Independent review agent identity** is not cryptographically verified — presence
   of `independent_review.md` only.
5. **Spec Kit engine** may still interpret gates differently; workflow YAML is
   normative for this project but depends on Spec Kit runtime fidelity.
6. **Push/PR/merge** intentionally not automated (authority: @devops).

---

## How to verify this track

```bash
cd /mnt/d/extra-consultoria-continue-02-harness
python3 -m pytest tests/test_dod_controller.py -q --tb=short
python3 -c "import yaml; yaml.safe_load(open('.specify/workflows/dod-convergence/workflow.yml'))"
```

---

## Commits

| SHA | Message |
|-----|---------|
| `7cc73d04e601b0a9401321a57ccfbab7bc7c6adb` | `fix(harness): fail-closed DOD controller gates (continue-02)` |

Branch: `campaign/continue-02-harness` (based on `origin/main` @ `f82737f`).  
Not pushed (coordinator integrates serially).

## Test evidence

```text
python3 -m pytest tests/test_dod_controller.py -q --tb=short --no-cov
# 16 passed
```
