# Production readiness evidence — real VPS collect session

- captured: 2026-08-02T03:09:04.241920+00:00
- code_sha (timeout fix): `fefa485d80457ae7785755cbbe204fb59465ef21`
- prior CI-green HEAD: `d54e408e635faf166d43b25f7a74afbfb0f308f5`

## Real collect (session since 2026-08-01T22:08Z)

| Metric | Value |
|--------|-------|
| session runs | 291 |
| documents downloaded | 179 |
| SUCCESS_NONZERO | 101 |
| success entities | 74 |
| overdue remaining | 335 |
| lag_cleared | **false** (capacity partial) |

Downloads by source: `{"ciga": 4, "pncp": 174, "html": 1}`

## Honesty

- NOT mark-all SUCCESS.
- Full lag drain of 407 active entities **not** achieved in wall budget.
- Terminal PASS_PRODUCTION_READINESS not claimed until lag drain + CI on final HEAD.

## Files

- `vps-full-cycle.json` — cycle1 end snapshot
- `vps-incremental-cycles.json` — three-cycles summary
- `queue-cycle.json` / `source-coverage.json` / `final-verdict.json`
