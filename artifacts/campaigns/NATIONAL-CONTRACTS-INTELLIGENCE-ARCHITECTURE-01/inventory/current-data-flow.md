# Current data flow — PNCP contracts → tables → coverage → deliverables

**Campaign:** NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01  
**Worktree base:** `origin/main` @ `a38981b`  
**As-of inventory:** 2026-07-22  
**Scope:** factual map of code on this worktree. Does not claim live 95% coverage or national completeness.

---

## 1. High-level pipeline

```
PNCP API /consulta/v1/contratos
        │
        ▼
scripts/crawl/contracts_crawler.py
  (modes: full | incremental | backfill_3y)
  FetchResult / WindowResult / crawl_with_evidence
  transform() → dicts (contrato_id, valor_total, dates, …)
        │
        ├─ checkpoints JSON  data/contracts_checkpoints/contracts_{mode}.json
        │
        ▼
monitor.py  OR  run_contracts_90d_pilot.py  OR  ops/run_contracts_pilot.py
        │
        │  UPSERT_FUNCTION = upsert_pncp_supplier_contracts
        ▼
PostgreSQL pncp_supplier_contracts
        │
        ├─ soft keys orgao_cnpj_8 / fornecedor_cnpj_8 → sc_public_entities (no hard FK after 050/055/056)
        │
        ├─ coverage_evidence  (entity × source × capability, state machine)
        │         │
        │         ▼
        │   dual_capability_coverage.py
        │   capability_monitoring_coverage(historical_contracts)
        │   output/coverage/*
        │
        ├─ analytical views (v_contract_*, v_supplier_winners, v_expiring_contracts, …)
        │         │
        │         ▼
        │   contract_intel/cli.py · workspace/cli.py · reports/*
        │
        └─ ops deliverables A–E + package_final · weekly_cycle · golden_path
```

---

## 2. Ingestion layer

### 2.1 Source registration

| Field | Value |
|-------|--------|
| Registry name | `contracts` |
| Module | `scripts/crawl/contracts_crawler.py` |
| Purpose | `contracts` (`is_contract_source=True`) |
| Capabilities | `historical_contracts`, `competitors` |
| Upsert RPC | `upsert_pncp_supplier_contracts` |
| File | `scripts/crawl/registry.py` |

**Invariant in registry/comments:** contracts ≠ bids. Bids go to `pncp_raw_bids` via `upsert_pncp_raw_bids`.

### 2.2 Crawler

| Item | Detail |
|------|--------|
| API base | `CONTRACTS_BASE` default `https://pncp.gov.br/api/consulta/v1` |
| Endpoint | `/contratos` with date windows + pagination |
| Modes | `full` (default 90d), `incremental` (default 3d), `backfill_3y` (default 3 years) |
| Checkpoint modes | `full`, `backfill_3y` → `data/contracts_checkpoints/contracts_{mode}.json` |
| Typed fetch | `FetchStatus`: SUCCESS_DATA, SUCCESS_ZERO, HTTP/connection/parse failures |
| Evidence map | SUCCESS_DATA→`success_with_data`, SUCCESS_ZERO→`success_zero` |
| Transform PK | PNCP `numeroControlePNCP` → `contrato_id` |
| Value field | PNCP `valorGlobal` (etc.) → `valor_total` (semantic CONTRATADO / global, not “preço praticado”) |
| UF rule | Never default to `"SC"` when absent |
| Date semantics | Migration 051: `data_assinatura`, `data_publicacao_fonte`, `source_event_date`, …; legacy `data_publicacao` kept |

### 2.3 Orchestration entry points

| Entry | Role |
|-------|------|
| `python3 -m scripts.crawl.monitor --source contracts --mode full\|incremental\|…` | Canonical multi-source monitor; dispatches upsert via crawler `UPSERT_FUNCTION` |
| `python3 scripts/crawl/run_contracts_90d_pilot.py` | Memory-safe national 90d pilot: per-window fetch/transform/upsert + evidence JSON |
| `python3 -m scripts.ops.run_contracts_pilot` | Thin wrapper around `crawl_with_evidence` / `crawl` + DB count stamp |
| Env knobs | `CONTRACTS_*` (page size, windows, delays, checkpoint dir, `CONTRACTS_PERSIST_EACH_WINDOW`) |

