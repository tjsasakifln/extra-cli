# CONFENGE National Commercial Reservoir — FUNNEL

Generated: `2026-08-10T12:42:52Z`

## Closed funnel

| STAGE | COUNT | % OF PREVIOUS | NOTES |
|-------|------:|--------------:|-------|
| NATIONAL_COMMERCIAL_UNIVERSE | 513650 | n/a | supplier CNPJ roots (canonical) |
| TARGET_CONFIRMED | 8382 | 1.63% | — |
| TARGET_PROBABLE_RESEARCH | 26083 | 5.08% | requires positive ICP evidence |
| TARGET_OUT_OF_SCOPE | 92543 | 18.02% | — |
| TARGET_INSUFFICIENT_EVIDENCE | 386642 | 75.27% | not PROBABLE — no positive ICP evidence |
| target_fit_class_partition_sum | 513650 | 100.00% | CONFIRMED+PROBABLE+OUT+INSUFFICIENT (should ≈ universe when fully classified) |
| CONTACT_READY | 8 | 0.10% | — |
| CONTACT_FOUND_NOT_SENDABLE | 25 | 0.30% | — |
| CONTACT_EXHAUSTED | 233 | 2.78% | — |
| CONTACT_RETRY_PENDING | 11 | 0.13% | — |
| CONTACT_EXTERNAL_BLOCKER | 0 | 0.00% | — |
| CONTACT_NEVER_ATTEMPTED | 8084 | 96.44% | — |
| contact_terminal_partition_sum | 8361 | 99.75% | must equal TARGET_CONFIRMED |
| EMAIL_SEND_READY | 60 | 0.72% | — |
| WARMBLY_RESERVOIR | 60 | 100.00% | — |
| ACTIVE_HOT_SET | 10 | 16.67% | — |

## Independent capacity metrics

```json
{
  "schema": "confenge.operational_capacity_metrics.v1",
  "PILOT_ACCEPTANCE_SAMPLE": 50,
  "NATIONAL_EMAIL_SEND_READY_RESERVOIR": 60,
  "ACTIVE_HOT_SET": 10,
  "MIN_OPERATIONAL_RESERVE": 900,
  "operational_reserve_days": 10,
  "emails_per_hour": 10.0,
  "business_hours_per_day": 9.0,
  "reserve_gate_ok": false,
  "hot_set_le_reservoir": true,
  "pilot_is_not_capacity": true,
  "note": "50 is PILOT_ACCEPTANCE_SAMPLE (quality only). Reservoir=60, hot_set=10, min_reserve=900.",
  "warmbly": {
    "email_only": true,
    "whatsapp_enabled": false,
    "auto_send_enabled": false,
    "sending_paused": false,
    "send_window_start": "09:00",
    "send_window_end": "18:00"
  }
}
```

## Principle

- `PILOT_ACCEPTANCE_SAMPLE=50` is quality-only.
- `NATIONAL_EMAIL_SEND_READY_RESERVOIR` is the commercial inventory.
- `ACTIVE_HOT_SET` is a rolling throughput window, not a fixed cohort.
