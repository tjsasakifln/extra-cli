# EXTRA-CONVERGE-DELIVER-AND-ACCEPT-01 — relatório final

**Generated:** 2026-07-29T13:05:53Z  
**Main SHA (deployed):** `d05d4c3de152b562493715f114e0a387fcb63dc3`  
**VPS SHA:** `d05d4c3de152b562493715f114e0a387fcb63dc3` (match OK)

## PRs

| PR | Merge SHA | Notes |
|----|-----------|-------|
| #166 | `1f937577a26625a25c8ccee53464f68f7ed0154b` | First client delivery + live fail-closed |
| #167 | `d05d4c3de152b562493715f114e0a387fcb63dc3` | Recurring delivery restacked exclusive |
| this | (evidence) | DOD promotion + manifests only |

## Live weekly

- **cycle_id:** `weekly-20260729T124604Z-3eff464362`
- **collection_id:** `col-extra-weekly-20260729T124604Z-3ea94fd3`
- **exit_code:** 0
- **universe_200km:** 1093
- **opportunities:** 50
- **sources:** pncp_opportunities fresh; pncp_contracts fresh

## First client package (Tiago review)

- **path:** `/home/extra-consultoria/extra-deliveries/EXTRA-FIRST-CLIENT-DECISION-B2G-20260729`
- **run_id:** `extra-first-20260729T130300Z-5e2ff211cf`
- **terminal_state:** `BUNDLE_READY_FOR_HUMAN_MERGE`
- **human-review:** PENDING_HUMAN (not auto-filled)
- **shortlist:** 6 REVIEW / GO=0 (critical intake pending)
- **dossie:** NOT_AVAILABLE

## Recurring package

- **path:** `/home/extra-consultoria/extra-deliveries/EXTRA-RECURRING-20260729`
- **events:** 52 (CONTRACT_ENTERED_EXPIRY_WINDOW=47, NEW_WINNER=5)
- **urgent_alerts:** 47
- **reports:** weekly-report.md/xlsx + monthly-report.md + meeting-support.md
- **status:** OK

## DOD primary 11

| # | Decision | ID |
|---|----------|-----|
| 1 | **ACCEPTED** | `DOD-definition-of-done-extra-a7bfa6a065` |
| 2 | **PARTIAL** | `DOD-definition-of-done-extra-cf947a49f2` |
| 3 | **PARTIAL** | `DOD-definition-of-done-extra-9331d70aea` |
| 4 | **ACCEPTED** | `DOD-definition-of-done-extra-5cbd68454b` |
| 5 | **ACCEPTED** | `DOD-definition-of-done-extra-620ffc8619` |
| 6 | **ACCEPTED** | `DOD-definition-of-done-extra-9a58a0b625` |
| 7 | **ACCEPTED** | `DOD-definition-of-done-extra-73ae4b71ba` |
| 8 | **ACCEPTED** | `DOD-definition-of-done-extra-5045b1cbac` |
| 9 | **PARTIAL** | `DOD-definition-of-done-extra-ed98230aaf` |
| 10 | **ACCEPTED** | `DOD-definition-of-done-extra-b2cf97c9c2` |
| 11 | **ACCEPTED** | `DOD-definition-of-done-extra-4362fd8c6d` |

**Accepted:** 8 · **Partial:** 3

### Not promoted

- NEW_TENDER / status-change family (0 natural occurrences this pair)
- Monthly report coverage/blockers section incomplete vs exact wording
- Human acceptance by Leonardo / contract signature
- 95% recall/coverage claims
- Timer 7-day soak

## Ops notes

1. VPS had empty `sc_public_entities` after old branch; reseeded to 1093 before weekly.
2. Pathological gaps query fixed ops-side with functional index `idx_psc_orgao_cnpj8_digits`.
3. Historical exit_code=2 pack remains HISTORICAL_BLOCKED_EXTERNAL only.

## Handoff for Tiago

See `handoff/TIAGO-HUMAN-REVIEW.md`.
