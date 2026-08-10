# CONFENGE Full National Commercial Reservoir — FUNNEL

Generated: `2026-08-10T08:44:08.264640+00:00`

## Principle

The datalake is a national asset. The commercial pipeline treats it as a
**continuously explored reservoir**, not a Top-50 spreadsheet.
Send capacity controls **velocity**, not **visibility**.

## Closed funnel

| STAGE | COUNT | % OF PREVIOUS | % OF NATIONAL | LOSS / NOTES |
|-------|------:|--------------:|--------------:|--------------|
| national supplier roots (pncp_supplier_contracts) | 511645 | n/a | 100.0% | — |
| construction-relevant (CONFIRMED+PROBABLE) | 419362 | 82.0% | 82.0% | — |
| target-fit eligible roots (supplier materialize set) | 511645 | 100.0% | 100.0% | — |
| target-fit dirty/enqueued | 1022948 | 199.9% | 199.9% | — |
| target-fit processed | 521785 | 51.0% | 102.0% | — |
| target-fit current materialized | 511646 | 100.0% | 100.0% | OUT_includes_non_construction=92284, RETRY_PENDING=500796, materialized=511646, supplier_roots=511645 |
| TARGET_CONFIRMED | 8337 | 1.6% | 1.6% | — |
| TARGET_PROBABLE_RESEARCH | 411025 | 80.3% | 80.3% | — |
| TARGET_OUT_OF_SCOPE | 92284 | 18.0% | 18.0% | — |
| activation WATCH | 0 | 0.0% | 0.0% | — |
| activation RESEARCH_REQUIRED | 0 | 0.0% | 0.0% | — |
| activation ACTIONABLE_NOW | 0 | 0.0% | 0.0% | — |
| activation SUPPRESSED | 0 | 0.0% | 0.0% | — |
| companies contact-discovery attempted | 75 | 0.9% | 0.0% | mailbox_purpose_rejected=6, network_harvest_attempted=75, never_attempted_of_confirmed=8262, no_email_in_harvest=0, offline_continuous_not_counted_as_discovery=True |
| companies contact-discovery never attempted | 8262 | 99.1% | 1.6% | — |
| companies with any email candidate | 75 | 100.0% | 0.0% | — |
| companies with real public email | 75 | 100.0% | 0.0% | — |
| COMPANY_OWNED | 68 | 90.7% | 0.0% | — |
| identity-safe | 68 | 100.0% | 0.0% | — |
| provenance-valid | 60 | 88.2% | 0.0% | — |
| service-fit valid | 60 | 88.2% | 0.0% | — |
| copy-context valid | 60 | 100.0% | 0.0% | — |
| EMAIL_SEND_READY | 60 | 0.7% | 0.0% | mailbox_purpose_rejected=6, ownership:UNRESOLVED=1, ownership_identity_domain_mismatch=8, service_code:diagnostico_contratual_b2g=9, service_fit_supported=9, sticky_ownership_insufficient_for_identity=8 |
| Warmbly imported | 60 | 100.0% | 0.0% | — |
| Warmbly currently eligible | 0 | 0.0% | 0.0% | — |
| Active hot-set | 10 | 16.7% | 0.0% | — |

## Headline capacity (honest)

- National universe: **511645**
- TARGET_CONFIRMED: **8337**
- Contact attempted: **75**
- Company-owned / identity-safe: **68**
- EMAIL_SEND_READY reservoir: **60**
- Active hot-set: **10**
- Warmbly capacity: **10/h EMAIL_ONLY** (WhatsApp OFF)

## PILOT_GO vs NATIONAL_RESERVOIR_HEALTHY

```json
{
  "pilot": {
    "PILOT_GO": false,
    "MINIMUM_PILOT_ACCEPTANCE_SAMPLE": 50,
    "email_send_ready": 60,
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
    "NATIONAL_RESERVOIR_HEALTHY": false,
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

Historical ~1038 resolved: full materialization 511646/511645, unexplained_missing=0.

## DO NOT

- Optimize for ESR ≥ 50 as capacity
- Stop target-fit / enrichment / materialization at Top-N
- Claim FULL_NATIONAL_READY without full reconcile evidence
- Treat worker HEALTHY + 2% populated as national readiness

