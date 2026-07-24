# Plan — 004 Extra Live Consulting Pack

## Architecture

```
authenticated dump (local SHA256)
        │
        ▼
 PostgreSQL isolated :5436 extra_live_pack_rc
        │  migrations …059 coverage + 060 intel views
        ▼
 scripts.ops.live_consulting_pack
   ├─ A org ranking (SQL full pop)
   ├─ B competitors (SQL full pop → select_competitors)
   ├─ C expiring 90–180 (complete window)
   ├─ D price panels (CONTRATADO_GLOBAL)
   ├─ E evidence file (OPEN-TENDERS) 
   └─ PDF + Excel + reconcile
        │
        ├─ scripts.workspace (same DSN)
        └─ strategic_monthly_monitor --live-isolated
```

## PR #121 integration

- Copy `scripts/national_intel/**` as internal engine/alias.
- Renumber `059_national_*` → `060_national_*` (main 059 is coverage).
- Do not merge draft PR; cherry-pick conscious on main tip.
- Spec 003 on PR was national architecture — main 003 is open-tenders; this is **004**.

## Data

- Package: `artifacts/migration/backfill-vps/pkg-20260723T195047Z`
- `pncp_supplier_contracts.dump` ~405MB custom, 4,437,142 rows meta
- SHA256 verified before restore

## Gates

1. Isolation assert
2. Migrations ×2
3. Targeted pytest + pack run
4. Monthly live two-cycle
5. Workspace CLI smoke on DSN

## Risks

| Risk | Mitigation |
|------|------------|
| Restore time | background; tests skip if n<100 |
| Empty sc_public_entities | UF=SC filter as eligible pop; dual coverage not rewritten |
| Sister campaign Makefile lease | integrate after rebase |
| Tiago unavailable | BLOCKED_HUMAN terminal |
