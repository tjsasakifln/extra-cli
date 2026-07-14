---
name: story-1.3-universe-authority
description: "Story 1.3 implemented: snapshot tables, duplicate loader removed, seed blocking, env configs, TD-005 JSON output, query migration partial"
metadata:
  type: project
---

# Story 1.3 Universe Authority Implementation

**Status:** InReview (2026-07-13)
**Executor:** Dex (Builder) - YOLO mode
**Total estimate:** 20h | **Completion:** 12 tasks (8 DONE, 2 code-ready, 2 partial)

## Delivered

### Infrastructure (6 new files)
- `db/migrations/037_target_universe_snapshot.sql` — target_universe_runs + target_universe_entities with indexes
- `db/migrations/038_target_universe_active_view.sql` — v_target_universe_active + v_target_universe_all views
- `scripts/universe_tools.py` — unified CLI: snapshot generate/list, divergence ledger, check-seed (exit 42)
- `scripts/lib/universe_query.py` — SQL helpers for JOIN with target_universe_entities
- `.env.dev`, `.env.staging`, `.env.production` — environment distinction (TD-034)
- `docs/operations/universe-snapshot-runbook.md` — operational documentation

### Refactored Files (5 modified)
- `scripts/consulting_readiness.py` — removed duplicate `load_target_universe()`; uses `CanonicalUniverse` from `scripts.lib.universe`
- `scripts/intel_pipeline.py` — added `--pipeline-json` flag for structured JSON output with run_id (TD-005)
- `scripts/opportunity_intel/manifest.py` — queries migrated to `target_universe_entities` with `universe_run_id`
- `scripts/opportunity_intel/backfill.py` — entity_coverage query migrated to `target_universe_entities`
- `scripts/reports/panorama.py` — coverage_gaps query migrated to `target_universe_entities`

### Decisions
- **Duplicate root 00394494**: 4 legitimate distinct entities (MJ, DPF, PRF, UniPRF) — no resolution needed; the identity_key chain handles it correctly
- **Raio_200km replacement**: Created v_target_universe_active view + SQL helper; applied to key analytic queries; ~50 files with raio_200km references remain for future waves

## Validation
- `ruff check` passes on all new/modified Python files (pre-existing S110/S101/S608 warnings unchanged)
- All imports verified

## Blockers
- Tasks 5 (snapshot) and 6 (divergence): require migration 037 applied to DB first
- Tasks 7 and 8 (full query migration): partial — 3 key files done, ~50 files remaining (crawl/infra scripts)
