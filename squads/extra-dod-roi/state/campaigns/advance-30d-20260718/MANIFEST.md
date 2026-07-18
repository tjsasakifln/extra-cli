# Campaign Manifest — ADVANCE-30D-LOCAL-READY

| Field | Value |
|-------|-------|
| campaign_id | ADVANCE-30D-LOCAL-READY-20260718 |
| epic_branch | `epic/advance-30d-local-ready-20260718` |
| initial_sha | `fbc586856332db11ecb21ae4524dfdf29dd90857` |
| started_at | 2026-07-18T12:42:30.202348+00:00 |
| squad | `squads/extra-dod-roi` |
| selection_rule | ranking[0] only via force-next |
| merge_to_main_during_campaign | **FORBIDDEN** |
| target | candidate defensável a LOCAL_READY (DoD §35.1 only if proven) |

## Non-claims at start

- NOT LOCAL_READY / PRE_VPS_FINAL_READY / VPS_OPERATIONAL / PROJECT_DONE
- operational_source_coverage is NOT ≥95% (stale snapshot ~0%)
- Fixtures ≠ live health; open PR ≠ integrated code

## Artifacts

- baseline: `squads/extra-dod-roi/state/campaigns/advance-30d-20260718/baseline.json`
- scorecard: `scorecard.json`
- blockers: `blockers.json`
- decisions: `decisions.jsonl`
- ownership: `ownership.json`
- matrix: `requirements-matrix.json`
- command ledger: `commands.jsonl`
