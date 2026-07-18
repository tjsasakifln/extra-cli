# Resume protocol — NEXT-30D-ROI-MAIN-R2

## Quick start (no chat required)

```bash
cd "$(git rev-parse --show-toplevel)"
git checkout main && git fetch origin main
git status -sb   # prefer clean + synced with origin/main
cat docs/ops/campaigns/NEXT-30D-ROI-MAIN-R2/resume.md
cat docs/ops/campaigns/NEXT-30D-ROI-MAIN-R2/scope.json
python3 squads/extra-dod-roi/scripts/cli.py status
python3 squads/extra-dod-roi/scripts/main_writer_lock.py status
# next work
python3 squads/extra-dod-roi/scripts/cli.py force-next
```

## State files

| File | Role |
|------|------|
| `baseline.json` / `BASELINE.md` | Immutable R2 start |
| `ledger.jsonl` | Append-only events |
| `scope.json` | Frozen campaign contract |
| `metric-lineage.json` | Separated metrics |
| `blockers.json` | Open blockers |
| `pert.json` / `critical-path.json` | CPM |
| Prior: `docs/ops/campaigns/NEXT-30D-ROI-MAIN/` | Historical R1 |

## Rules

1. main-direct only; no PR; no force-push; no remote feature branches.
2. One writer (`main-writer.lock`).
3. Independent QA before DONE.
4. Do not re-count R1 inherited flips.
5. Re-rank after every accepted increment.
6. ≥30 **new** business days on critical path (PERT), not calendar/commits.

## Baseline HEAD

`dc7cea0efb3f19b36a5133aabb235d89baf09cca` @ 2026-07-18T20:34:29Z
