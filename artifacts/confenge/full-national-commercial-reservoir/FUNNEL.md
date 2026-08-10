# CONFENGE Full National Commercial Reservoir — FUNNEL

Generated: `2026-08-10T07:58:27.146311+00:00`

## Principle

The datalake is a national asset. The commercial pipeline treats it as a
**continuously explored reservoir**, not a Top-50 spreadsheet.
Send capacity controls **velocity**, not **visibility**.

## Closed funnel

| STAGE | COUNT | % OF PREVIOUS | % OF NATIONAL | LOSS / NOTES |
|-------|------:|--------------:|--------------:|--------------|
| canonical national B2G construction companies | 511645 | n/a | 100.0% | — |
| target-fit eligible roots | 511645 | 100.0% | 100.0% | — |
| target-fit dirty/enqueued | 511645 | 100.0% | 100.0% | — |
| target-fit processed | 511645 | 100.0% | 100.0% | — |
| target-fit current materialized | 511646 | 100.0% | 100.0% | — |
| TARGET_CONFIRMED | 8337 | 1.6% | 1.6% | — |
| TARGET_PROBABLE_RESEARCH | 411025 | 80.3% | 80.3% | — |
| TARGET_OUT_OF_SCOPE | 92284 | 18.0% | 18.0% | — |
| activation WATCH | — | n/a | n/a | — |
| activation RESEARCH_REQUIRED | — | n/a | n/a | — |
| activation ACTIONABLE_NOW | — | n/a | n/a | — |
| activation SUPPRESSED | — | n/a | n/a | — |
| companies contact-discovery attempted | 8337 | 100.0% | 1.6% | mailbox_purpose_rejected=8, never_attempted=0, no_email_found=8262, note=attempted includes continuous offline pass + historical network enrichment harvest |
| companies contact-discovery never attempted | 0 | 0.0% | 0.0% | — |
| companies with any email candidate | 75 | 0.9% | 0.0% | — |
| companies with real public email | 75 | 0.9% | 0.0% | — |
| COMPANY_OWNED | 67 | 89.3% | 0.0% | — |
| identity-safe | 67 | 100.0% | 0.0% | — |
| provenance-valid | 67 | 100.0% | 0.0% | — |
| service-fit valid | 67 | 100.0% | 0.0% | — |
| copy-context valid | 67 | 100.0% | 0.0% | — |
| EMAIL_SEND_READY | 67 | 0.8% | 0.0% | historical_network_harvest=75, mailbox_purpose_blocked=8, offline_continuous_found_zero_new=True |
| Warmbly imported | 41 | 61.2% | 0.0% | — |
| Warmbly currently eligible | 0 | 0.0% | 0.0% | — |
| Active hot-set | 10 | 14.9% | 0.0% | — |

## Headline capacity (honest)

- National universe: **511645**
- TARGET_CONFIRMED: **8337**
- Contact attempted: **8337**
- Company-owned / identity-safe: **67**
- EMAIL_SEND_READY reservoir: **67**
- Active hot-set: **10**
- Warmbly capacity: **10/h EMAIL_ONLY** (WhatsApp OFF)

## PILOT_GO vs NATIONAL_RESERVOIR_HEALTHY

```json
{
  "pilot": {
    "PILOT_GO": false,
    "MINIMUM_PILOT_ACCEPTANCE_SAMPLE": 50,
    "email_send_ready": 67,
    "pilot_sample_met": true,
    "zero_false_target": true,
    "zero_wrong_contact": false,
    "zero_tainted_provenance": true,
    "zero_unsupported_service": true,
    "zero_hollow_copy": null,
    "zero_unsafe_claim": null,
    "note": "PILOT_GO is independent of NATIONAL_RESERVOIR_HEALTHY. Do not treat ESR≥50 as pipeline capacity or business objective."
  },
  "national": {
    "NATIONAL_RESERVOIR_HEALTHY": true,
    "FULL_NATIONAL_READY": true,
    "coverage_mode": "FULLY_RECONCILED",
    "requirements": [
      "full target-fit coverage >= 99.5% or fully explained gaps",
      "continuous enrichment over reservoir (no artificial truncation)",
      "observable backlog / dirty queue",
      "no EMAIL_SEND_READY hard cap",
      "service multi-service not monoculture without causal diagnosis"
    ]
  }
}
```

## Root cause of historical ~1.038 materialization

Resolved: full national materialization 511646/511645 with pagination_ok and unexplained_missing=0. Historical ~1038 was pagination+SHADOW+no-worker+rollback bug.

## DO NOT

- Optimize for ESR ≥ 50 as capacity
- Stop target-fit / enrichment / materialization at Top-N
- Claim FULL_NATIONAL_READY without full reconcile evidence
- Treat worker HEALTHY + 2% populated as national readiness

