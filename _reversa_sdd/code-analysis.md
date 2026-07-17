# Análise de Código — Extra Consultoria

> 🟢 **CONFIRMADO** — re-extração Archaeologist 2026-07-17  
> HEAD `d3e82ba` | `doc_level`: completo | 25 módulos  
> Delta vs 2026-07-13: +8 módulos, resilience fail-closed, source_registry, workspace, coverage contract, official_acts

---

## 1. Arquitetura lógica (resumo)

```
                    ┌─────────────────────┐
                    │  Gates / CI / ops   │
                    │ readiness, freshness│
                    │ coverage_contract   │
                    └──────────┬──────────┘
                               │
┌──────────────┐   registry    │    ┌──────────────────┐
│ crawl/*      │◄──SourceInfo──┤    │ source_registry  │
│ + resilience │   11 fontes   │    │ entity→portais   │
│ + ingestion  │───────────────┼───►│ gap / discovery  │
└──────┬───────┘               │    └────────┬─────────┘
       │ upsert / acts         │             │
       ▼                       │             ▼
┌──────────────┐   cascade     │    ┌──────────────────┐
│ matching +   │───────────────┼───►│ coverage/*       │
│ official_acts│               │    │ multi-source     │
│ reconcile    │               │    │ commercial status│
└──────┬───────┘               │    └────────┬─────────┘
       │                       │             │
       ▼                       │             ▼
┌──────────────┐               │    ┌──────────────────┐
│ opportunity  │◄── universe ──┴───►│ workspace /      │
│ intel+radar  │    lib/*           │ buyer_intel      │
└──────┬───────┘                    └────────┬─────────┘
       │                                     │
       └──────────────► reports / root_scripts (PDF, Excel, B2G collectors)
```

**Padrão dominante:** CLI-first, Postgres como sistema de registro, arquivos JSON/JSONL de evidência para sessões e pré-VPS (resilience).

---

## 2. Módulo `crawl` (~40K LOC, 102 .py) 🟢

### 2.1 Propósito
Coleta multi-fonte de licitações/contratos/atos oficiais de SC e fontes federais, com transform → match → upsert → coverage.

### 2.2 Single source of truth — `registry.py`
- `SourceInfo` dataclass expandida (Story 1.5): `name`, `aliases`, `module`, `purpose` (`bids|contracts|coverage_only|hybrid`), `capabilities`, `authority_level`, `entity_types`, `credential_names`, `snapshot_semantics`, `freshness_sla_hours`, `supports_pagination`, `supports_zero_proof`, `reconciliation_strategy`, `is_contract_source`.
- API: `lookup`, `resolve_name`, `iter_sources`, filtros por capability/contracts/public/credential.
- **11 fontes canônicas ativas:**

| name | purpose | module | authority |
|------|---------|--------|-----------|
| pncp | bids | pncp_crawler_adapter | federal |
| ciga_ckan | hybrid | ciga_ckan_crawler | municipal |
| pcp | bids | pcp_crawler | multi |
| compras_gov | bids | compras_gov_crawler | federal |
| sc_compras | bids | sc_compras_crawler | estadual |
| contracts | contracts | contracts_crawler | federal |
| transparencia | bids | transparencia_crawler | municipal |
| tce_sc | bids | tce_sc_crawler | estadual |
| doe_sc | bids | doe_sc_crawler | estadual |
| mides_bigquery | bids | mides_bigquery_crawler | estadual |
| dom_sc | bids | dom_sc_crawler | municipal |

### 2.3 Orquestração
- **`monitor.py`** (1581 LOC): orquestrador vivo; carrega SOURCES do registry; modes full/incremental; `--report-coverage`; DSN fail-loud (sem socket Unix silencioso).
- **`orchestrator.py`**: 🟡 **DEPRECATED** — hardcode de lista antiga; não usar em código novo.

### 2.4 Resilience (NOVO / ADR-021)
Path pré-VPS com filesystem como fonte de verdade:

| Tipo | Papel |
|------|-------|
| `ResilienceConfig` | paths, budgets, env live/fixture |
| `CheckpointStore` / `CanonicalCheckpoint` | retomada de páginas/scopes |
| `RawStore` | raw responses |
| `EvidenceLedger` | evidência machine-sealed |
| `FileDLQ` | dead letter em arquivo |
| `RequestBudget` | orçamento diário de requests |
| Adapters | `PNCPAdapter`, `CigaDomAdapter`, `ScComprasAdapter` |
| `ops/resilient_cycle.run_cycle` | ciclo fixture ou live |

