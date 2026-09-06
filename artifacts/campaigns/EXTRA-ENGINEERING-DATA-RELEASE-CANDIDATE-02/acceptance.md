# Candidate acceptance split

CODE_CANDIDATE_READY=YES

MERGE_BLOCKED_BY_EXTRA_468=YES

PRODUCTION_EVIDENCE_PENDING=YES

NO_MERGE=YES

NO_DEPLOY=YES

## Local code gates

- focused unit/static tests, including signed/published and terminal fixtures;
- wrong-cwd freshness replay;
- disposable PostgreSQL clean migrations, upgrade from 107, reapply,
  reverse-order rollback and reapply;
- replay/idempotency and shipped-view query contract;
- local representative seven-day `EXPLAIN ANALYZE` under 10 seconds;
- full repository suite attempted: 1,531 passed before a missing-DSN setup
  error; the real-DB selection separately reached 256 passed with one
  pre-existing cluster-global role isolation failure;
- generated-artifacts and PR-reviewability policies;
- exact-HEAD CI remains the remote authority before any future review-ready
  transition; this PR stays draft and blocked by #468 regardless.

CodeRabbit local review was unavailable because the installed CLI is signed
out and its configured legacy flags are unsupported. This is not represented
as a pass; GitHub review/check status remains required.

## Production evidence deliberately pending

- structural-field and engineering-class backfill coverage;
- supplier registry coverage and cadastral contact hit rate;
- F1-F8 refresh time/data parity and F9 reconciliation;
- terminal-term coverage/latency;
- seven-day view latency at production volume;
- any commercial cohort, contact, feed or delivery evidence.

None of these may be inferred from fixtures or local disposable-DB results.
