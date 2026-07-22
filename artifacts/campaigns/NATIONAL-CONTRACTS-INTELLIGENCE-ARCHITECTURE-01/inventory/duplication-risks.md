# Duplication risks — contract_intel, deliverables A–E, opportunity_intel

**Campaign:** NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01  
**Base:** `origin/main` @ `a38981b`

---

## 1. Overlap matrix (product surfaces)

| Concern | contract_intel | deliverable A–D | deliverable E | opportunity_intel | workspace | reports/* | weekly_cycle |
|---------|----------------|-----------------|---------------|-------------------|-----------|-----------|--------------|
| Historical contracts | Yes (views/CLI) | A uses orgs; C expiring | No | No (tenders) | Yes | contratos_report | Yes |
| Competitors / winners | `fornecedores` / v_supplier_winners | **B** | No | Partial (ranking GO on editais) | competitors | concorrentes_report | Yes |
| Expiring 90–180d | `ativos` / views | **C** | No | No | expiring-contracts | — | Yes |
| Price refs / percentiles | `precos`, `desagio`, percentis view | **D** | No | valor_estimado/homologado | prices | valores_report | Partial |
| Org ranking | manifesto readiness | **A** | No | radar ranking | — | org_ranking | — |
| Open editais | No | No | **E** | **Yes (core)** | opportunities | editais_report | Yes |
| Coverage truth | manifesto per-cap | notes only | — | `cli coverage` (OI metric) | coverage cmd | coverage_* | Freshness stamp |
| Dual 95% gates | Not authority | Not authority | Not | Not | Facade | Not | Not |

**Canonical dual coverage authority:** only `scripts/coverage/dual_capability_coverage.py` + `coverage_evidence` (ADR-030).

---

## 2. Parallel “historical contracts” query stacks

| Stack | Location | Join scope | Risk |
|-------|----------|------------|------|
| Views 025a | `v_contract_intel_historico`, fornecedores, ativos_90_180, percentis | `sc_public_entities` LIKE/left cnpj_8 + raio_200km/dist | Multiple similar views |
| Views 026 | `v_contract_historical`, `v_supplier_winners`, `v_expiring_contracts` | raio_200km + 3y window | Overlaps 025a with different filters |
| `v_contracts_canonical` | Migration 030 family | Soft joins + enrichment | Third projection |
| contract_intel CLI | Hardcoded SQL + view names; readiness SQL uses alt column names in places | 200 km | CLI vs views drift |
| workspace SQL | Inline SELECT on `pncp_supplier_contracts` | ad-hoc UF/filters | Duplicates deliverable B/C logic |
| weekly_cycle SQL | Inline contracts + competitors aggregates | weekly pack filters | Fourth copy of “top contracts” |
| reports/* | Separate generators | report-specific | Fifth commercial layer |
| deliverable A–D | Schema/audit + fixture paths | often empty live DSN | Product contract without shared query module |
| backend/local_datalake | SQL with `ni_fornecedor`, `data_assinatura` | mixed | Column-name fork |

**Risk:** same business question (e.g. expiring contracts) answered with different filters (`data_fim` vs `data_fim_vigencia`, 3y cut, raio flag, is_active), yielding irreconcilable numbers in client packs.

---

## 3. Column-name / semantic forks

| Concept | Repo base / crawler / many views | Alt / tests / some helpers / migration 026 **comments** |
|---------|----------------------------------|---------------------------------------------------------|
| Contract PK | `contrato_id` | `numero_controle_pncp` |
| Supplier CNPJ | `fornecedor_cnpj` | `ni_fornecedor` |
| Supplier name | `fornecedor_nome` | `nome_fornecedor` |
| Value | `valor_total` | `valor_global` |
| Start | `data_inicio` | `data_assinatura` (also real 051 column — different semantic!) |
| End | `data_fim` | `data_fim_vigencia` |
| Agency base | `orgao_cnpj_8` generated | `orgao_cnpj8` in readiness SQL snippets |

**Semantic landmine:** after migration 051, `data_assinatura` is a real column meaning signature date; using it as vigencia start conflates dates. `valor_total` maps from PNCP `valorGlobal` — must not be labeled “preço praticado” (domain rule RN-V01 / deliverable D).

---

## 4. contract_intel vs deliverables B/C/D

| Product | contract_intel | deliverable |
|---------|----------------|-------------|
| Competitors | `fornecedores` + HHI view | B: selection rules (top N, min_contracts, deságio guards, no padding) |
| Expiring | `ativos` / v_expiring | C: WindowConfig, termino_tipo CONTRATUAL\|ESTIMADO, relicitacao signals |
| Prices | `precos` / `desagio` | D: comparability dimensions, IQR outliers, value semantics enum |

**Duplication:** two “honest” commercial layers evolved separately. Deliverables emphasize fail-closed schema/audit; contract_intel emphasizes SQL views readiness ≥95%. Neither is yet a single national product API.

**Recommendation direction (inventory only):** one query module per product surface; deliverables call it; CLI wraps it; reports consume same aggregates + run_id.

---

## 5. opportunity_intel vs contracts / editais

| | opportunity_intel | contracts lake |
|--|-------------------|----------------|
| Table | `opportunity_intel` | `pncp_supplier_contracts` |
| Lifecycle | open/upcoming/closed tenders | signed contracts / vigencia |
| Ranking | GO/REVIEW/NO_GO on profile | N/A (historical) |
| Values | estimado / homologado | valor_total (contratado/global) |
| Coverage CLI | OI-specific coverage/source-health | dual `historical_contracts` |

**Risk:** calling OI “coverage” in ops docs confuses dual capability gates.  
**Risk:** deságio between bid estimado and contract valor_total without same-certame match (forbidden domain rule).  
**Overlap:** deliverable E (editais) and OI ranking both recommend open notices — potential dual recommendation engines.

---

## 6. Coverage measurement forks

| Path | Status |
|------|--------|
| dual_capability_coverage | **Canonical** dual gates |
| entity_coverage.is_covered | Legacy / forbidden for gates |
| capability_coverage table | Story 1.2; not dual spine |
| coverage_snapshots | Trend/admin |
| opportunity_intel.cli coverage | Product/source health for OI |
| multi_source_coverage / session pipeline | Supporting ops |
| golden_path legacy metric stamp | `legacy_metric` only |

**Risk:** ops proxies (e.g. “1090/1093 SZ”) accepted as dual 95% without dual engine.

---

## 7. Universe loaders (two modules)

| Module | Role |
|--------|------|
| `scripts/lib/universe.py` | **Canonical** dual / golden path / freshness |
| `scripts/contract_intel/target_universe.py` | Parallel Haversine universe for contract intel |

**Risk:** divergent entity sets if seed parsing differs. New work should depend on `load_canonical_universe` only.

---

## 8. Upsert / import paths into contracts

| Path | Notes |
|------|-------|
| monitor + contracts_crawler | Primary |
| run_contracts_90d_pilot | Batched national pilot |
| ops/run_contracts_pilot | Thin evidence wrapper |
| smartlic_snapshot_import | External snapshot import |
| integrations / backfills | Additional writers |

**Risk:** concurrent writers (HC backfill vs ops pilot) without process locks on same DSN; checkpoint namespace collision if both use `contracts_checkpoints` with different modes.

---

## 9. Report / package multiplicity

- `deliverable_package_final` vs `reports/executive_*` vs `reports/golden_path_pack` vs weekly package  
- Multiple Excel/PDF generators can invent different “contratos no pack” filters  
- Package final insists on same `run_id` — good pattern; not universally enforced on older reports

---

## 10. HC branch / campaign-only artifacts

| Item | Main worktree | HC-only / runtime |
|------|---------------|-------------------|
| contracts_crawler backfill_3y | Present | Used heavily by HC |
| Checkpoint `hc_closure_*` | Must not invent | HC runtime under `data/contracts_checkpoints/` |
| HISTORICAL-CONTRACTS campaign artifacts | Out of scope | Parallel tree |
| Spec 003 body | Placeholder | To be filled by this campaign |
| National analytics product tables | Not present | Future (this campaign) |

---

## 11. Priority collision list (for architects)

1. **Unify contract query semantics** (columns, dates, is_active, 3y window, universe join).  
2. **Single competitor / expiring / price service** feeding B/C/D + workspace + weekly.  
3. **Demote entity_coverage / OI coverage language** away from dual gates.  
4. **One universe loader**.  
5. **Serialize writers** to `pncp_supplier_contracts` on shared DSN (HC vs NI).  
6. **Resolve column drift** in tests and local_datalake before national scale queries.  
7. **Separate open-tender recommendation** (E/OI) from historical contracts products.  
8. **Spec 003** must declare which of the parallel surfaces is SoT for national products.
