# ENTITY-FRESHNESS-CANONICAL-ACCEPTANCE-01 — Onda Zero Acceptance Matrix

| Campo | Valor |
|-------|-------|
| **Campaign** | ENTITY-FRESHNESS-CANONICAL-ACCEPTANCE-01 |
| **Base SHA** | `d6d9e1984e348d64a669546613e192e4ebf610cd` (`origin/main`) |
| **Worktree** | `wt-entity-freshness-canonical` |
| **Branch** | `goal/entity-freshness-canonical-acceptance` |
| **DOD item (exact)** | `Freshness coverage mensurável por entidade dentro dos SLAs.` |
| **Seed** | `Extra - alvos de licitação. R-0.xlsx` |

## Product Squad

| Claim | Status |
|-------|--------|
| Exact DOD text only | allowed |
| Dual reports (editais + contracts) measurable per entity | allowed |
| Nominal breaches with entity_id | allowed |
| Deterministic sealed manifest with hashes | allowed |
| Operational coverage ≥95% | **forbidden** |
| Freshness ≥95% | **forbidden** |
| Recall ≥95% | **forbidden** |
| LOCAL_READY / VPS_OPERATIONAL / PROJECT_DONE | **forbidden** |
| Presence-in-DB or MAX(ingested_at) as freshness | **forbidden** |
| len==1093 without set equality | **forbidden** |

## Architecture Squad

| Topic | Decision |
|-------|----------|
| main vs PR #63 | Selective port of classification helpers only; **no wholesale merge** |
| Denominator authority | `scripts.lib.universe.load_canonical_universe` only |
| ADR-020 | Full reports under `output/coverage/` (gitignored); sealed compact evidence in Git |
| Migration 058 | **Out of scope** — not required for this DOD item |
| `entity_source_binding` | **Out of scope** — generation does not depend on it |
| Capabilities | Distinct: `notices_or_bids` vs `contracts` (no cross-promotion) |
| Extra modules/dashboards/agents | **Forbidden** |

## Data Squad

| Rule | Detail |
|------|--------|
| Population | Ordered set of `entity_id` from `load_canonical_universe(seed).included` |
| Identity equality | Report entity_id set **==** included set (not cardinality alone) |
| Registry role | Observations only; must reconcile to canonical entity_id |
| Reconcile keys | CNPJ8 unique; else CNPJ8+name+município disambiguation |
| Fail closed | Unreconciled, duplicate target, missing, extra IDs → error in strict mode |
| Absence | Missing observation → NEVER (not zero, not FRESH) |
| Provenance | FRESH/STALE require entity-scoped timestamp + run_id + content_hash |
| Future timestamp | INCOMPLETE |
| Missing run_id/hash | INCOMPLETE (never FRESH/STALE) |

## QA / DevOps Squad

| Item | Requirement |
|------|-------------|
| Tests | `tests/test_freshness_by_entity.py` mandatory in CI critical job |
| No skip | Fixture-based; must not skip for missing operational files |
| Small wave first | FRESH/STALE/NEVER/INCOMPLETE×3 + capability isolation + dup + non-canonical |
| Full identity | Set equality vs real seed; reject 1092/1094 |
| Operational command | `python -m scripts.coverage.freshness_by_entity --seed ... --registry ... --strict --evidence-manifest ...` |
| Manifest fields | git_sha, seed_*, registry_*, as_of, sla_version, command, exit_code, report hashes, counts, claims |
| Serial closeout | code → tests → CI → op run → manifest → ADR → handoff → **DOD last** |

## Prerequisites

| ID | Description | Status |
|----|-------------|--------|
| P1 | Canonical identity + reconcile fail-closed | in progress |
| P2 | CI mandatory test + sealed op evidence | pending |

## Out of scope (hard stop)

- db/migrations/**, bindings.py, weekly_cycle broad refactor
- PRs #48, #50–#62 wholesale
- Gap reduction / 95% claims / VPS / full suite / agents / dashboards
