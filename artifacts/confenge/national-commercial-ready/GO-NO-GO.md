# GO / NO-GO

**Terminal state:** `EXTERNAL_BLOCKER_REQUIRES_TIAGO`

**NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY:** `False`

**PILOT_TECHNICAL_READINESS:** `READY_FOR_HUMAN_REVIEW`
**NATIONAL_RESERVE_READINESS:** `PARTIAL_0.79_DAYS`
**RESERVE_DAYS:** `0.79`

**PILOT_READY_CANDIDATE:** `True`

**EMAIL_SEND_READY (strict):** 71
**MIN_OPERATIONAL_RESERVE:** 900
**Gap:** 829
**full_source_ladder_complete:** `True`

## Gates

```json
{
  "FULLY_RECONCILED": true,
  "all_confirmed_terminal": true,
  "full_source_ladder_complete": true,
  "ladder_yield_missing": [],
  "email_send_ready_ge_min_reserve": false,
  "strict_esr_measured": true,
  "service_fit_ontology_ok": true,
  "service_fit_unsupported_count": 0,
  "machine_audit_pass": true,
  "machine_audit_sample_size": 100,
  "sha_bound": true,
  "warmbly_e2e_pass": true,
  "warmbly_feed_import_pass": true,
  "warmbly_behavioral_complete": true,
  "warmbly_partial_config_only": false
}
```

**One action:** ESR strict final=71 com ladder terminal; gap_to_900=829. Autorizar fontes autenticadas de maior yield (documentadas por portal) OU decisão comercial de MIN_OPERATIONAL_RESERVE — sem atalho de engenharia.

## Human review

```bash
python -m scripts.confenge.human_review --sample artifacts/confenge/national-commercial-ready/HUMAN-REVIEW-SAMPLE.json --reviewer tiago
```
