# Production readiness evidence pack — 20260802T130202Z

Skeptic remediation pack. Re-proves gates C/F/G/H and official SINAPI acquisition path.
Deploy SHA recorded in `vps-deploy.json`.

| Gate | Result |
|------|--------|
| A Code | PASS — consulting workflows registered; official SINAPI acquire; restore integrity; real-case chain |
| B Quality | CI on tip after push |
| C E2E | PASS — Playwright 12/12 (16 flows), real `workflow.edital_case` / budget / acervo / bid IDs |
| D Scale | PASS — dual-run 4.4M checksum match (unchanged full_scale path; see full-scale-benchmark.json) |
| E Operation | PASS — VPS `.deployed_sha` matches tip; lag_cleared 407/407 |
| F Observability | PASS — live webhook fire+receive (`channels_configured=true`) |
| G Recovery | PASS — restore with domain row counts + content fingerprints |
| H Real case | PASS — same-execution chain edital→budget→acervo→bid→PDF/XLSX |

SINAPI: **OFFICIAL_SIDRA_INDEX** (IBGE SIDRA live; not STRUCTURE_ONLY demo).

Terminal: **PASS_PRODUCTION_READINESS_IMPLEMENTED_AND_PROVEN**

Non-claims:
- CAIXA composition bulk zip not acquired (portal redirect loop)
- Full-scale dual-run reused from proven pack when full_scale module unchanged
