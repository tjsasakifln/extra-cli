# Capability Registry

Source: `scripts/command_center/capabilities/definitions.py`

Each capability declares id, name, category, argv builder, params, risk, confirmation, modules, outputs.

## Initial IDs

- `extra.profile.validate` / `show`
- `extra.weekly.run`
- `extra.actionable.run`
- `extra.decision.review` / `finalize`
- `extra.recurring.run`
- `confenge.suppliers.registry.health|lookup|coverage`
- `confenge.suppliers.cycle.run`
- `confenge.public_agencies.cycle.run` / `review.open`
- `confenge.all.cycle.run` (may be unavailable)
- `process_documents.*`
- `ops.health|source_health|timer_status|soak_status|recent_runs`
- `dod.status|item.show`
- `cc.fixture.echo` (safe CI job)

## Adding a capability

1. Append `Capability(...)` in `definitions.py`.
2. Implement `argv_builder` returning `list[str]` only.
3. Prefer `python -m scripts....` entrypoints.
4. Mark `required_modules` for discovery.
5. Add tests if risk is write/human.
