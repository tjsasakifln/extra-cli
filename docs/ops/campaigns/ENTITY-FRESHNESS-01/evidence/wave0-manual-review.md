# Wave-0 manual review — ENTITY-FRESHNESS-CANONICAL-ACCEPTANCE-01

| Campo | Valor |
|-------|-------|
| **Date** | 2026-07-20 |
| **Base SHA** | `d6d9e1984e348d64a669546613e192e4ebf610cd` |
| **Reviewer** | campaign executor (serial worktree) |
| **Pytest** | `tests/test_freshness_by_entity.py` — 27 passed |

## Fixture coverage reviewed

| Case | Expected | Observed |
|------|----------|----------|
| FRESH + full provenance | FRESH | FRESH |
| STALE + full provenance | STALE | STALE |
| NEVER (no obs) | NEVER, age_hours=null | NEVER |
| INCOMPLETE missing hash | INCOMPLETE (not STALE) | INCOMPLETE |
| INCOMPLETE missing run_id | INCOMPLETE | INCOMPLETE |
| INCOMPLETE future timestamp | INCOMPLETE | INCOMPLETE |
| Editais-only obs | contracts = NEVER | contracts NEVER |
| Contracts-only obs | editais = NEVER | editais NEVER |
| Duplicate entity_id | fail closed | FreshnessIdentityError |
| Non-canonical entity_id | fail closed | FreshnessIdentityError |

## Stop conditions (all clear)

- [x] No identity divergence on wave0 set
- [x] No unprovenanced FRESH/STALE
- [x] No capability cross-promotion
- [x] No skipped tests

## Escalation decision

**GO** to full 1.093 canonical population (set equality vs `load_canonical_universe().included`).
