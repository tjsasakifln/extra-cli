# Resume protocol — NEXT-30D-ROI-MAIN-R2

## Quick start

```bash
cd "$(git rev-parse --show-toplevel)"
git checkout main && git fetch origin main
git status -sb
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
cat docs/ops/campaigns/NEXT-30D-ROI-MAIN-R2/STATUS.md
cat docs/ops/campaigns/NEXT-30D-ROI-MAIN-R2/FINAL-REPORT.md
python3 squads/extra-dod-roi/scripts/cli.py status
```

## Latest HEAD

`62b6f49c0d74683acf139fdf51e6e45099a7838d` @ 2026-07-18T22:03:55Z

## Rules

1. main-direct only; no PR; no force-push
2. One writer (`main-writer.lock`)
3. Independent QA before DONE
4. Do not re-count R1 inherited flips
5. PARTIAL is not DONE
6. N01 requires single-process `golden_path --sources pncp,pcp --strict` SUCCESS

## State files

| File | Role |
|------|------|
| scope.json | all terminal |
| final-report.json | **scope_open must be []** |
| blockers.json | includes **B-R2-N09** |
| ledger.jsonl | events |