### 2.4 Parallel HC campaign (do not touch)

- HC Closure backfill may run against `extra_test:5433` with checkpoint `hc_closure_3y`.
- Protected paths (this campaign): `data/contracts_checkpoints/hc_closure_*`, `artifacts/campaigns/HISTORICAL-CONTRACTS-*`.
- This worktree/campaign uses isolated DSN `…5435/extra_national_intelligence_test` for schema/experiments only.
- Code for `backfill_3y` **exists on main**; HC-specific checkpoint filenames / campaign artifacts may live only on HC branch or runtime — treat HC process as external concurrent writer.

---

## 3. Persistence layer

| Object | Role |
|--------|------|
| `pncp_supplier_contracts` | Canonical contracts lake (national-capable after FK drops) |
| `upsert_pncp_supplier_contracts(jsonb)` | Idempotent insert by `contrato_id`; migration 051 extends optional date fields + last_seen |
| `contract_version_history` | Optional versioning (trigger disabled by default) |
| `coverage_evidence` | Per-entity/source/capability investigation ledger |
| `entity_coverage` | **Legacy/diagnostic** admin flags (bids-oriented); forbidden as dual coverage method |
| `capability_coverage` | Story 1.2 capability flags (not dual spine) |
| `sc_public_entities` | SC/entity diagnostic + join surface for 200 km analytics |
| `target_universe_*` | Snapshot tables for universe runs (seed remains authority) |
| `ingestion_runs` / checkpoints | Crawl run metadata |

National ingest unblocked by migrations **050 / 055 / 056** (hard FKs to `sc_public_entities` dropped; soft `*_cnpj_8` keys remain).

---

## 4. Coverage measurement layer

| Layer | Authority |
|-------|-----------|
| Universe denominator | `scripts.lib.universe.load_canonical_universe` (seed spreadsheet / fixture) — **not** DB `raio_200km` alone |
| Dual metric | `scripts/coverage/dual_capability_coverage.py` (ADR-030) |
| Caps | `open_tenders` (bids) vs `historical_contracts` (contracts) — **independent** |
| Evidence | Latest `coverage_evidence` per entity×source×capability |
| Applicability | `config/source_applicability.yaml` + optional DB matrix (`source_policy`) |
| Presence | `data_presence(*)` reported separately; **never** labeled as coverage |
| Freshness | SLA open_tenders 24h; historical_contracts 7d; contracts also require ≥3y query window for cover |
| Gate | `GATE_THRESHOLD = 0.95`; `measurement_success ≠ coverage_gate_pass ≠ pipeline_success` |

Golden path (`scripts/golden_path.py`) calls `compute_dual_coverage` for the coverage step.

---

## 5. Intelligence / product layer

### 5.1 Contract intel

- Package: `scripts/contract_intel/` (`cli.py`, `target_universe.py`).
- Commands: `historico`, `fornecedores`, `ativos`, `manifesto`, `stats`, `precos`, `desagio`.
- Views: `v_contract_historical`, `v_supplier_winners`, `v_expiring_contracts`, plus `v_contract_intel_*` (025a/026).
- Scope today: **200 km Florianópolis / seed universe** joins on `sc_public_entities`, not full national analytics product.

### 5.2 Workspace facade (ADR-017)

- `scripts/workspace/cli.py` / `queue.py` query `pncp_supplier_contracts` for contracts, competitors, prices, expiring.
- Comments note real columns `valor_total` (not `valor_global`).

### 5.3 Opportunity intel (adjacent, not contracts lake)

- `opportunity_intel` table + `scripts/opportunity_intel/*` = open tenders / radar / ranking.
- Shares PNCP and entity identity; **does not** replace `pncp_supplier_contracts`.

### 5.4 Ops deliverables (DoD A–E + package)

