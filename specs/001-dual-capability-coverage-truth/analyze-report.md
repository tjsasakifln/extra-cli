# Speckit analyze — dual-capability-coverage-truth

**Date:** 2026-07-22  
**Artifacts:** spec.md · plan.md · tasks.md · checklist · ADR-030 · completion-baseline

## Cross-artifact consistency

| Check | Result |
|-------|--------|
| FR-001..015 original map to code | PASS |
| FR-016..024 completion mission | PASS (code+tests) |
| Dual capabilities named consistently | PASS |
| Forbidden methods listed | PASS |
| Tasks reflect real completion (no false CONVERGED) | PASS |
| Checklist exists | PASS |
| No untreated CRITICAL/HIGH in code path | PASS (as of unit+live selective) |

## Findings

### CRITICAL

*None open in code.* Prior CRITICAL fail-open / outsider-ignore / vacuous tests **fixed in v1.1.0**.

### HIGH

*None open in code.* Residual HIGH are **process**: merge, independent review, acceptance controller, main reproof.

### MEDIUM

1. Live DB has ambiguous CNPJ roots (e.g. `00394494`) → identity_unresolved_count>0 blocks gate (correct).
2. Applicability config status=`draft` — engine consults it; formal ACTIVE promotion is product decision.
3. Presence unmapped rows (matched_entity_id null / cnpj not in universe) are descriptive limitations.

### LOW

1. Transition den/num fields still mirror open_tenders.

## Verdict

**CODE_READY_FOR_REVIEW** — not CONVERGED for mission completion until T020–T036 close.
