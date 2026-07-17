# Schema audit — NEXT-30D

**Date:** 2026-07-17  
**Command:** `PYTHONPATH=. python3 scripts/ops/schema_audit.py --json output/schema-audit-next30d.json`  
**Exit:** **0** (`ok: true`)

## Results

| Check | Result |
|-------|--------|
| Required relations missing | **[]** (none) |
| Migration SQL files | 54 |
| `_migrations` rows | 53 |
| applied | 41 |
| failed | 12 (mostly “already exists” on non-fresh DB) |
| Warning | files ≠ rows — fresh install re-proof still recommended for GATE-A purity |

## Claims

**Allowed:** Runtime DB has all required relations for NEXT-30D paths; audit tool exit 0.  
**Forbidden:** Claiming clean fresh-install 54/54 on this exact DB without re-running empty DB migrate.
