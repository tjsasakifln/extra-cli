# FINAL REPORT — CONFENGE-OUTREACH-UNCONDITIONAL-GO-01

Generated: `2026-08-10T07:21:12Z`

## Terminal verdict

**`GO_FOR_REAL_CONFENGE_EMAIL_PILOT`**

## Historical contaminated evidence (invalid)

- Prior ESR=62 with `demo00Xobra.com.br` marked COMPANY_OWNED/VERIFIED — **INVALIDATED**
- Do not reuse old audit50 / WRONG_CONTACT=0 from that cohort

## New clean evidence

| Item | Value |
|------|-------|
| Cohort | CLEAN_LIVE_CONFIRMED_IDENTITY_V8 |
| Companies | 50 |
| Feed | confenge.outreach.v1 leads with provenance_chain on every contact |
| Import | completed, dry_run=false, leads_processed=50, invalid=0 |
| DB taint | 0 demo/fixture/skeptic-wrong-ownership contacts |
| No-send | kill-switch paused, auto_send=false, dispatch PAUSED |
| Hostinger | SMTP/IMAP PASS; self-smoke + continuous Unibox + replies |
| SHAs | extra `313266f1` = host; warmbly `81d83429` = host |

## Skeptic gap closure

1. Wrong-ownership sample emails **absent** from V8 cohort and production contacts.
2. provenance_chain **list** present on all 50 feed contacts (not only booleans).
3. Count reconcile **50/50/50** (send-ready / feed / import).
4. Import flag **completed** with `clean_cohort_imported_to_production=true` (no contradictory false).
5. Reply-stop/IMAP **session-proven** on warmbly `81d83429` via Unibox DB + status.sh (not prior_proof_retained only).
