# Architecture

```
Browser (127.0.0.1)
    │
    ▼
FastAPI (scripts/command_center)  ── serves SPA dist + /api/*
    │
    ├─ CapabilityRegistry (declarative)
    ├─ JobRunner (subprocess allowlist, shell=False)
    ├─ SQLite store (jobs, audit, decisions)
    └─ Artifact reader (roots allowlist)
            │
            ▼
     existing extra-cli modules / python -m entrypoints
```

## Layout

| Path | Role |
|------|------|
| `apps/command-center/` | React + Vite + TS SPA |
| `scripts/command_center/` | API, registry, runner, security |
| `bin/command-center` | Single-command launcher |
| `data/command_center/` | Local CC state only |

## Principles

1. UI never constructs shell commands.
2. Business logic stays in extra-cli.
3. Missing capabilities degrade with clear messaging.
4. Human decisions require explicit confirmation when sensitive.
