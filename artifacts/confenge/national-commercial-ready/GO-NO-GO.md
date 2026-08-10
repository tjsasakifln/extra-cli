# GO / NO-GO

**Terminal state:** `EXTERNAL_BLOCKER_REQUIRES_TIAGO`

**NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY:** `False`

## Gates

```json
{
  "canonical_universe_reconciled": false,
  "coverage_ratio_le_1": true,
  "unexplained_missing_eq_0": false,
  "orphan_materialized_eq_0": true,
  "duplicate_roots_eq_0": true,
  "target_fit_fresh": true,
  "contact_terminals_complete": false,
  "provenance_contamination_eq_0": true,
  "copy_audit_all_zero": true,
  "email_send_ready_ge_min_reserve": false,
  "sha_binding_exact": false,
  "whatsapp_off": true
}
```

## Human review command

```bash
python -m scripts.confenge.human_review --sample artifacts/confenge/national-commercial-ready/HUMAN-REVIEW-SAMPLE.json --reviewer tiago
```
