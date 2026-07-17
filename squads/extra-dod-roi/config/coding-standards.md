# Coding standards — extra-dod-roi

Extends project/core standards (`config.extends: extend`).

## Squad-specific

- Task-first: agents dispatch tasks; workers own deterministic parse/score/hash
- Python 3.11+ for squad scripts; stdlib-first (PyYAML optional for weights)
- No absolute paths in manifests
- State writes only under `squads/extra-dod-roi/state/`
- Product tree mutations only via `@delivery-engineer` with execution card
- Never update `DOD.md` checkboxes without adversarial PASS
- Conventional commits when implementing slices
- Prefer relative paths from repo root in docs and scripts
