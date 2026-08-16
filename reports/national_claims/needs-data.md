# National claims observability

- claim_id: `claim-national-incomplete`
- authorization_state: `NEEDS_DATA`
- consumer_view: `blocked`
- nacional_completo: `False`
- universe: `nu-pncp-contratos-2026-fecfaa9b1842f386`
- expected/attempted/closed: 3/1/1
- freshness: `OK`
- next_action: `consult_unknown_partitions`
- cost_ms: `1.198`

## Reason codes

- `unknown_partitions`
- `national_denominator_incomplete`

## Partitions

- `org-a` FOUND attempted=True reason=None
- `org-b` UNKNOWN attempted=False reason=execution_absent
- `org-sc` UNKNOWN attempted=False reason=not_consulted_this_run

## Identity

- mapped=1 source_wide=0 unmappable=0
- proves_entity_coverage=True

## Diff vs prior

- lkg_status: `absent`
- invalidation_triggers: `[]`
