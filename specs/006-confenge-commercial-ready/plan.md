# Plan 006 — CONFENGE Commercial Ready

## Architecture

```
config/commercial_profiles/confenge.yaml  +  signal_catalog.yaml
                 │
                 ▼
     scripts/commercial_leads/*  (profile, signals, scoring, identity, snapshot, isolation)
                 │
                 ▼
     pipeline.run_pipeline()  ──read──►  STATE DSN (pncp_supplier_contracts + commercial_* tables)
                 │
                 ├── exports (JSON/CSV/MD/HTML)
                 ├── commercial_lead_runs / commercial_leads
                 └── feedback / overrides ledger
                 │
                 ▼
     workspace CLI + make confenge-commercial-cycle
```

## Source / state separation

| Role | Env | Rules |
|------|-----|-------|
| STATE | `CONFENGE_COMMERCIAL_STATE_DSN` | Isolated local port (5441/5433…); migrations 062; writes only commercial_* |
| SOURCE | `CONFENGE_COMMERCIAL_SOURCE_DSN` | Read-only intent; contracts restored into STATE for this campaign |

Production hosts (`ec-prod`, port 5432, non-local) are rejected by `isolation.assert_isolation`.

## Migrations

- `062_commercial_leads_ledger.sql` — additive commercial runs/leads/overrides/feedback/exclusions.
- Does not alter PNCP write path or soak tables.

## Modules

| Module | Responsibility |
|--------|----------------|
| `profile.py` | Load/hash profile + catalog |
| `signals.py` | ≥12 deterministic signals + NOT_COMPUTABLE |
| `scoring.py` | Decomposable score + rank |
| `identity.py` | CNPJ14 resolution + exclusions |
| `snapshot.py` | Authenticated snapshot manifest |
| `isolation.py` | Fail-closed production/soak guard |
| `pipeline.py` | End-to-end run |
| `review.py` | States, import/export reviews |
| `exports.py` | Open artifacts |
| `ops/confenge_commercial_cycle.py` | Canonical cycle |
| `ops/verify_soak_non_interference.py` | Soak guard |

## Integration

- Workspace: `commercial-leads`, `commercial-lead`, `commercial-review`.
- Makefile targets as in campaign mandate.
- Extra weekly cycle untouched.

## Soak protection

- Capture soak-baseline before campaign mutations on VPS.
- Final compare via `make verify-soak-non-interference`.
- Never restart/disable soak units.

## Rollout / rollback

1. Merge after CI green + gates.
2. Timer comercial (if any) stays disabled until gates + non-interference.
3. Rollback: drop commercial_* tables or revert migration 062; restore profile previous version.

## Reuse decision

Foundation adapted from uncommitted work on `campaign/confenge-commercial-queue-operational-01` (same base SHA), re-homed to campaign ID `CONFENGE-COMMERCIAL-READY-01` and `specs/006-*` without reusing that branch as main.
