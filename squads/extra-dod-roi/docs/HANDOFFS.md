# Handoffs — extra-dod-roi

## Protocol

1. Producer fills `templates/handoff.md`
2. Persist to `state/handoffs/{cycle_id}-{from}-to-{to}.md`
3. Consumer reads artifacts paths; re-validates git identity (stale_detect)
4. Do not rely on chat history

## Critical handoffs

| From | To | When |
|------|-----|------|
| cartographer | truth-auditor | snapshot ready |
| truth-auditor | planner | matrix ready |
| planner | delivery-engineer | execution card READY |
| delivery-engineer | adversarial-qa | implementer tests done |
| adversarial-qa | evidence-steward | PASS only for DoD edits |
| orchestrator | planner | point next ROI |
