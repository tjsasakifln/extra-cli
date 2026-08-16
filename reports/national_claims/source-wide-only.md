# National claims observability

- claim_id: `claim-source-wide-only`
- authorization_state: `NEEDS_DATA`
- consumer_view: `blocked`
- nacional_completo: `False`
- universe: `nu-pncp-contratos-2026-fecfaa9b1842f386`
- expected/attempted/closed: 3/0/0
- freshness: `OK`
- next_action: `consult_unknown_partitions`
- cost_ms: `1.0`

## Reason codes

- `source_wide_aggregate_without_identity`
- `aggregated_evidence_not_entity_coverage`
- `unknown_partitions`
- `national_denominator_incomplete`

## Partitions

- `org-a` UNKNOWN attempted=False reason=execution_absent
- `org-b` UNKNOWN attempted=False reason=execution_absent
- `org-sc` UNKNOWN attempted=False reason=execution_absent

## Identity

- mapped=0 source_wide=1 unmappable=0
- proves_entity_coverage=False

## Diff vs prior

- lkg_status: `absent`
- invalidation_triggers: `[]`
