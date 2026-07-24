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

1. Isolation assert (fail on prod/soak DSN/path)
2. Migrations ×2 (idempotent)
3. Targeted pytest + pack run
4. Workspace: today / competitors / expiring-contracts / prices
5. Weekly isolated cycle (exit 0 or 2 with manifest)
6. golden_path on pack DSN
7. run_full_suite on suite DSN :5433 **or** fail-closed CI evidence file (no `|| true`)
8. Monthly live two-cycle FULL_WINDOW
9. Human ACCEPT or terminal BLOCKED_HUMAN

## Risks

| Risk | Mitigation |
|------|------------|
| Restore time | background; tests skip if n<100 |
| Empty sc_public_entities | UF=SC filter as eligible pop; dual coverage not rewritten |
| Sister campaign Makefile lease | integrate after rebase |
| Tiago unavailable | BLOCKED_HUMAN terminal |
| Dual empty on restore | measure 0% honestly; do not claim ≥95% isolado |

## Deviations (current tip evidence)

- Eligible universe in isolated DB uses UF=SC full contracts (1.18M); dual denominator 1093 measured on isolado with **GATE_FAIL_0%** (empty `coverage_evidence`); prior signed live dual paths preserved as non-tip claim.
- Terminal **BLOCKED** / **BLOCKED_HUMAN**: `user-acceptance.decision=null`, `agent_fill_in_forbidden=true`; no fabricated ACCEPT.
- Engineering-filtered B (Extra profile object terms + hospital denylist); 15 construction peers.
- C full window query: `success_zero=false`, n=14750.
- Monthly FULL_WINDOW contracts_c1/c2=57238 labeled (`not_silent_5000_universe=true`).
- Pack generation SHA product tip `fa66dd7`; evidence docs tip may advance without product code delta; package-reconciliation binds same pack `run_id`.
- Full suite: CI proxy when suite DSN :5433 down; assert on `ci-full-suite-pass.json`.
- RC technical complete; merge/DOD `[x]` blocked on human ACCEPT + main CI.
