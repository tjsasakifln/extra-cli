# Arquitetura — Extra Consultoria

> Re-extração Architect **2026-07-17** | HEAD `d3e82ba`  
> `doc_level`: completo | Delta: 131 commits, +8 módulos, ADRs 017–022

---

## 0. Escopo almejado

> 🟢 O **escopo-alvo** do sistema é o **`DOD.md`** na raiz (checklist viva + 3 róis + gates §35).  
> Esta `architecture.md` descreve a arquitetura **as-is**.  
> Detalhamento do binding e gaps DoD×código: `_reversa_sdd/target-scope-dod.md`.  
> **Não declarar** `LOCAL_READY` / `VPS_OPERATIONAL` / `PROJECT_DONE` / 95% operacional a partir só desta extração.

## 1. Visão geral

Plataforma **CLI-first / single-tenant** de inteligência B2G para consultoria em licitações (foco SC, raio 200 km, universo **1.093** entidades), alinhada à natureza definida no DOD (ferramenta pessoal de Tiago para a Extra Construtora).

| Camada | Responsabilidade | Componentes-chave |
|--------|------------------|-------------------|
| **0. Facade operacional** | Rotina diária do consultor | `workspace` (ADR-017) |
| **1. Ingestão multi-fonte** | Coleta resiliente + atos oficiais | `crawl` + `resilience` + `schema/official_acts` |
| **2. Identidade & matching** | Universo, ESR, reconcile | `lib/universe`, `source_registry`, `matching` |
| **3. Verdade de cobertura** | Dual-metric M1/M2 fail-closed | `coverage/*` (ADR-018) |
| **4. Produto intel** | Radar, ranking, contratos, buyers | `opportunity_intel`, `contract_intel`, `buyer_intel` |
| **5. Pipeline analítico legado** | 7 estágios + LLM | `intel_pipeline` + scripts intel_* |
| **6. Relatórios** | PDF/Excel/amostra comercial | `reports/*` |
| **7. Gates & CI** | Readiness, freshness, coverage, ruff/mypy/pytest | root_scripts + GH Actions |
| **8. Dados** | Postgres + migrations 001–054 | `db/`, docker pgvector:pg16 |
| **9. Ops** | systemd, health, resilient cycle | `deploy/`, `ops/` |

**Stack:** Python 3.12 (~179K LOC) · PostgreSQL 16+pgvector · systemd · pip · GitHub Actions fail-closed  
**Não há** API REST de produto nem UI web de multi-tenant.

---

## 2. Decisões arquiteturais (22 ADRs)

| # | Decisão |
|---|---------|
| 001–011 | Fundação: PG direto, systemd, crawlers HTTP, cascade match, LLM, PDF, migrations, logging, transparência |
| 012 | QW-01 Radar PostgreSQL-only |
| 013 | Coverage Truth evidence ledger |
| 014 | CI gates fail-closed |
| 015 | Value semantics 5 estágios |
| 016 | Competitive intelligence HHI/market share |
| **017** | **Workspace CLI facade** |
| **018** | **Coverage contract multi-metric (M1–M5, den=1093)** |
| **019** | **Entity Source Registry canônico** |
| **020** | **Dados operacionais fora do git** |
| **021** | **Adapter architecture + fail-closed 429/partial** |
| **022** | **Client Profile = única lei comercial** |

---

## 3. Subsistemas (atualizado)

### 3.1 Crawl + Resilience
- 11 fontes no `registry` (SoT)
- `monitor.py` orquestrador vivo; `orchestrator.py` **deprecated**
- Adapters pré-VPS: PNCP, CIGA/DOM, SC Compras + File DLQ/checkpoint/evidence
- Official acts pipeline (DOE/DOM/CKAN) → mig 052

### 3.2 Source Registry + Coverage
- ESR 1093 bindings (mig 053)
- Coverage contract dual-metric; commercial_status; multi_source_coverage
- M2 strict honest: 0/1093 na baseline carimbada

### 3.3 Matching
- Cascade CNPJ → alias → fuzzy
- Reconcile determinístico atos×PNCP (8 regras prioritárias)

### 3.4 Workspace + Extra Ledger + Buyer
- Facade diária; decide/scaffold; buyer AEC ranking

### 3.5 Opportunity / Contract Intel
- Radar, scoring, ranking, target universe

### 3.6 Reports & Gates
- Entregáveis + consulting_readiness / freshness / coverage_gate / golden_path / ci_gate

### 3.7 Database
- 59 migrations; DLQ, watermarks, runs, official_acts, ESR, resilience projections (054)

### 3.8 Deploy
- 25 services / 24 timers; docker test-db; provision VPS

---

## 4. Integrações externas

| Sistema | Protocolo | Papel |
|---------|-----------|-------|
| PNCP | REST | bids/contracts primários |
| Compras.gov | REST | federal |
| SC Compras | HTTP/scrape | estadual fail-closed |
| DOE-SC / DOM-SC / CIGA | scrape/CKAN | atos oficiais |
| TCE-SC / PCP / Transparência / MIDES | scrape/API | cobertura / hybrid |
| OpenAI | HTTPS | intel pipeline legado |
| IBGE | HTTPS | geo cache |
| Postgres / Supabase | SQL/REST | system of record |

---

## 5. Cross-cutting

1. Fail-closed claims (cobertura, GO, zero-ok)  
2. Evidence-bound (`run_id`, content-hash, provenance)  
3. Dual-metric commercial vs operational  
4. ADR-020 path discipline (raw out of git)  
5. Client Profile commercial law  
6. Idempotent upserts + watermarks + DLQ  

---

## 6. Dívidas técnicas (top)

| ID | Dívida | Severidade |
|----|--------|------------|
| TD-A1 | M2 operacional 0/1093 vs meta 95% | 🔴 produto |
| TD-A2 | Scorers legados vs ADR-022 sole law | 🟡 |
| TD-A3 | Duplicação clients/ingestion top-level vs crawl/* | 🟡 |
| TD-A4 | mypy boundary parcial | 🟡 |
| TD-A5 | Sem pip lockfile | 🟡 |
| TD-A6 | Win rate NOT_READY | 🟡 |
| TD-A7 | orchestrator still in tree (deprecated) | 🟢 baixo |

---

## 7. Artefatos relacionados

- `c4-context.md`, `c4-containers.md`, `c4-components.md`  
- `erd-complete.md`  
- `traceability/spec-impact-matrix.md`  
- `domain.md`, `code-analysis.md`  