**Algoritmo fail-closed SC:** bulk incompleto / páginas faltantes → status `partial`/`error`, **não** promove sucesso comercial. Chaos tests em `tests/chaos/`.

### 2.5 Pipeline de atos oficiais
- Crawlers DOE/DOM/CIGA + `act_classifier.py`
- Persistência via `scripts/schema/official_acts.OfficialActsStore`
- Reconciliação determinística em `matching/official_acts_reconcile.py`

### 2.6 Cross-cutting crawl
- Checkpoint, watermark, DLQ (DB + file), circuit breaker, rate limiter, provenance, run_evidence (`run_id`, content-hash), parallel mixin PNCP.

### 2.7 Algoritmos-chave
1. **Pipeline source:** crawl → transform → entity match → upsert → coverage update  
2. **Registry resolve:** alias → canonical name  
3. **Resilience adapter:** budget → fetch page → checkpoint → raw persist → evidence  
4. **Zero-proof:** `supports_zero_proof` permite `success_zero` quando fonte confirma vazio  

---

## 3. Módulo `source_registry` (~2.6K LOC) 🟢 NOVO

### Propósito
Mapear as **1093 entidades** do universo 200 km → portais, plataformas, status de acesso, blockers e estratégia de coleta.

### Entidades
- `EntitySourceRecord` — identidade, geo, portais, `integration_type`, `access_status`, `collection_strategy`, `current_blocker`, `priority`, `mapping_confidence`, `evidences`
- `DiscoveryResult` — candidatos de URL/plataforma

### Algoritmos
1. **`build_registry_from_csv`**: seed CSV + YAML transparência + platform detection + residual portals → records  
2. **`_decide_status_and_strategy`**: status/estratégia a partir de evidências  
3. **`discover_sources_for_entity` / `probe_url`**: descoberta ativa de candidatos  
4. **`generate_gap_report`**: classifica blockers e gera MD/JSON de gaps  
5. **`sync_registry_to_postgres`**: projeta em `entity_source_registry`  
6. **`is_strict_operational`**: critério **estrito** de operacionalidade (honest coverage)

### Estados de acesso (CHECK constraint SQL)
`mapped | accessible | collected | verified | operational | failed | blocked | unknown | source_not_identified`

---

## 4. Módulo `workspace` (~2.7K LOC) 🟢 NOVO

### Propósito
Workspace do consultor: fila do dia, seções de atenção, ações (decidir oportunidade, scaffold edital/proposta).

### Componentes
- `queue.build_today` — seções: novas abertas, near deadline, review, source health, expiring, pending profile, suggested actions  
- `actions.decide_opportunity`, `scaffold_edital`, `scaffold_proposal`  
- `common` — DSN, PG soft-fail, ledger/overrides JSON, emit table/json  

### Algoritmo `build_today`
1. Conecta PG (timeout); se offline, degrada seções com dados de sessão JSON  
2. Cada seção retorna `SectionResult`  
3. Prioriza ações sugeridas a partir de seções anteriores  

---

## 5. Módulo `coverage` (~8.4K LOC) 🟢 EXPANDIDO

### 5.1 `coverage_contract.py` (1638 LOC)
Contrato **falível e honesto** de métricas comerciais/operacionais:

| Peça | Papel |
|------|-------|
| `MetricDefinition` / `MetricResult` / `MetricStatus` / `MetricKind` | tipagem de métricas |
| `SLAConfig` | freshness/historical/cadastral windows |
| `resolve_denominator` | denominador canônico (ex.: 1093) |
| `compute_source_mapping_coverage` | mapeamento de fontes |
| `compute_operational_source_coverage` | operacional **strict** |
| `compute_freshness_coverage` | SLA de frescor |
| `compute_opportunity_recall` | recall de oportunidades |
| `compute_required_field_completeness` | campos obrigatórios |
| `compute_commercial_signal` | sinal comercial |
| `build_contract_report` | relatório agregado fail-closed |

**Regra de ouro:** métrica sem evidência → `not_ready` / numerador 0 — **nunca inventa cobertura**.

### 5.2 `states.py` — máquina de estados de cobertura
- `CoverageState` + `CoverageEvidence`
- `is_valid_transition`, `determine_initial_state`, `determine_run_result_state`
- `evaluate_freshness`, `map_monitor_state_to_evidence`
- Estados de evidência satisfatória exigem: success_with_data|success_zero + scope + provenance + pages + sem error (migration 054)

### 5.3 `commercial_status.py`
Classificação comercial auditável (`CommercialClassification`) a partir de evidências reais.

