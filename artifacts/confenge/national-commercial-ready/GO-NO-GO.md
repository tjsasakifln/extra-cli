# GO / NO-GO

**Terminal state:** `EXTERNAL_BLOCKER_REQUIRES_TIAGO`

**NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY:** `False`

**PILOT_TECHNICAL_READINESS:** `READY_FOR_HUMAN_REVIEW`
**NATIONAL_RESERVE_READINESS:** `PARTIAL_0.8_DAYS`
**RESERVE_DAYS:** `0.8` (= ESR / (eph × hours))

**PILOT_READY_CANDIDATE:** `True`

**EMAIL_SEND_READY (strict):** 72
**MIN_OPERATIONAL_RESERVE:** 900
**Gap:** 828
**full_source_ladder_complete:** `True`

## Gates

```json
{
  "FULLY_RECONCILED": true,
  "all_confirmed_terminal": true,
  "full_source_ladder_complete": true,
  "email_send_ready_ge_min_reserve": false,
  "strict_esr_measured": true,
  "service_fit_ontology_ok": true,
  "service_fit_unsupported_count": 0,
  "machine_audit_pass": true,
  "machine_audit_sample_size": 100,
  "sha_bound": true,
  "warmbly_e2e_pass": true
}
```

**One action:** ESR strict final=72 com ladder terminal; gap_to_900=828. Autorizar fontes autenticadas de maior yield (documentadas por portal) OU decisão comercial de MIN_OPERATIONAL_RESERVE — sem atalho de engenharia.

## Human review

```bash
python -m scripts.confenge.human_review --sample artifacts/confenge/national-commercial-ready/HUMAN-REVIEW-SAMPLE.json --reviewer tiago
```
