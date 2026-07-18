# Resume protocol — NEXT-30D-ROI-MAIN-R2

**UTC:** 2026-07-18T23:06:00Z

## Policy: SmartLic dataset DEFERRED_STALE_SOURCE

- No SmartLic snapshot import on critical path
- No waiting for SmartLic DB export
- No SmartLic data in coverage/freshness/gates
- `smartlic_snapshot_import.py` = optional frozen asset only

## Quick start

```bash
cd "$(git rev-parse --show-toplevel)"
git checkout main && git fetch origin main
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"
cat docs/ops/campaigns/NEXT-30D-ROI-MAIN-R2/PLAN-30D.md
cat docs/ops/campaigns/NEXT-30D-ROI-MAIN-R2/evidence/N06c-wave/entity-coverage-delta-wave2.json
python3 squads/extra-dod-roi/scripts/main_writer_lock.py status
# Highest ROI unlocked: N06c (finish crawls + final remeasure)
```

## Extra-ROI next

1. **N06c** (IN_PROGRESS) — +68 either mid-wave; finish PNCP/contracts then close
2. N01 — golden path stability
3. N09 — recall gold sample
4. N07/N18 — own contracts history (partially advanced by 180d pilot)
5. N14 → N15 close

## State files

| File | Role |
|------|------|
| scope.json | N06c progress + SmartLic deferred |
| smartlic-reuse-matrix.json | DEFERRED_STALE_SOURCE |
| critical-path.json | next = N06c |
| evidence/N06c-wave/* | wave2 deltas Extra-only |
| ledger.jsonl | events |