### 5.4 `multi_source_coverage.py` (1664 LOC)
Métricas multi-fonte a partir de artefatos de sessão (CIGA DOM, SC Compras, Dados Abertos, PNCP): municípios com publicação 30d, orgs com licitação recente, reconciliação PNCP, completeness, freshness hours, distribuição de categorias de atos.

### 5.5 Outros
`validate_coverage`, `calculator`, `reconcile_targets`, `run_matching`, `session_coverage_pipeline`, `measure_pncp_expansion`, `sector_engineering`, `blockers`, `manifest`, `recall_benchmark`.

---

## 6. Módulo `matching` (~2.7K LOC) 🟢

### Entity matcher cascade
`match_entities_cascade` — níveis típicos: CNPJ exato → CNPJ8 → aliases → fuzzy (threshold por município/população).

### Official acts reconcile (1819 LOC) — NOVO
Reconciliação **determinística** (sem fuzzy de texto livre) DOE/DOM × Compras SC × PNCP:

| Rule (priority order) | score meta |
|-----------------------|------------|
| pncp_number_exact | 1.0 |
| process_number_orgao_cnpj | 0.95 |
| process_number_year_modalidade | 0.90 |
| contract_number_orgao_cnpj | 0.88 |
| edital_number_year_orgao_cnpj | 0.85 |
| edital_number_year_orgao_name | 0.80 |
| compras_sc_id_crosswalk | 0.92 |
| deterministic_hash | 0.75 |

Ordem de avaliação = `RULE_PRIORITY` (não score-sorted). Divergência valor 1% / R$1; data exact flag.

---

## 7. Módulo `opportunity_intel` (~6.9K LOC) 🟢

| Arquivo | Papel |
|---------|-------|
| `radar.py` | Radar auditável QW-01 |
| `ranking.py` | Competitive intelligence / market share |
| `scoring.py` | `score_opportunity` multi-fator + freshness |
| `status.py` | status canônico a partir de datas/fonte |
| `dedup.py` / `transformer.py` / `reconciliation.py` | pipeline de qualidade |
| `cli.py` / `manifest.py` / `models.py` / `schema.py` | interface e DDL |

**Algoritmo de status:** `infer_status_from_dates` + `compute_canonical_status` → active / terminal / needs_review.

---

## 8. Módulo `lib` (~4.1K LOC) 🟢

| Componente | Papel |
|------------|-------|
| `universe.py` | `CanonicalUniverse` / `CanonicalEntity` — seed 200km + resolução |
| `value_semantics.py` | `ValorSemantica` ESTIMADO/HOMOLOGADO/CONTRATADO/PAGO/GLOBAL + deságio |
| `name_normalizer.py` | normalização de nomes de órgãos |
| `entity_resolver.py` / `entity_hierarchy.py` | resolução e hierarquia |
| `geocode.py` | geocoding + cache IBGE |
| `victory_profile.py` / `win_loss_tracker.py` | perfil de vitória comercial |
| `dedup.py`, `retry.py`, `cli_validation.py`, `cost_estimator.py` | utilitários |

**Regra de valor:** `valor_global` PNCP **não** é preço praticado — é teto/contratado assinado.

---

## 9. Módulo `schema` (~1.8K LOC) 🟢 NOVO

- `OfficialActsStore`: upsert resources/acts/links/classifications/matches  
- `compute_record_hash` para idempotência  
- `diagnostics.py`, `audit_sql_references.py` — integridade de refs SQL no código  

---

## 10. Módulo `ops` (~0.5K LOC) 🟢 NOVO

- `resilient_cycle.run_cycle` — orquestra adapters PNCP/CIGA/SC  
- `health.py`, `schema_audit.py`, `validate_systemd.py`, `run_contracts_pilot.py`  

---

## 11. Módulo `buyer_intel` (~0.7K LOC) 🟢 NOVO

- Classificação AEC por keywords no objeto do contrato  
- `BuyerProfile` multi-fator: volume, ticket, HHI fornecedores, frequência, contratos a vencer  
- Ranking explicável para abordagem comercial  

---

## 12. Módulo `extra_ledger` 🟢 NOVO

CLI de ledger operacional de sessões/evidências (acoplado a docs/ops e workspace).

---

## 13. Módulo `contract_intel` 🟢

- `target_universe.py` — universo-alvo de contratos  
- CLI para exploração de contratos / truth  

---

## 14. Módulo `reports` (~7.9K LOC) 🟢

| Script | Saída |
|--------|-------|
| panorama / executive_report / executive_excel | entregáveis consultoria |
| coverage_weekly / coverage_gaps | cobertura |
| commercial_sample_sc / commercial_b2g_session | amostra comercial honesta |
| org_ranking / deliverable_orgaos_ranking | rankings |
| reconcile_pdf_excel / run_metadata | consistência e metadados de run |