| Code | Module | Product |
|------|--------|---------|
| A | `scripts/ops/deliverable_a_org_ranking.py` | Org ranking (honest semantics) |
| B | `scripts/ops/deliverable_b_competitors.py` | Competitor winners (≥15 when data allows) |
| C | `scripts/ops/deliverable_c_expiring.py` | Expiring 90–180d |
| D | `scripts/ops/deliverable_d_prices.py` | Price references (comparable groups) |
| E | `scripts/ops/deliverable_e_editais.py` | Open editais recommendations (bids side) |
| Package | `scripts/ops/deliverable_package_final.py` | PDF+Excel same-run package |

Many deliverable paths are **fixture/schema-complete** with live DSN often `INSUFFICIENT` when lake empty for the slice — DoD marks schema gates, not live national product.

### 5.5 Reports & weekly ops

| Module | Role |
|--------|------|
| `scripts/ops/weekly_cycle.py` | Extra weekly pack; reuses lake contracts with freshness stamp (`pncp_contracts`) |
| `scripts/reports/contratos_report.py` | Contracts report |
| `scripts/reports/concorrentes_report.py` | Competitors |
| `scripts/reports/valores_report.py` | Values |
| `scripts/reports/org_ranking.py` / `deliverable_orgaos_ranking.py` | Ranking variants |
| `scripts/reports/panorama.py` | Executive panorama / Excel |
| `scripts/golden_path.py` | End-to-end local cycle including dual coverage + contracts report step |

### 5.6 Other consumers

- `scripts/datalake_helper.py`, `backend/local_datalake.py` — lake access helpers (note: some local_datalake SQL still references alt column names — drift risk).
- `scripts/demo_b2g_setorial.py` — sector market demo from contracts.
- `scripts/integrations/smartlic_snapshot_import.py` — import path into contracts/bids.

---

## 6. Architecture docs (as-is / to-be)

| Doc | Relevance |
|-----|-----------|
| `docs/architecture/b2g-operational-target-architecture.md` | Target C4: adapters → raw → PG → evidence/bids/contracts → workspace → reports |
| `docs/architecture/adr/ADR-030-dual-capability-coverage-truth.md` | Dual coverage spine |
| `docs/architecture/adr/ADR-028-entity-freshness-by-capability.md` | Freshness by capability |
| `docs/architecture/adr/ADR-021-…` | Adapter / 429 fail-closed |
| `docs/architecture/coverage-contract.md` | Multi-metric coverage contract |
| `specs/001-dual-capability-coverage-truth/` | Spec for dual spine |
| `specs/003-national-contracts-intelligence-architecture/spec.md` | **Placeholder** Spec Kit draft (not filled) |

---

## 7. Gaps relevant to national architecture (observed)

1. **Analytics surface is SC/200 km-first** while lake is national-capable.
2. **Column-name drift** across tests, migrations comments (026), and helpers (`valor_global`/`ni_fornecedor` vs `valor_total`/`fornecedor_cnpj`).
3. **Dual coverage 95% for historical_contracts** open in DOD; measurement spine ready.
4. **Deliverables A–D** schema-ready; national productization incomplete.
5. **Concurrent HC backfill** writes same table family on another DSN — isolation required.
6. Spec 003 not yet substantive on this branch.

---

## 8. Key file index (absolute paths)

- `/mnt/d/extra-consultoria-national-intelligence/scripts/crawl/contracts_crawler.py`
- `/mnt/d/extra-consultoria-national-intelligence/scripts/crawl/monitor.py`
- `/mnt/d/extra-consultoria-national-intelligence/scripts/crawl/registry.py`
- `/mnt/d/extra-consultoria-national-intelligence/scripts/crawl/run_contracts_90d_pilot.py`
- `/mnt/d/extra-consultoria-national-intelligence/scripts/coverage/dual_capability_coverage.py`
- `/mnt/d/extra-consultoria-national-intelligence/scripts/coverage/states.py`
- `/mnt/d/extra-consultoria-national-intelligence/scripts/contract_intel/cli.py`
- `/mnt/d/extra-consultoria-national-intelligence/scripts/lib/universe.py`
- `/mnt/d/extra-consultoria-national-intelligence/db/migrations/002_pncp_supplier_contracts.sql`
- `/mnt/d/extra-consultoria-national-intelligence/db/migrations/051_contract_date_semantics.sql`
- `/mnt/d/extra-consultoria-national-intelligence/db/migrations/058_dual_capability_coverage_views.sql`
