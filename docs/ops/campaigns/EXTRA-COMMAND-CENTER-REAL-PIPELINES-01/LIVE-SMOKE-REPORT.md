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


## process_documents REAL smoke (attempted)

Preflight: **READY** (safe_to_run=True)

| Field | Value |
|-------|-------|
| run_id | `aa471c7b-f03a-4618-a417-edfb79c5b54c` |
| status | **FAILED** |
| exit_code | 1 |
| data_mode | REAL |
| command | `/usr/bin/python3 -m scripts.process_documents show demo-processo-001` |
| message | Process documents REAL exit=1; 3 artefatos. |

Honest outcome: pipeline executed REAL without fixture fallback; exit=1 → **FAILED** (no acervo for query demo-processo-001). Evidence saved under implementer scratch live-smoke/.

No auto-outreach occurred.
