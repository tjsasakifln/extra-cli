# O golden path aplica seed

## Given/When/Then
- Given reachable DSN and migrations applied
- When golden path runs without --skip-seeds
- Then db/seed/001_sc_entities.py and 002_entity_aliases.py execute with exit 0
- And re-run remains non-failing (idempotent seeds)

## Evidence
- Unit test_apply_seeds_runs_seed_scripts
- Live dual apply_seeds on PG16:5544
