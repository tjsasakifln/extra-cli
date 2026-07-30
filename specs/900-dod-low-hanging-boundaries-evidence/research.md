# Research notes

## Existing assets reused

| Asset | Use |
|-------|-----|
| `tools/dod_controller.py` | IDs, verify/accept gates (PR B only) |
| `scripts/ops/requirement_states.py` | PARTIAL/BLOCKED/NA/field absence |
| `scripts/ops/dod_process_integrity.py` | evidence-only / unit≠e2e / three rolls |
| `scripts/coverage/dual_capability_coverage.py` | no average; data_presence descriptive; claims_forbidden |
| `tests/test_requirement_states.py` | regression for family A |
| `tests/test_dual_capability_coverage.py` | dual semantics |

## Gaps closed by this campaign

- No canonical negative-scope config  
- No executable per-item proof for §2.3 exclusions  
- No client claim guard with exceptions  
- Code-ready dual items never registered for accept  

## Decisions

- Spec ID `900` avoids collision with commercial `006`  
- Scanners limited to implementation roots for performance and signal  
- Family E optional; no new restore runs  
