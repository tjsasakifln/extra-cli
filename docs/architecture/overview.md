# Architecture overview — Extra Consultoria

**Status:** canônico (pós ARCH-RESET-2026-07-20, sujeito a merge das PRs da campanha)  
**Baseline main inspected:** `d6d9e19`

## One-page target

```text
Sources (PNCP, portals…)
        │ collect
        ▼
 PostgreSQL 16  (operational truth)
        │
        ▼
 normalize → reconcile → quality → intelligence → decision → delivery
        │
        ▼
 make extra-weekly  →  MD + CSV + Excel (+ PDF residual)  · shared run_id
```

**Engineering (not product):** `make verify` (when PR #56 merged) · pytest · ruff · source contracts.

## Canonical product entry

| Class | Command | Module |
|-------|---------|--------|
| **product_canonical** | `make extra-weekly` | `scripts.ops.weekly_cycle` |
| diagnostic | `make golden-path` | `scripts.golden_path` |
| legacy_composite | `make run-pipeline` | Makefile composite |
| campaign_governance | `force-next` | `squads/extra-dod-roi` |

Contract file: `docs/canonical-entry-points.yaml` (v1.1+ when PR #56 lands).

## Non-goals

- Kubernetes / Kafka / Redis-required / Airflow / microservices  
- Second canonical database  
- LLM authority over coverage, freshness, identity, money, legal status  
- Auto-merge of PRs  

## Key ADRs (campaign)

| ADR | Topic |
|-----|--------|
| ADR-023 | Architecture reset campaign charter |
| ADR-024 | OCDS as semantic reference (not physical model) |
| ADR-025 | Canonical Python/SQL quality contract |
| ADR-026 | dbt snapshots rejected for ops core |
| ADR-027 | Keep document parser stack |
| ADR-028 | Deterministic identity first; Splink deferred |
| ADR-029 | Keep openpyxl + ReportLab |

Full index: `docs/architecture/adr/INDEX.md`.

## Campaign evidence root

`docs/ops/campaigns/ARCH-RESET-2026-07-20/`
