# GO / NO-GO

**Terminal state:** `ENGINEERING_IN_PROGRESS`

**NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY:** `False`

**PILOT_TECHNICAL_READINESS:** `PARTIAL`
**NATIONAL_RESERVE_READINESS:** `PARTIAL_0.8_DAYS`
**RESERVE_DAYS:** `0.8` (= ESR / (eph × hours))

**PILOT_READY_CANDIDATE:** `False`

**EMAIL_SEND_READY (strict):** 72
**MIN_OPERATIONAL_RESERVE:** 900
**Gap:** 828
**full_source_ladder_complete:** `False`

## Gates

```json
{
  "FULLY_RECONCILED": true,
  "all_confirmed_terminal": true,
  "full_source_ladder_complete": false,
  "ladder_yield_missing": [
    "transparency_compras"
  ],
  "email_send_ready_ge_min_reserve": false,
  "strict_esr_measured": true,
  "service_fit_ontology_ok": true,
  "service_fit_unsupported_count": 0,
  "machine_audit_pass": false,
  "machine_audit_sample_size": 72,
  "sha_bound": true,
  "warmbly_e2e_pass": true,
  "warmbly_feed_import_pass": true,
  "warmbly_behavioral_complete": true,
  "warmbly_partial_config_only": false
}
```

**One action:** Completar source ladder nacional (missing/partial: transparency_compras); transparency_compras e demais PUBLIC_NO_AUTH exigem companies_attempted>=8382. RETRY_PENDING=0; ESR=72 reserve=900.

## Human review

```bash
python -m scripts.confenge.human_review --sample artifacts/confenge/national-commercial-ready/HUMAN-REVIEW-SAMPLE.json --reviewer tiago
```