---

## 15. Módulos auxiliares

| Módulo | Resumo |
|--------|--------|
| **fix** | repair: residual portals, rebuild evidence ledger, resolve entities, geocode missing, SC backfill |
| **pipeline** | `backfill_multi_source` — backfill multi-fonte com registry |
| **clients** | clientes HTTP compartilhados top-level |
| **ingestion** | camada de ingestão top-level (paralela a crawl/ingestion) |
| **diagnose** | diagnóstico DOM-SC / plataformas |
| **transparencia** | detecção/utilitários de portais |
| **config** | settings, constants, logging, YAMLs setores/SLA/applicability, CSV 200km |
| **db** | 59 migrations; DLQ, watermarks, official_acts, entity_source_registry, resilience projections |
| **deploy** | 25 services / 24 timers; install/provision/hardening |
| **root_scripts** | gates, intel_*, datalake, health, B2G collectors, golden_path, ci_gate |
| **tests** | unit/integration/smoke/chaos; foco registry, workspace, coverage, resilience |
| **docs** | ops sessions §40–§44, audits, baseline, stories, ADRs |

---

## 16. Algoritmos transversais (catálogo)

| ID | Nome | Local | Confiança |
|----|------|-------|-----------|
| A01 | Multi-source crawl pipeline | crawl/monitor | 🟢 |
| A02 | Source registry resolve | crawl/registry | 🟢 |
| A03 | Resilience fail-closed cycle | crawl/resilience + ops | 🟢 |
| A04 | Entity match cascade | matching/entity_matcher | 🟢 |
| A05 | Official acts deterministic reconcile | matching/official_acts_reconcile | 🟢 |
| A06 | Coverage contract metrics | coverage/coverage_contract | 🟢 |
| A07 | Coverage state machine | coverage/states | 🟢 |
| A08 | Canonical universe 200km | lib/universe | 🟢 |
| A09 | Value semantics / deságio | lib/value_semantics | 🟢 |
| A10 | Opportunity scoring + status | opportunity_intel | 🟢 |
| A11 | Source registry build/gap | source_registry | 🟢 |
| A12 | Workspace today queue | workspace/queue | 🟢 |
| A13 | Buyer AEC ranking | buyer_intel | 🟢 |
| A14 | Commercial classification | coverage/commercial_status | 🟢 |
| A15 | Evidence run_id + content hash | crawl/run_evidence | 🟢 |

---

## 17. Cross-cutting concerns

1. **Fail-closed** — CI, coverage contract, resilience SC bulk  
2. **Evidence-bound claims** — run_id, content-hash, path_proof  
3. **DSN resolution** — DATABASE_URL > LOCAL_DATALAKE_DSN > default test  
4. **Idempotência** — record_hash, upserts, watermarks  
5. **Honest denominators** — 1093 universo; operational strict ≠ commercial headline  
6. **Deprecation hygiene** — orchestrator deprecated  
7. **Observability** — logging_config, metrics, health, systemd on-failure  

---

## 18. Complexidade por módulo

| Módulo | Complexidade | Notas |
|--------|--------------|-------|
| crawl | **alta** | 102 arquivos, multi-fonte, resilience |
| coverage | **alta** | contrato + multi-source + states |
| matching | **alta** | cascade + reconcile determinístico |
| opportunity_intel | **alta** | radar + ranking + scoring |
| source_registry | **média-alta** | build + discovery + gaps |
| workspace | **média** | queue multi-seção |
| reports | **média** | muitos formatos |
| lib | **média** | universe + semantics |
| root_scripts | **alta (agregada)** | superfície CLI larga |
| demais | baixa–média | |

---

## 19. Lacunas 🔴 / Inferências 🟡

| Item | Nível |
|------|-------|
| Clientes Selenium/Playwright opcionais — caminho degradado | 🟡 |
| orchestrator ainda presente no tree | 🟢 (deprecated explícito) |
| scripts/clients vs crawl/clients — possível duplicação histórica | 🟡 |
| Cobertura mypy só em boundary parcial | 🟢 (CI documenta expansão TD-7.1) |
| Volume real de entidades operacionais em produção neste ambiente | 🔴 (requer DB live) |

---

## 20. Artefatos relacionados

- `_reversa_sdd/data-dictionary.md`  
- `_reversa_sdd/flowcharts/*.md`  
- `.reversa/context/modules.json`  
- `_reversa_sdd/inventory.md` (Scout)
