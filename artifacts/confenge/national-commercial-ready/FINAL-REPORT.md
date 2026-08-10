# FINAL-REPORT — National commercial reservoir (strict ESR)

- generated_at: `2026-08-10T18:20:40Z`
- extra_cli_sha: `238754c071a163daf6747876c65aab025f71b2d3`
- TARGET_CONFIRMED: **8382**
- EMAIL_SEND_READY strict: **72**
- email roots upper bound: **223**
- MIN_OPERATIONAL_RESERVE: **900** (10/h × 9h × 10d)
- NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY: **False**
- PILOT_READY_CANDIDATE: **False**
- terminal: **ENGINEERING_IN_PROGRESS**
- machine audit PASS: **False** (n=72)

## Funnel (strict)

```json
{
  "TOTAL_CONTACT_CANDIDATES": 315,
  "DISTINCT_COMPANIES_WITH_EMAIL": 223,
  "COMPANY_OWNED": 83,
  "IDENTITY_SAFE": 83,
  "MAILBOX_ALLOWED": 220,
  "PROVENANCE_VALID": 72,
  "SERVICE_FIT_VALID": 223,
  "COPY_CONTEXT_VALID": 72,
  "EMAIL_SEND_READY_DISTINCT_COMPANIES": 72
}
```

## Notes

- email observed ≠ EMAIL_SEND_READY
- gestao_monitoramento_contratual is a valid CONFENGE service; service_fit requires portfolio signals (not bare label)
- HUMAN_REVIEW_PENDING until Tiago executes human_review CLI
- NO REAL COMMERCIAL SEND during this goal
