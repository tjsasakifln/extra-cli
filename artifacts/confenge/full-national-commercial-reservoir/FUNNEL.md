# CONFENGE Full National Commercial Reservoir — FUNNEL

Generated: `2026-08-10T07:23:47.969866+00:00`

## Principle

The datalake is a national asset. The commercial pipeline treats it as a
**continuously explored reservoir**, not a Top-50 spreadsheet.
Send capacity controls **velocity**, not **visibility**.

## Closed funnel

| STAGE | COUNT | % OF PREVIOUS | % OF NATIONAL | LOSS / NOTES |
|-------|------:|--------------:|--------------:|--------------|
| canonical national B2G construction companies | 48748 | n/a | 100.0% | — |
| target-fit eligible roots | 48748 | 100.0% | 100.0% | — |
| target-fit dirty/enqueued | 1194 | 2.4% | 2.4% | — |
| target-fit processed | 1054 | 88.3% | 2.2% | — |
| target-fit current materialized | 1038 | 2.1% | 2.1% | HISTORICAL_KEYSET_EARLY_EXIT=499, NOT_YET_FULL_RECONCILED=47710, NO_CONTINUOUS_WORKER_DRAIN=1, PARTIAL_CONSTRUCTION_REQUEUE=1038, SHADOW_VS_CURRENT_AUTHORITY_GAP=1 |
| TARGET_CONFIRMED | 156 | 15.0% | 0.3% | — |
| TARGET_PROBABLE_RESEARCH | 609 | 58.7% | 1.2% | — |
| TARGET_OUT_OF_SCOPE | 273 | 26.3% | 0.6% | — |
| activation WATCH | — | n/a | n/a | — |
| activation RESEARCH_REQUIRED | — | n/a | n/a | — |
| activation ACTIONABLE_NOW | — | n/a | n/a | — |
| activation SUPPRESSED | — | n/a | n/a | — |
| companies contact-discovery attempted | 41 | 26.3% | 0.1% | mailbox_purpose_rejected=2, never_attempted_of_confirmed=115, note=attempted count = proven ESR cohort only (lower bound); continuous enrichment not yet national |
| companies contact-discovery never attempted | 115 | 73.7% | 0.2% | — |
| companies with any email candidate | 41 | 100.0% | 0.1% | — |
| companies with real public email | 41 | 100.0% | 0.1% | — |
| COMPANY_OWNED | 41 | 100.0% | 0.1% | — |
| identity-safe | 41 | 100.0% | 0.1% | — |
| provenance-valid | 41 | 100.0% | 0.1% | — |
| service-fit valid | 41 | 100.0% | 0.1% | SERVICE_MONOCULTURE_reajuste_pct=100.0, causal_diagnosis_required=True |
| copy-context valid | 41 | 100.0% | 0.1% | — |
| EMAIL_SEND_READY | 39 | 25.0% | 0.1% | PRESS_mailbox=1, SOCIAL_PROGRAM_mailbox=1, awaiting_discovery_on_confirmed=115 |
| Warmbly imported | 41 | 105.1% | 0.1% | — |
| Warmbly currently eligible | 0 | 0.0% | 0.0% | — |
| Active hot-set | 10 | 25.6% | 0.0% | — |

## Headline capacity (honest)

- National universe: **48748**
- TARGET_CONFIRMED: **156**
- Contact attempted: **41**
- Company-owned / identity-safe: **41**
- EMAIL_SEND_READY reservoir: **39**
- Active hot-set: **10**
- Warmbly capacity: **10/h EMAIL_ONLY** (WhatsApp OFF)

## PILOT_GO vs NATIONAL_RESERVOIR_HEALTHY

```json
{
  "pilot": {
    "PILOT_GO": false,
    "MINIMUM_PILOT_ACCEPTANCE_SAMPLE": 50,
    "email_send_ready": 39,
    "pilot_sample_met": false,
    "zero_false_target": true,
    "zero_wrong_contact": false,
    "zero_tainted_provenance": true,
    "zero_unsupported_service": false,
    "zero_hollow_copy": true,
    "zero_unsafe_claim": true,
    "note": "PILOT_GO is independent of NATIONAL_RESERVOIR_HEALTHY. Do not treat ESR≥50 as pipeline capacity or business objective."
  },
  "national": {
    "NATIONAL_RESERVOIR_HEALTHY": false,
    "FULL_NATIONAL_READY": false,
    "coverage_mode": "BOOTSTRAPPING",
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

Root causes of ~1.038 materialization (host 2026-08-10): (1) Pre-#215 keyset pagination early-exit (reconcile missing=499); (2) SHADOW population ignored by reconcile (checked empty current); (3) continuous worker unit disabled; refresh only drains when CDC>0; (4) construction requeue stopped at 1038; full 511k roots / 48.7k eligible not visited; (5) contact enrichment on pilot cohort only. Campaign fixes: SHADOW-aware reconcile, coverage watermark/modes, drain-worker hook, mailbox PRESS/SOCIAL, multi-service signals, monoculture diagnostic.

## DO NOT

- Optimize for ESR ≥ 50 as capacity
- Stop target-fit / enrichment / materialization at Top-N
- Claim FULL_NATIONAL_READY without full reconcile evidence
- Treat worker HEALTHY + 2% populated as national readiness

