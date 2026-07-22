# STATUS — DUAL-CAPABILITY-COVERAGE-TRUTH-01

**Status:** FINAL-CLOSURE IN PROGRESS (not GOAL DONE until CI + #107 + review + merge)  
**Date:** 2026-07-22  

## Observed SHAs (roles)

| Role | SHA / note |
|------|------------|
| `origin_main_observed_at_baseline` | `1c063005e5116ff394e26ef3ac3221c7f97c2d01` |
| `implementation_branch` | `fix/dual-canonical-closure` |
| `reproof` | live dual in `evidence/dual-reproof-summary-final-closure.json` |

Do **not** label ancestral SHAs as “current tip”.

## Policy

| Field | Value |
|-------|-------|
| status | **active** |
| policy_version | 2.0.0 |
| policy_sha256 | `867d77b3a18a3c154aa08ec94e83e2e580234c77adba03059d8e4da46d473e46` |
| authority | `config/source_applicability.yaml` + `scripts/coverage/source_policy.py` |

## Live dual snapshot (final-closure reproof)

| Field | Value |
|-------|-------|
| measurement_success | true |
| mapping_status | partial (DB unmapped residual OK) |
| identity_unresolved_count | **0** |
| dual_gate_status | FAIL (coverage 0%; not 95%) |
| source_combinations open_tenders | pncp, pncp+ciga_ckan |
| source_combinations historical | pncp, pncp+contracts |
| den (approx) | 946 applicable (147 unknown esfera honest) |

## Evidence

* New pack: `.dod/evidence/DOD-rol-1-definition-of-done-1fdea0f6e6/`
* Old pack `4efe05fc94`: SUPERSEDED

## Non-claims

* No operational 95% dual coverage  
* No LOCAL_READY / PROJECT_DONE  
