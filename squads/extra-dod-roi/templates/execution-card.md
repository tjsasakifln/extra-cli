# Execution Card — {{card_id}}

| Field | Value |
|-------|-------|
| cycle_id | {{cycle_id}} |
| created_at | {{created_at}} |
| dod_ref | {{dod_ref}} |
| gate | {{gate}} |
| status | DRAFT \| READY \| IN_PROGRESS \| QA \| DONE \| BLOCKED |

## Problem

{{problem}}

## Evidence of problem

{{evidence}}

## Selected task

{{task_title}}

### Why unlocked

{{why_unlocked}}

### ROI score

- **ROI:** {{roi_score}}
- **Justification:** {{roi_justification}}
- **Dimensions:** {{roi_dimensions}}

## Alternatives discarded

{{alternatives_discarded}}

## Planned files

{{planned_files}}

## Risks

{{risks}}

## Dependencies

{{dependencies}}

## Acceptance criteria

{{acceptance_criteria}}

## Test commands

```bash
{{test_commands}}
```

## Rollback strategy

{{rollback}}

## Claims if PASS

{{allowed_claims}}

## Claims still forbidden

{{forbidden_claims}}

## Agents

| Role | Agent |
|------|-------|
| Implement | @delivery-engineer |
| QA | @adversarial-qa-auditor |
| Release | @evidence-release-steward |
| Orchestrate | @roi-orchestrator |

## Handoff plan

{{handoff_plan}}
