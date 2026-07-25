# Client-ready recurring consulting cycle

Technical orchestration that composes national intel (migration 060) and
canonical linkage (migration 061) into commercial deliverables A–E.

## Separation of concerns

| Layer | Meaning |
|-------|---------|
| Technical readiness | Code + CI green; pack can be generated offline |
| Package publication | Fail-closed publish path (`publish_commercial_rc_v2`) |
| Human acceptance | **Only Tiago** may set `user-acceptance.json` to ACCEPTED |

Agents must never forge human acceptance.

## Operator entry

```bash
python -m scripts.ops.client_ready_consulting_cycle --help
```

Heavy outputs: generate locally / CI artifacts — do not commit PDF/XLSX dumps.
