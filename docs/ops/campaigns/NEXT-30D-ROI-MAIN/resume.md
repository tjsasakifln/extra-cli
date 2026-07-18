# Resume protocol — NEXT-30D-ROI-MAIN

## Quick start (no chat required)

```bash
cd "$(git rev-parse --show-toplevel)"
git checkout main
git fetch origin main
git status -sb   # must be clean and synced
cat docs/ops/campaigns/NEXT-30D-ROI-MAIN/resume.md
cat docs/ops/campaigns/NEXT-30D-ROI-MAIN/scope.json  # after freeze
python3 squads/extra-dod-roi/scripts/cli.py status
# writer lock
python3 squads/extra-dod-roi/scripts/main_writer_lock.py status
# next work
python3 squads/extra-dod-roi/scripts/cli.py force-next   # after main-direct
```

## State files

| File | Role |
|------|------|
| `docs/ops/campaigns/NEXT-30D-ROI-MAIN/baseline.json` | Immutable baseline snapshot |
| `docs/ops/campaigns/NEXT-30D-ROI-MAIN/ledger.jsonl` | Append-only events |
| `docs/ops/campaigns/NEXT-30D-ROI-MAIN/scope.json` | Frozen scope contract |
| `docs/ops/campaigns/NEXT-30D-ROI-MAIN/blockers.json` | Open blockers |
| `squads/extra-dod-roi/state/campaigns/next-30d-roi-main.json` | Machine campaign state |
| `squads/extra-dod-roi/state/locks/main-writer.lock` | Global write lock |

## Rules

1. Work only on `main`; no PR; no force-push.
2. One writer at a time (main-writer.lock).
3. Independent QA before accepting DONE.
4. Do not re-count prior campaign flips.
5. Re-rank after every accepted increment.
6. If interrupted: read ledger tail + campaign state + lock recovery.

## Baseline HEAD

`fbc586856332db11ecb21ae4524dfdf29dd90857` @ 2026-07-18T19:19:39Z
