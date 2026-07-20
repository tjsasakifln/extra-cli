# Architecture current (as-is) — ARCH-RESET-2026-07-20

Baseline: `d6d9e19` · monorepo Python · local-first · single operator (Tiago).

## One-page diagram (as-is)

```text
┌──────────────────────────────────────────────────────────────────────┐
│ Sources (PNCP, PCP, DOM/DOE, portals…)                               │
└───────────────┬──────────────────────────────────────────────────────┘
                │ collect / crawl / ingestion (many scripts)
                ▼
┌──────────────────────────────────────────────────────────────────────┐
│ PostgreSQL 16  (canonical operational store)                         │
│ raw tables · coverage_evidence · universe 1093 · migrations (62)     │
└───────────────┬──────────────────────────────────────────────────────┘
                │
     ┌──────────┼──────────┬─────────────┬──────────────┐
     ▼          ▼          ▼             ▼              ▼
 coverage*   freshness*  opportunity   workspace      reports/
 multi paths  multi      _intel        CLI facade     PDF/Excel
     │          │          │             │              │
     └──────────┴────┬─────┴─────────────┘              │
                     ▼                                  │
            ┌────────────────────┐                      │
            │ weekly_cycle       │◄── make extra-weekly │
            │ (declared canonical)                      │
            └─────────┬──────────┘                      │
                      │                                 │
                      ▼                                 ▼
            delivery pack (CSV/MD/…)          report-executivo
                                                     │
  Parallel / competing entrypoints:                  │
  golden-path · run-pipeline · resilient_cycle · intel_pipeline
  force-next (ROI campaign) · (PR) decision_pack · (PR) cto autopilot
```

\* Multiple concurrent implementations — see BASELINE.

## Target layering (decision — to implement, not yet true)

```text
collect → raw → normalize → reconcile → quality → intelligence → decision → delivery
```

**Single product command:** `make extra-weekly`  
**Single engineering verify command:** to be named (`make verify`) — **not** a second product pipeline.

## Explicit non-goals (current policy, reaffirmed)

- No Kubernetes / Kafka / Redis-as-required / Airflow / microservices
- No second canonical DB (DuckDB spike-only OK)
- No LLM authority over coverage, freshness, legal status, entity merge, monetary invention
- No auto-merge of PRs

## OCDS

`scripts/ocds_bridge/` maps operational rows → OCDS-inspired fragments for validation/export.  
**Not** the physical PostgreSQL model. Spike PR D will decide ADOPT_AS_REFERENCE / EXPORT_LAYER / REJECT.

## Document precedence (operational)

1. Tiago commercial scope decisions  
2. `DOD.md` (requirements, not proof)  
3. ADRs  
4. Executed tested code  
5. Live evidence  
6. Descriptive docs / agent reports  

## Contradictions to reconcile later (PR docs final)

| Surface A | Surface B | Tension |
|-----------|-----------|---------|
| `canonical-entry-points.yaml` weekly | Makefile `run-pipeline` / `golden-path` look “full” | Multiple narratives |
| ADR-018 one coverage contract | 6 coverage-related modules | Multiplicity |
| Extra-dod-roi force-next | Product weekly cycle | Governance vs product confusion |
| Campaign HTML / CHANGELOG epics | main HEAD claims | Stale “current campaign” language |
| PR #48–51 CTO | Product PRs #52–53 | Agent stack vs consultive pack |

## Fitness functions (planned)

See [`FITNESS-FUNCTIONS.md`](./FITNESS-FUNCTIONS.md). Minimal automated checks; no meta-governance framework.
