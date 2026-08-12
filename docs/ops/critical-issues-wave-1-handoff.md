# Critical Issues Wave 1 — Handoff

**Branch:** `agent/critical-issues-wave-1`  
**Scope:** #303, #286, #237, #245, #234, #278, #288, #233, #311, #313  
**Truth ceiling:** branch evidence is at most `VERIFIED`; issue closure and DOD
acceptance require exact-HEAD CI and the repository's human/main gates.

## Current state

| Issue | State | Reproducible evidence | Remaining gate |
|---:|---|---|---|
| #303 | VERIFIED | Focused contracts suite; new zero/data/multipage/error/cap/persistence cases | exact-HEAD CI + main |
| #286 | OPEN | — | implementation and test |
| #237 | OPEN | — | implementation and test |
| #245 | OPEN | — | implementation and test |
| #234 | OPEN | — | implementation and test |
| #278 | OPEN | — | implementation and test |
| #288 | OPEN | — | implementation and test |
| #233 | OPEN | — | implementation and test |
| #311 | OPEN | — | implementation and test |
| #313 | OPEN | — | implementation and test |

## #303 verification

```text
python3 -m pytest tests/test_contracts_crawler.py \
  tests/test_contracts_pilot_completion.py \
  tests/test_contracts_per_window_persist.py -q --tb=short
76 passed

python3 -m ruff check scripts/crawl/contracts_crawler.py \
  scripts/ops/run_contracts_pilot.py tests/test_contracts_crawler.py \
  tests/test_contracts_pilot_completion.py
All checks passed!
```

No live coverage, `LOCAL_READY`, or `VPS_OPERATIONAL` claim is made.
