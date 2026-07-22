# STATUS — DUAL-CAPABILITY-COVERAGE-TRUTH-01

**Status:** ENGINE_COMPLETE_V1.2 + DOD_ACCEPT_CALCULACAO (main)  
**Date:** 2026-07-22  
**Adapter:** `dual_capability_coverage/1.1.0` + skeptic remediation

## Merged

| Item | SHA / PR |
|------|----------|
| Implementation | PR #108 → `edd7618` |
| DOD accept calcula cobertura (dual method) | PR #109 → `30f5548` then main tip |
| Skeptic gaps fix | this branch → pending merge |

## Skeptic remediation (v1.2)

| Gap | Fix |
|-----|-----|
| Single-cap pipeline_success | scope_complete + dual_gate_status=NOT_EVALUATED |
| identity_unresolved measurement true | measurement_success=false when identity_unresolved_count>0 |
| mapping_status overwrite | preserve identity_unresolved |
| Dead view 058 | engine queries v_dual_capability_evidence_latest when present |
| tasks falsely open | T020–T036 + T040–T044 marked real |
| Independent review shell | executed attacks with commands (artifact) |

## Non-claims

* No operational 95% dual coverage
* No LOCAL_READY / PROJECT_DONE
