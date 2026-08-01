# Production readiness evidence

SHA: see final-verdict.json / baseline.json

## Proven
- Fair entity×source queue (tests + 1093 discovery / 407 active / 1768 pairs on VPS)
- Full-scale VPS: 4,479,442 contracts, ~55MB RSS, ~27k rows/s, publication_allowed
- Consulting chain: budget audit PDF/XLSX, acervo match, bid readiness BLOCKED, deliverables manifest
- Deploy + pg_dump backup + restore drill (97 tables)

## Residuals
See final-verdict.json residuals. Do not claim PASS_PRODUCTION_READINESS without closing Playwright browser E2E, alert delivery channel, dual-run compare, and green PR CI.
