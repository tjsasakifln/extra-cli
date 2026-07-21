# Extra Consultoria — Spec Kit Constitution

**Authority order:** `DOD.md` > acceptance criteria > reproducible tests/evidence >
accepted ADRs > existing contracts > operational handoffs > issues/PRs > current code.

Code is the current state, not the normative truth. Never weaken a DOD requirement
to match what the system already does.

## Core Principles (NON-NEGOTIABLE)

### I. Merge and CI integrity

- No merge without green canonical CI **and** the specific test for the DOD item under work.
- A `skipped` job is **not** a passed job.
- Absence of execution is **not** evidence of success.
- Do not reduce coverage thresholds, add `skip`/`xfail`, unreal mocks, loose tolerances,
  broad catches, or soft-fail solely to hide defects.
- Do not remove tests without proving the corresponding requirement was removed or replaced.

### II. Architecture impact discipline

- No architecture change outside the declared impact radius without an explicit warning
  and recorded decision.
- Prefer the smallest delta over the current codebase.
- Do not create parallel frameworks when a small fix in the current tree is enough.
- Do not perform broad refactors as a side effect of a narrow DOD item.
- Do not expand the DOD merely to keep generating work.

### III. Definition of ready for each item

Updating `DOD.md`, ADRs, and handoffs is part of Done for every item that changes
behavior, contracts, operations, or acceptance evidence.

### IV. Parallel work safety

- If two subagents collide on the same file, **stop the wave** instead of continuing.
- First wave must be small and manually validated before scaling.
- At most four parallel tracks; exclusive file ownership per track.
- Normative files (DOD, ADRs, handoffs, `.dod/*`) are coordinator-owned only.

### V. Evidence honesty

- Do not confuse registry existence with operational coverage.
- Do not claim recall, coverage, freshness, integrity, or availability without measuring
  the correct denominator.
- Do not fabricate retrospective evidence.
- Live external evidence requires timestamps, origin, identifiers, hashes, and parameters.
- Fixtures may test logic; they do not prove live operation.
- The same agent must not implement **and** be the sole independent acceptance authority.

### VI. State vocabulary (mandatory)

`OPEN` | `IN_PROGRESS` | `IMPLEMENTED` | `VERIFIED` | `ACCEPTED` |
`BLOCKED_HUMAN` | `BLOCKED_CREDENTIAL` | `BLOCKED_EXTERNAL` |
`BLOCKED_INFRA` | `BLOCKED_LIVE` | `DEFERRED_BY_DOD`

Only `ACCEPTED` may mark `[x]` in `DOD.md`. Branch/PR proof tops out at `VERIFIED`.

### VII. Global completion claims

Do not declare `PROJECT_DONE`, `LOCAL_READY`, `VPS_OPERATIONAL`, or equivalent without
every corresponding gate. Prefer precise formulations: campaign complete, item verified,
item accepted, blocked on human action, local phase complete, external deps remain.

## DOD Convergence workflow rules

1. Work **one** final DOD item at a time (max two indispensable prerequisites).
2. Register acceptance criteria before finishing implementation.
3. Prefer critical-path items that unlock many later acceptances; default first candidate
   is **Suíte global completa verde** unless audit shows otherwise.
4. After three converge cycles with no new learning, diagnose instead of repeating.
5. Atomic commits must not mix different final DOD items.
6. Persistent progress lives in `.dod/state.json`, `.dod/manifest.yaml`, `.dod/log.jsonl`,
   and evidence packs under `.dod/evidence/`.

## Governance

- This constitution supersedes agent convenience and session memory.
- Amendments require explicit documentation and must not silently dilute DOD.md.
- Runtime controller: `python3 tools/dod_controller.py`.

**Version**: 1.0.0 | **Ratified**: 2026-07-20 | **Last Amended**: 2026-07-20
