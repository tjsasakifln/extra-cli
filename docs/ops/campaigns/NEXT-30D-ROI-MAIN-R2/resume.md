# Resume protocol — NEXT-30D-ROI-MAIN-R2

## Quick start

```bash
cd "$(git rev-parse --show-toplevel)"
git checkout main && git fetch origin main
git status -sb   # prefer clean + synced
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
cat docs/ops/campaigns/NEXT-30D-ROI-MAIN-R2/STATUS.md
cat docs/ops/campaigns/NEXT-30D-ROI-MAIN-R2/FINAL-REPORT.md
python3 squads/extra-dod-roi/scripts/cli.py status
python3 squads/extra-dod-roi/scripts/main_writer_lock.py status
```

## Latest HEAD

`48d0c418c1799d86873621b0bc1abe09175a951e` @ 2026-07-18T21:55:14Z

## Rules

1. main-direct only; no PR; no force-push
2. One writer (`main-writer.lock`)
3. Independent QA before DONE
4. Do not re-count R1 inherited flips
5. PERT days from critical DONE with evidence only
6. PARTIAL is not DONE

## State files

| File | Role |
|------|------|
| baseline.json | R2 start |
| scope.json | Frozen contract (all terminal) |
| ledger.jsonl | Append-only events |
| metric-lineage.json | Separated metrics |
| FINAL-REPORT.md | Close report |
| next-ranked-backlog.json | Next work |
