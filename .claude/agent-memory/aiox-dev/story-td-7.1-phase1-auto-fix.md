---
name: story-td-7.1-phase1-auto-fix
description: Story TD-7.1 Phase 1 — ruff auto-fix e format executados: 644 lint fixes, 84 files formatted, 222 erros restantes
metadata:
  type: project
---

Phase 1 of Story TD-7.1 (Code Quality Cleanup) completed on 2026-07-11.

**Executed:**
- `ruff check scripts/ --fix` — 644 errors auto-fixed (safe fixes only, no `--unsafe-fixes`)
- `ruff format scripts/` — 84 files reformatted, 12 already correct
- `ruff format --check scripts/` — 96/96 files formatted (zero remaining)

**Results:**
- Lint errors: 932 -> 222 (-710, 76% reduction)
- Unformatted files: 87 -> 0 (100%)
- Tests: 439 passed (zero regressions)
- Coverage: ~5% -> 6% (marginal, within noise)

**Remaining (222 non-auto-fixable):** N806(99), F841(51), E402(27), N999(22), F601(14), E731(4), UP031(2), E741(1), F821(1), UP042(1) — these require Phase 2 (manual fixes).

**Key decisions:**
- No `--unsafe-fixes` used (70 hidden fixes deferred to manual review)
- No `pyproject.toml` changes (scheduled for Phase 2/4)
- No module renames (N999 deferred to Phase 2)
- Story status: Ready -> InProgress

**Story:** `docs/stories/epics/epic-td-002-code-quality/story-TD-7.1-code-quality-cleanup.md`
**Self-critique:** `plan/self-critique-td-7.1-phase1.json`
