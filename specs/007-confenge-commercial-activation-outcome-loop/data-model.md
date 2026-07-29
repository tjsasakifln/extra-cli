# Data model — 007

## Source (read-only)

| Table | Role |
|-------|------|
| `pncp_supplier_contracts` | Canonical public contracts history |

Key fields: `fornecedor_cnpj`, `orgao_cnpj`, `objeto_contrato`, `valor_total`, dates, `uf`, `is_active`.

## State (isolated commercial)

| Table | Role |
|-------|------|
| `commercial_leads` | Lead snapshots per run |
| `commercial_lead_runs` | Run metadata |
| `commercial_feedback_ledger` | Append-only events |
| `commercial_lead_state_overrides` | Human state |
| `commercial_exclusions` | Exclusion records |
| `supplier_registry` | Official cadastral rows |

Migrations: `062_commercial_leads_ledger.sql`, `063_supplier_registry.sql`, `064_snapshot_write_guard.sql`.

## Logical entities

- **Supplier (CNPJ14)** — primary commercial unit.
- **SignalResult** — fired / NOT_COMPUTABLE / evidence.
- **LeadScore** — decomposable score + offer + next step.
- **CanonicalCoverage** — single coverage structure (`canonical-coverage-v1`).
- **Dossier** — per Top20 company package.
- **OutreachKit** — Top5 manual messages.
- **Review / Outcome** — append-only transitions.

## Registry resolution statuses

`RESOLVED`, `DEFINITIVELY_NOT_FOUND` (`NOT_FOUND_IN_OFFICIAL_DATASET`), `INVALID_CNPJ`, `SOURCE_ERROR` / `LOOKUP_TRANSIENT_FAILURE`, `PENDING`.
