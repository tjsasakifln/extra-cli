# GO / NO-GO

**Terminal state:** `ENGINEERING_IN_PROGRESS`

**NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY:** `False`

**PILOT_READY_CANDIDATE:** `True`

**EMAIL_SEND_READY (strict):** 72
**MIN_OPERATIONAL_RESERVE:** 900
**Gap:** 828

## Gates

```json
{
  "FULLY_RECONCILED": true,
  "all_confirmed_terminal": false,
  "email_send_ready_ge_min_reserve": false,
  "strict_esr_measured": true,
  "service_fit_ontology_ok": true,
  "machine_audit_pass": true,
  "sha_bound": false,
  "warmbly_e2e_pass": false
}
```

**One action:** Completar contact ladder full-sweep + ampliar fontes públicas (ESR=72 << reserve=900); não reduzir reserve prematuramente.

## Human review

```bash
python -m scripts.confenge.human_review --sample artifacts/confenge/national-commercial-ready/HUMAN-REVIEW-SAMPLE.json --reviewer tiago
```
