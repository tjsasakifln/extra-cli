# `.dod/` — DOD Convergence state

| Path | Tracked? | Purpose |
|------|----------|---------|
| `manifest.yaml` | yes | Executable DOD items + stable IDs |
| `state.json` | yes | Active item / run / phase |
| `log.jsonl` | yes | Append-only events |
| `schemas/` | yes | JSON Schemas |
| `blockers/` | yes | Structured blockers |
| `evidence/` | yes (packs) | Acceptance evidence per item |

Controller: `python3 tools/dod_controller.py`
