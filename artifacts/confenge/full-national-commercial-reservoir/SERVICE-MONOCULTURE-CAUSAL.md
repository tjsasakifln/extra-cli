# SERVICE_MONOCULTURE causal diagnosis (cohort 41)

## Observation
100% of the clean EMAIL_SEND_READY cohort (41) had
`service_id = estruturacao_pleito_reajuste`.

## Not accepted as explanation alone
"These companies have reajustable contracts" is insufficient.

## Causal factors
1. **Thin mature books**: single-contract / <3 contracts with real `start_date` and
   age≥365 without reajuste proof → router correctly scores reajuste verification at 60.
2. **Missing multi-contract bags in pilot path**: if only one contract is loaded into
   the intelligence bag, gestão (requires ≥3) never competes.
3. **Specialty signals not present in object text** of this cohort (no glosa/aditivo/edital tokens).
4. **Not a silent default**: empty bag → diagnóstico, not reajuste. Tests prove cases A–E.

## Fixes shipped
- `normalize_record` derives `recent_tender_activity` / rapid_growth / high_recurrence from public dates.
- Adversarial A–E tests + SERVICE_MONOCULTURE flag blocks outreach release at ≥95% without diagnosis.
- Full national rebuild of dossiers required after continuous target-fit + multi-contract load.

## Outreach
`blocks_outreach_release = true` while monoculture persists without full multi-contract rebuild.
