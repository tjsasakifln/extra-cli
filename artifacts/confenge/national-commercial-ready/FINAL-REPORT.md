# CONFENGE National Reservoir — Final Report

**As of:** 2026-08-10T17:52:48Z
**Terminal:** `EXTERNAL_BLOCKER_REQUIRES_TIAGO`
**PR #227:** merged as `238754c071a1`

## Headline

| Metric | Value |
|--------|-------|
| TARGET_CONFIRMED | 8382 |
| full_source_ladder_complete | true |
| EMAIL_SEND_READY (strict) | 72 |
| MIN_OPERATIONAL_RESERVE | 900 |
| gap | 828 |
| RESERVE_DAYS | 0.8 |
| service_fit_unsupported | 0 |
| machine audit | n=100 PASS (real stratified sample) |
| SHA triple | 238754c071a1 equal |
| Warmbly E2E | PASS (self-smoke + DNC sticky + hot-set + paused) |

## Warmbly behavioral (this freeze)

- Self-smoke Hostinger SMTP: task `7a0465f3-301e-4e17-9ca5-a1f489556164` **completed**; message_id `<12f60934-377f-42b4-b79d-e79622bef7e8@confenge.com.br>`; commercial_leads=none
- DNC sticky: account `e470eb5a…` NOSEND PROOF remains `do_not_contact=true` after import run at 2026-08-10T16:08:47Z
- Rolling hot-set: ACTIVE=10 / eligible=72
- Controls: DISPATCH PAUSED, GREEN OFF, WHATSAPP OFF, SENDING_PAUSED

## One action

ESR strict final=72 com ladder terminal; gap_to_900=828. Autorizar fontes autenticadas de maior yield (documentadas por portal) OU decisão comercial de MIN_OPERATIONAL_RESERVE — sem atalho de engenharia.

## Human review

```bash
python -m scripts.confenge.human_review --sample artifacts/confenge/national-commercial-ready/HUMAN-REVIEW-SAMPLE.json --reviewer tiago
```
