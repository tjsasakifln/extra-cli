# Wave 1 manual validation — 429 rate limit

## Context

- Base SHA: `75e5653c4b1e338009f6e395d3ffa50066fc16dd`
- Branch: `fix/full-suite-resilience`
- Fix SHA: `155f57cb75618bbe769278912a4cb33bef156450`
- Change: fixture-only (`tests/chaos/test_429_rate_limit.py`); no production code change

## Pytest (wave 1 required set)

| Command | Exit | Result |
|---------|-----:|--------|
| `pytest tests/chaos/test_429_rate_limit.py -q -o addopts=''` | 0 | 3 passed |
| `pytest tests/test_fetch_result.py -q -o addopts=''` | 0 | 7 passed |
| `pytest tests/test_resilience_vertical_slice.py -m "not database" -q -o addopts=''` | 0 | 4 passed, 2 deselected |

## Independent QA re-run

```text
14 passed, 2 deselected in 7.32s
QA_EXIT=0
```

Log: campaign `logs/wave1/qa-independent-rerun.log` (scratch mirrored).

## Manual HTTP 429 scenario (temp dir)

Executed against `PNCPAdapter` with injected fetcher returning HTTP 429.

| Check | Observed |
|-------|----------|
| status | `rate_limited` |
| pending checkpoint | 1 (`stage=rate_limited`, `last_http_status=429`) |
| `evidence.satisfactory` | `false` |
| watermark advanced | **no** — `ValueError: watermark exige checkpoint completo e evidence satisfatoria` |
| `success_zero` | false |
| empty confirmed | false (`empty_confirmed=false`) |

## Verdict

**PASS** — fixture contract restored; production untouched.
