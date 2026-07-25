# Tasks 006 — CONFENGE Commercial Ready

| task_id | owner | dependencies | files | requirement_refs | test | evidence | status |
|---------|-------|--------------|-------|------------------|------|----------|--------|
| T01 | coordinator | — | baseline.json/md | Phase0 | manual | artifacts/.../baseline.* | done |
| T02 | domain | T01 | config/commercial_profiles/* | FR-01,FR-02 | test_signals | profile load ≥12 | done |
| T03 | data | T01 | db/migrations/062_*.sql | FR-06,FR-09 | migration apply | migration file | done |
| T04 | signals | T02 | scripts/commercial_leads/signals.py | FR-02,FR-04 | test_signals | 26+ unit tests | done |
| T05 | ranking | T04 | scoring.py, baseline.py | FR-04,FR-05,FR-07 | test_scoring | unit | done |
| T06 | queue | T03,T05 | review.py, pipeline.py | FR-06,FR-12 | test_review_states | unit | done |
| T07 | workspace | T06 | workspace/cli.py, Makefile | FR-11 | CLI --help | structural | done |
| T08 | exports | T05 | exports.py | FR-08 | test_exports | unit | done |
| T09 | soak | T01 | verify_soak_non_interference.py | FR-09 | gate script | soak-baseline | in_progress |
| T10 | real-run | T03–T08 | confenge_commercial_cycle.py | FR-10 | real gate | real-run.json | pending |
| T11 | docs | T02 | specs/006, ADR, entry-points, DOD impact | docs | structural | specs | in_progress |
| T12 | rc | T10,T09 | user-acceptance.json | FR-13 | RC target | PENDING_HUMAN | pending |
