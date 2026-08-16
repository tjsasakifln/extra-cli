# National claims observability

- claim_id: `claim-stale-with-lkg`
- authorization_state: `STALE`
- consumer_view: `lkg`
- nacional_completo: `False`
- universe: `nu-pncp-contratos-2026-fecfaa9b1842f386`
- expected/attempted/closed: 3/3/3
- freshness: `STALE`
- next_action: `refresh_complete_run`
- cost_ms: `1.0`

## Reason codes

- `freshness_stale`

## Partitions

- `org-a` FOUND attempted=True reason=None
- `org-b` FOUND attempted=True reason=None
- `org-sc` FOUND attempted=True reason=None

## Identity

- mapped=0 source_wide=0 unmappable=0
- proves_entity_coverage=False

## Diff vs prior

- lkg_status: `valid`
- invalidation_triggers: `[]`
