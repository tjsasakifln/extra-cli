# Collision Matrix — HC Closure vs National Intelligence

| Resource | HC Operational Closure | National Intelligence | Collision risk | Mitigation |
|----------|------------------------|----------------------|----------------|------------|
| Worktree path | `/mnt/d/extra consultoria` | `/mnt/d/extra-consultoria-national-intelligence` | LOW | Separate trees |
| Branch | `campaign/historical-contracts-operational-closure-01` | `campaign/national-contracts-intelligence-architecture-01` | LOW | No shared branch |
| Base commits | d49b103 (+ unmerged HC work) | origin/main a38981b | MEDIUM (code drift) | Feature flags / future integration plan |
| Checkpoint dir | `hc_closure_3y/` | none / own fixtures | CRITICAL if shared | Never write HC checkpoints |
| Artifacts root | `.../HISTORICAL-CONTRACTS-...` | `.../NATIONAL-CONTRACTS-...` | LOW | Separate trees |
| Postgres port | 5433 | 5435 | LOW | Dedicated container |
| Database name | `extra_test` | `extra_national_intelligence_test` | LOW | Distinct DBs |
| Table `pncp_supplier_contracts` | heavy write | fixture/schema only | HIGH if same DB | Isolated DB only |
| Coverage dual scripts | may project after 3y | adversarial tests only | MEDIUM semantic | RF-03 isolation tests |
| `scripts/crawl/*` | live process using them | read-only; no re-run 3y | HIGH if re-exec | Non-goal: no national backfill |
| Migrations | may evolve on HC branch | additive only on isolated DB | MEDIUM | No destructive DDL |
| DOD.md | HC owns operational claims | **must not** mark DOD done | CRITICAL | Non-claim list |
| Host CPU/IO | crawler + postgres 5433 | tests/migrations 5435 | MEDIUM | Light tests; no full scans on 5433 |
| Git push/PR | HC may publish later | draft PR only | LOW | No force-push; no merge auto |

## File ownership for subagents (initial)

| Subagent | Allowed write roots | Forbidden |
|----------|--------------------|-----------|
| A Archaeology | `artifacts/.../inventory/**` | code, HC paths |
| B Data architecture | `artifacts/.../architecture/**`, `artifacts/.../data-model/**`, `specs/003/**/data-model.md` | crawlers, HC paths |
| C Metrology | `artifacts/.../coverage-isolation/**` | production coverage mutation |
| D Market intel | `artifacts/.../products/**` | DB writes to 5433 |
| E Performance | `artifacts/.../performance/**` | infra restart |
| F SQL impl | migrations assigned + `scripts/` assigned paths only after Spec | HC checkpoints |
| G CLI | assigned CLI modules only after Spec | new competing entry without approval |
| H Tests | `tests/**` assigned | weakening thresholds |
| I Review | `artifacts/.../review/**` | implementation files |

## Gate

```text
PARALLEL_ISOLATION_PASS
```

Criteria:

1. [x] Worktree independent and based on origin/main  
2. [x] Active backfill process identified and left running  
3. [x] Protected paths enumerated  
4. [x] Isolated DB on different port/database  
5. [x] Collision matrix documented  
6. [x] No writes performed to HC artifacts/checkpoints  
