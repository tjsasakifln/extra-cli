# FINAL-REPORT — National commercial reservoir (strict ESR)

- generated_at: `2026-08-10T18:46:55Z`
- extra_cli_sha: `84d3779656b162c85ca72373722f126ef87be638`
- TARGET_CONFIRMED: **8382**
- EMAIL_SEND_READY strict: **71**
- email roots upper bound: **223**
- MIN_OPERATIONAL_RESERVE: **900** (10/h × 9h × 10d)
- NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY: **False**
- PILOT_READY_CANDIDATE: **True**
- terminal: **EXTERNAL_BLOCKER_REQUIRES_TIAGO**
- machine audit PASS: **True** (n=100)

## Funnel (strict)

```json
{
  "TOTAL_CONTACT_CANDIDATES": 315,
  "DISTINCT_COMPANIES_WITH_EMAIL": 223,
  "COMPANY_OWNED": 80,
  "IDENTITY_SAFE": 80,
  "MAILBOX_ALLOWED": 220,
  "PROVENANCE_VALID": 71,
  "SERVICE_FIT_VALID": 223,
  "COPY_CONTEXT_VALID": 71,
  "EMAIL_SEND_READY_DISTINCT_COMPANIES": 71
}
```

## Notes

- email observed ≠ EMAIL_SEND_READY
- gestao_monitoramento_contratual is a valid CONFENGE service; service_fit requires portfolio signals (not bare label)
- HUMAN_REVIEW_PENDING until Tiago executes human_review CLI
- NO REAL COMMERCIAL SEND during this goal
