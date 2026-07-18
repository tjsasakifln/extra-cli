# RECOVERY INVENTORY — NEXT-30D-ROI-MAIN-R2

**UTC:** 2026-07-18T20:34:29Z  
**HEAD:** `dc7cea0efb3f19b36a5133aabb235d89baf09cca`  
**origin/main:** `dc7cea0efb3f19b36a5133aabb235d89baf09cca` (synced=True)  
**Branch:** `main`  
**DoD:** 195/1355 = **14.39%** · sha256 `facf55424bc2fe86…`

## Principle

Recover → reconcile → advance. Prior chat is **not** truth. Only repo, branches, stashes, AIOX state, ledgers, DOD, tests, DB.

## Git snapshot

| Item | Value |
|------|-------|
| Dirty WIP | golden_path, apply_migrations, mig 056, N01–N03 evidence |
| Rescue branch | `rescue/r2-dirty-pre-bootstrap-20260718` @ `dc7cea0efb3f` |
| Epic | `epic/advance-30d-local-ready-20260718` @ `0bd5074a0c4e` |
| Merge-base epic↔main | `fbc586856332` |
| Commits epic not in main | 169 |
| Commits main not in epic | 8 |
| PR #28 | OPEN (not delivery; historical only) |
| Worktrees | 1 (primary) |
| Stashes | 12 |
| extra-roi/cand-* local | 53 |
| Writer lock | force-released (stale delivery-engineer post-inherit) |

## Metric lineage (do not collapse)

| Layer | Checked | Total | % | Notes |
|-------|--------:|------:|--:|-------|
| Epic historical | 437 | 1354 | 32.3 | branch only — **not main** |
| Main R1 baseline | 92 | 1355 | 6.8 | pre-recon |
| Main after inherited port | 195 | 1355 | 14.4 | inherited_validated, not new PERT |
| **Main now (R2 start)** | **195** | **1355** | **14.39** | canonical |

Δ 32.3→6.8 was **branch/denominator switch**, not pure regression.  
Δ 6.8→14.4 was **selective inherited port**, not new critical-path invention.

## Prior campaign (NEXT-30D-ROI-MAIN) — reference only

- Path: `docs/ops/campaigns/NEXT-30D-ROI-MAIN/`
- Increments accepted: T02, T03
- PERT new ~4.5d claimed; scope N01–N17 still mostly PLANNED
- Evidence packs present (T02/T03/T05/S5/N01 partial)
- Status machine: EXECUTING_POST_INHERIT → superseded by R2

## Dirty WIP classification (pre-commit)

| Artifact | Class | Decision |
|----------|-------|----------|
| mig 056 drop supplier FK | REVALIDATE → port if QA | Fix apply max=56, **min stays 1** |
| golden_path pncp timeout 360 | REVALIDATE | Keep if live golden needs it |
| N01–N03 evidence logs | DOCUMENTATION_ONLY until re-run | Keep as evidence; re-prove live |
| apply_migrations min=56 dirty | INVALID (wrong default) | Correct to min=1 |

## Next steps (bootstrap order)

1. ✅ Inventory (this file)
2. Baseline + metric lineage freeze
3. Legacy reconciliation (reference prior + delta since dc7cea0)
4. Commit clean product WIP (056 + apply fix)
5. SmartLic read-only audit
6. PERT recalculate + freeze scope.json ≥30d critical path
7. Continuous Extra-ROI slices on main-direct

## Forbidden

- Blind cherry-pick of 169 epic commits
- Counting inherited as new PERT
- Restoring 32.3% artificially
- PR as delivery / force-push / remote feature branches
