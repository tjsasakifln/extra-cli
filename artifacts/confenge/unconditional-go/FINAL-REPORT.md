# FINAL REPORT — CONFENGE Unconditional GO

Generated: `2026-08-10T04:59:40Z`

## Historical contaminated evidence (INVALID)

- Claimed EMAIL_SEND_READY=62 included `licitacoes@demo00Xobra.com.br` as COMPANY_OWNED/VERIFIED on real CNPJs
- Invalidated machine-readable: CONTAMINATION-ERADICATION.json / COHORT-62-INVALIDATION.json
- Warmbly production: contaminated_sendable_count=0, all 9 demos blocked

## New clean evidence

- Provenance fail-closed gates merged (#213) + Warmbly import/CanEnroll (#35)
- Target-fit continuous merged (#212) and HEALTHY on host-of-record (SHADOW)
- SHA identity:
  - extra-cli origin/main = host = runtime: `c7fadc192131d4c39dd4d5d6a9664512c7908f9f`
  - warmbly origin/main = host = runtime: `81d83429316aa6241cc81b3ac8e761bfc59c2487`
- Clean cohort: **53** companies, first-50 audit all zeros
- Production import: leads_processed=53, errors=0 (import id 53e12361…)
- Operator self-smoke SMTP: task 9ce3f304 **completed** to tiago.sasaki@confenge.com.br only
- WhatsApp OFF; kill switch ENGAGED; EMAIL_ONLY 10/h config available

## Terminal

`EXTERNAL_BLOCKER_REQUIRES_TIAGO` — human sample review only (see GO-NO-GO.md).
