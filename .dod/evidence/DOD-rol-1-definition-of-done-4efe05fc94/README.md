# Evidence pack — DOD-rol-1-definition-of-done-1fdea0f6e6

**Item:** O golden path calcula cobertura  
**Semantics:** dual capability coverage truth v1.2 (canonical source policy)

## SHAs (roles — do not call ancestors "current tip")

| Role | Value |
|------|-------|
| `implementation_sha` | (branch tip of `fix/dual-canonical-closure` at pack creation — restamp after merge) |
| `reproof_sha` | live dual reproof captured in this pack |
| `acceptance_sha` | set at controller accept |
| `reviewed_sha` | independent review on implementation tip |

## Separation of truths

| Layer | Result |
|-------|--------|
| `method_acceptance` | PASS — unit matrix + policy authority + dual engine |
| `live_operational_state` | `measurement_success=true`, `identity_unresolved_count=0`, `dual_gate_status=FAIL` (coverage 0%, unknown esfera residual) |
| `coverage_gate_state` | FAIL — not 95%; no LOCAL_READY |

## Supersedes

* `.dod/evidence/DOD-rol-1-definition-of-done-4efe05fc94/` → SUPERSEDED (post-acceptance semantic changes)

## Non-claims

* No operational 95%  
* No LOCAL_READY / PROJECT_DONE  
