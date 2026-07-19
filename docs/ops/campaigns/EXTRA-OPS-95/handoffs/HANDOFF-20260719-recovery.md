# HANDOFF — EXTRA-OPS-95 recovery after unexpected WSL close

**UTC:** 2026-07-19T recovery session  
**Branch:** `campaign/extra-ops-95-20260719`  
**Status global:** **PARTIAL**

## Recovery facts

- Worktree: `/mnt/d/extra consultoria` (single worktree)
- HEAD pre-recovery-commit: `d022012` (22 commits ahead of `origin/main`, **no upstream**)
- Reflog continuous; no orphan commits requiring rescue branch
- Safety patch + bundle: implementer scratch `recovery/`
- Stashes from other branches left untouched

## Honest metrics (STATUS + session-metrics)

| Metric | Value | Meta |
|--------|------:|-----:|
| DOD | ~313/1352 (**~23.15%**) | ≥55% |
| Editais presence | 299/1093 (**27.36%**) | ≥95% presence/ops |
| Contracts presence | 371/1093 (**33.94%**) | — |
| Contracts SZ | 722 | — |
| **Contracts ops proxy** | **1093/1093 (100%)** | ≥95% **ATINGIDO** (proxy only) |
| N09 gold/recall | **BLOCKED_SOURCE** | open |

## Fronts

| Front | Class |
|-------|-------|
| M0 baseline / OSS matrix | DONE |
| M1 universe 1093 | DONE |
| Contracts ops proxy ≥95% | DONE (proxy def) |
| Editais presence/ops | PARTIAL (~27%) |
| DOD 55% | PARTIAL (~23%) |
| N09 recall | BLOCKED |
| §25 PARTIAL/BLOCKED semantics | IN_PROGRESS (this recovery) |
| Campaign DONE / LOCAL_READY | NOT_READY |

## Ops proxy definition (not 7-stage)

```
ops_proxy = lake presence(orgao_cnpj8) OR entity success_zero(cnpj14 root + http_204_complete)
```

## Deliberately unversioned

- PG dump M5-backup `*.dump`
- CNPJ cache backups `*.bak` / `*.pre-purge-mismatch`
- `.env*`
- Large qw-01 universe_snapshot / coverage_gaps

## Next (extra-roi)

1. Editais presence/ops (main material gap)
2. DOD evidence-only flips toward 55%
3. Keep N09 as BLOCKED_SOURCE until gold sample
4. Independent QA / adversarial before any DONE claim
