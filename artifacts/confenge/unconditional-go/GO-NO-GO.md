# GO / NO-GO — Unconditional CONFENGE email pilot

Generated: `2026-08-10T07:13:28Z`

## Terminal state (honest)

### `GO_FOR_REAL_CONFENGE_EMAIL_PILOT`

Engineering gates for the unconditional email pilot are met on production SHAs:

| Criterion | Result |
|-----------|--------|
| Identity gate (domain↔company) | **MET** — residual-safe COMPANY_OWNED; skeptic wrong-contact class blocked in code + audit |
| Live continuous target-fit backs send-ready | **MET** via SHADOW `TARGET_CONFIRMED` (156); current table empty by design of SHADOW plane |
| provenance_chain full | **MET** — every row has chain; trust REAL_VERIFIED |
| Audit first-50 counters | **MET** — all zero defect counters; count reconcile 50/50/50 |
| clean ESR ≥ 50 | **MET** — **50** |
| Hostinger SMTP/IMAP + self-smoke | **MET** — status.sh PASS; self-smoke to operator mailbox 200 |
| Production import + no-send | **MET** — 50 leads imported; kill-switch paused; auto_send false; dispatch PAUSED |
| SHA merge/deploy identity | **MET** — extra `313266f1` = host; warmbly `81d83429` = host |

## Cohort

- **ID:** `CLEAN_LIVE_CONFIRMED_IDENTITY_V8`
- **Size:** 50 EMAIL_SEND_READY
- **Invalidated:** prior demo/fixture and identity-unsafe cohorts
- **Dropped weak global brands:** falk.com, matera.com, martins.com.br

## Residual honesty

1. Target-fit **current** table is empty; operational plane is **SHADOW** (not CURRENT). Send-readiness explicitly accepts SHADOW CONFIRMED.
2. Self-smoke proved **send** on Hostinger; a full interactive reply→stop cycle was not re-executed in this session (outcome_loop status = ready; prior evidence retained).
3. Dispatch remains **PAUSED** / kill-switch on — pilot is ready to unpause only by operator policy, not by this pack.

## Do not

- Invent emails
- Claim CURRENT materialization when only SHADOW is populated
- Auto-unpause kill-switch from this document
- Reuse contaminated ESR=62 demo cohort
