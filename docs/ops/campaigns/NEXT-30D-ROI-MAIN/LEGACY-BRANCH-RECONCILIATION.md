# LEGACY BRANCH RECONCILIATION — NEXT-30D-ROI-MAIN

**Generated (UTC):** 2026-07-18T19:57:58Z  
**Main HEAD:** `ce81e50ffbf05dabc7b81b6a9a90b86c5d242801`  
**Epic checkpoint:** `0bd5074`  
**Merge-base:** `fbc586856332db11ecb21ae4524dfdf29dd90857`  
**PR #28:** https://github.com/tjsasakifln/extra-consultoria/pull/28 (OPEN, not merged)

## 1. Metric lineage (why 32.3% → 6.8%)

| Reference | Checked | Total | Acceptance |
|-----------|---------|-------|------------|
| Epic `0bd5074` | **437** | 1354 | **32.3%** |
| Main `ce81e50ffbf0` (pre-reconcile port) | **93** | 1355 | **6.9%** |

**Explanation:** The drop was a **branch/denominator switch**, not destruction of work.  
~**344** checkboxes were `[x]` on epic and still `[ ]` on main.  
That work remains on `epic/advance-30d-local-ready-20260718` / PR #28 (**169** commits, **617** files vs merge-base).

### Metrics the executive panel must show separately

1. **Canonical acceptance on main** — checkboxes `[x]` at `origin/main` HEAD only  
2. **Inherited + validated from prior campaigns** — ported after independent QA (not double-counted as new PERT)  
3. **New items accepted in NEXT-30D-ROI-MAIN** — after campaign baseline freeze  
4. **New PERT advance this campaign** — business-day path only  
5. **Reopened / invalidated by audit** — false green removed  

## 2. Scope of forensic inventory

| Bucket | Count |
|--------|------:|
| Commits on epic not in main | 169 |
| Files changed epic vs merge-base | 617 |
| scripts | 60 |
| tests | 46 |
| db | 1 |
| stories | 120 |
| evidence sessions | 291 |
| squads | 54 |
| other | 43 |

Session dirs on epic: `56` under `docs/ops/session-*`.

## 3. Checkbox matrix summary (epic `[x]` missing on main)

| Classification | Count |
|----------------|------:|
| `REVALIDATE` | 299 |
| `PORT_VALIDATED` | 27 |
| `INVALID_FALSE_GREEN` | 17 |
| `OBSOLETE` | 1 |

**Total epic-checked not on main:** 344

Full matrix: `legacy-branch-reconciliation.json` → `checkbox_matrix`.

## 4. Product file classification (scripts/tests/db)

| Classification | Count |
|----------------|------:|
| `PORT_VALIDATED` | 80 |
| `REVALIDATE` | 25 |
| `ALREADY_REIMPLEMENTED` | 2 |

- **MISSING_ON_MAIN:** 81  
- **IDENTICAL:** 2  
- **DIVERGED:** 24  

## 5. Port priority slices (coherent, not blind cherry-pick)

| Slice | Classification | Rationale |
|-------|----------------|-----------|
| S1 truth/docs/claims | PORT_VALIDATED | Honesty tooling, low live risk |
| S2 ops foundation | REVALIDATE | Re-prove on main PG |
| S3 deliverables A–E | REVALIDATE | Port code + independent QA |
| S4 source registry | REVALIDATE | Critical path LOCAL_READY |
| S5 session evidence | PORT_VALIDATED | Audit trail only |
| S6 DoD flips | REVALIDATE | Only after code+QA |

## 6. Rejected / not to do

| Item | Class | Justification |
|------|-------|---------------|
| Blind cherry-pick of 169 commits | INVALID_FALSE_GREEN | Unverified seals; history noise |
| Treating epic 32.3% as main acceptance | INVALID_FALSE_GREEN | Not on main |
| Merge/checkpoint commits as product | OBSOLETE | Orchestration only |

## 7. Atomic unit closed before pause

Main commit `ce81e50` (pre-recon pause foundation): PNCP multi-day window + migration 055 (drop hard orgao FK) + 1883 live pncp bids.  
**Paused:** new campaign feature cycles until reconciliation ports complete.

## 8. Acceptance counts (before → after this report)

| Stage | Checked on main | Notes |
|-------|----------------:|-------|
| Campaign baseline (fbc5868 era) | 92 | pre NEXT-30D |
| After main-direct + T02–T03 + PNCP atomic | 93 | includes 1 §13.4 flip on main |
| After full port (target) | TBD | = inherited validated + new; **not** forced back to 32.3% |

## 9. Next steps (ordered)

1. Port S1 + S5 (code/tests/evidence) with pytest green  
2. Port S2–S4 in ROI order; independent QA per slice  
3. Flip DoD only with reproducible evidence on main  
4. Freeze **inherited baseline** (post-port)  
5. Recompute campaign **delta** (new only)  
6. Re-rank Extra-ROI and resume cycles  

Machine-readable: `legacy-branch-reconciliation.json`


## 10. Port wave 1 (executed 2026-07-18T20:05:18Z)

**Source:** `0bd5074` → **main** (no PR, main-direct)  
**Pytest:** 184 passed, 1 skipped  
**DoD flips this wave:** 0 (intentional — evidence revalidation pending)

### Ported (code/tests/docs)

- Ops deliverables A–E, package final, honesty scanners, capability/inventory, host/ops monitors  
- Claim language, data reliability, structured logging, manual overrides  
- Coverage contract (indicator catalog), applicability matrix, entity freshness  
- Crawl registry + run_evidence fields required by ported tests  
- Canonical docs: DEVELOPMENT, GLOSSARY, METRIC policy, PRD honesty, AGENTS, campaign-30d operational baseline  

### Not yet ported

- Bulk `docs/ops/session-2026-07-18-*` evidence packs (S5)  
- DoD `[x]` for the ~344 epic-only checkboxes (per-item after independent QA)  
- Diverged pipeline/universe/orchestrator files  
- Epic migration `055_fix_upsert_pncp_raw_bids_ambiguous.sql` (conflicts with main `055_drop_orgao_entity_fk`)

### Acceptance after wave 1

| Metric | Value |
|--------|------:|
| Canonical acceptance on main | **93/1355 (6.9%)** |
| Inherited checkboxes flipped | 0 |
| New campaign DoD flips | 1 (§13.4 earlier) |
| Code capability restored from epic | yes (184 unit tests) |

**Still paused for new PERT cycles until S5 evidence port + selective DoD revalidation.**


## 11. Inherited baseline freeze (2026-07-18T20:11:41Z)

| Metric | Value |
|--------|------:|
| Canonical acceptance on main | **195/1355 (14.4%)** |
| Inherited validated flips (this wave) | **102** |
| New campaign-only flips | 1 (§13.4) |
| Epic historical (reference only) | 437/1354 (32.3%) — not main |

**Policy:** inherited flips are NOT new PERT advance. Campaign EXECUTING resumed after freeze.
