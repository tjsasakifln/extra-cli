# LIVE-SMOKE-REPORT

## Environment

| Check | Result |
|-------|--------|
| `LOCAL_DATALAKE_DSN` | **absent** in implementer shell |
| PostgreSQL `127.0.0.1:5433` | not verified (`psycopg` missing / no DSN) |
| External PNCP/registry live | not exercised |

## Per-capability smoke (Command Center REAL)

| Capability | Attempt | Outcome |
|------------|---------|---------|
| Extra opportunities | REAL preflight | **BLOCKED_CONFIG** (DSN) |
| CONFENGE suppliers | REAL preflight | **BLOCKED_CONFIG** (DSN) |
| CONFENGE public agencies | REAL preflight | **BLOCKED_CONFIG** (DSN) |
| Process documents | REAL preflight | modules importable; may run `show` without DSN — **not claimed LIVE** without operator DSN proof |

## Honesty

- **No fixture substitution** used to claim live success.
- Harness tests prove adapter REAL path with controlled `exec_fn` (`data_mode=REAL`, argv list).
- Terminal for this mission: **PARTIAL_COMMAND_CENTER_REAL_ADAPTERS_NO_LIVE_PROOF** unless operator re-runs with DSN and attaches evidence.

## How to run live smoke when DSN available

```bash
export LOCAL_DATALAKE_DSN='postgresql://…'
python3 -m scripts.command_center  # or bin/command-center
# UI: each flow → data_mode=REAL → confirm → capture run_id + manifest
```
