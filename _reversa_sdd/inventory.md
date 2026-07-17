# Inventário do Sistema — Extra Consultoria

> 🟢 **CONFIRMADO** — re-extração Scout em 2026-07-17  
> HEAD: `d3e82ba` | Última extração anterior: 2026-07-13  
> Motivo: atualização completa e profunda pós **131 commits** (754 arquivos, +159.888 / −11.442 LOC)

> **Escopo almejado:** `DOD.md` (raiz) é a definição canônica do que o projeto deve ser. Inventário abaixo = superfície **as-is**. Ver `_reversa_sdd/target-scope-dod.md`.

---

## 1. Visão geral

| Atributo | Valor |
|----------|-------|
| **Projeto** | Extra Consultoria — plataforma B2G / DataLake de compras públicas |
| **Linguagem principal** | Python 3.12 |
| **Arquivos rastreados (git)** | 3.352 |
| **LOC Python** | ~178.915 |
| **Arquivos Python** | 435 |
| **Banco** | PostgreSQL 16 + PostGIS + pgvector (local via Docker; produção VPS) |
| **Orquestração** | systemd timers (25 services / 24 timers) + CLI scripts |
| **CI** | GitHub Actions fail-closed (ruff, mypy, pytest, bandit, pip-audit) |
| **Testes** | 126 arquivos de teste, ~32.473 LOC (unit / integration / smoke / chaos) |

Sistema **batch/CLI-first** de inteligência de licitações e contratos públicos (foco SC, raio 200 km e cobertura multi-fonte), sem frontend de produto. Documentação e AIOX/Reversa convivem no monorepo.

---

## 2. Contagem por linguagem

| Linguagem | Extensões | Arquivos (git) | Observação |
|-----------|-----------|----------------|------------|
| Python | `.py` | 435 | Núcleo de negócio |
| Markdown | `.md` | 1.524 | docs, stories, DoD, AIOX |
| JavaScript | `.js` | 579 | tooling AIOX / vendors |
| JSON | `.json` | 253 | configs, evidências, fixtures |
| YAML | `.yaml`/`.yml` | 173 | setores, CI, configs |
| SQL | `.sql` | 87 | migrations + schema |
| Shell | `.sh` | 23 | deploy, bootstrap, gates |
| TOML | `.toml` | 16 | pyproject, configs |
| CSS / HTML | `.css`/`.html` | 20 | relatórios executivos pontuais |

---

## 3. Módulos identificados (25)

### 3.1 Domínio de aplicação (`scripts/`)

| Módulo | `.py` | LOC (approx) | Papel |
|--------|------:|-------------:|-------|
| **crawl** | 102 | 39.830 | Crawlers multi-fonte, ingestion, resilience fail-closed, DLQ, watermarks, provenance |
| **root_scripts** | 50 | 52.870 | Entry points top-level: gates, intel pipeline, datalake, health, B2G collectors |
| **coverage** | 16 | 8.421 | Contrato de cobertura, multi-source, commercial status, matching, session pipeline |
| **reports** | 12 | 7.938 | PDF/Excel executivo, panorama, commercial sample, coverage weekly/gaps |
| **opportunity_intel** | 18 | 6.864 | Radar QW-01, ranking competitivo, scoring, dedup, CLI |
| **fix** | 7 | 4.236 | Repair: residual portals, evidence ledger, entity resolve, geocode |
| **lib** | 19 | 4.110 | Universe, geocode, name normalizer, value semantics, victory profile |
| **matching** | 4 | 2.700 | Entity matcher cascade + reconcile official_acts |
| **workspace** | 6 | 2.707 | Workspace operacional do consultor (fila, actions, CLI) ✨ **NOVO** |
| **source_registry** | 12 | 2.601 | Registro de fontes por entidade, discovery, gap report, promote ✨ **NOVO** |
| **schema** | 3 | 1.774 | official_acts helpers, diagnostics, audit SQL refs ✨ **NOVO** |
| **contract_intel** | 3 | 1.660 | Universo-alvo e CLI de contratos |
| **ingestion** | 9 | 1.137 | Camada de ingestão top-level (paralela a crawl/ingestion) |
| **clients** | 8 | 1.022 | Clientes HTTP compartilhados |
| **pipeline** | 2 | 876 | Backfill multi-fonte |
| **buyer_intel** | 2 | 695 | Ranking de compradores ✨ **NOVO** |
| **diagnose** | 1 | 651 | Diagnóstico DOM-SC / portais |
| **ops** | 6 | 546 | Health, resilient cycle, schema audit, validate systemd ✨ **NOVO** |
| **extra_ledger** | 1 | 470 | Ledger operacional ✨ **NOVO** |
| **transparencia** | 1 | 406 | Detecção / utilitários de portais de transparência |

### 3.2 Infraestrutura e conhecimento

| Módulo | Conteúdo | Papel |
|--------|----------|-------|
| **config** | `settings.py`, `constants.py`, YAMLs de setores/SLA/aplicabilidade, CSV universo 200 km | Configuração central |
| **db** | 59 migrations em `db/migrations/` (+ 8 supabase) | Schema DataLake |
| **deploy** | 25 services / 24 timers systemd, install, provision, hardening | Operação VPS |
| **tests** | unit / integration / smoke / chaos / fixtures | Qualidade e fail-closed |
| **docs** | ~340 MD em `docs/` (ops, audits, baseline, stories, architecture) | Operação, DoD, ADRs |

---

## 4. Pontos de entrada principais

### 4.1 Orquestração de crawl

| Path | Tipo |
|------|------|
| `scripts/crawl/monitor.py` | Orquestrador monitor multi-fonte |
| `scripts/crawl/orchestrator.py` | Orquestração de pipeline de crawl |
| `scripts/pipeline/backfill_multi_source.py` | Backfill multi-fonte |
| `scripts/ops/resilient_cycle.py` | Ciclo resiliente local (pré-VPS) |

### 4.2 Inteligência e produto B2G

| Path | Tipo |
|------|------|
| `scripts/opportunity_intel/cli.py` | CLI opportunity intel |
| `scripts/opportunity_intel/radar.py` | Radar auditável QW-01 |
| `scripts/contract_intel/cli.py` | CLI contract intel |
| `scripts/buyer_intel/cli.py` | CLI buyer ranking |
| `scripts/source_registry/cli.py` | CLI registry de fontes |
| `scripts/workspace/cli.py` | CLI workspace operacional |
| `scripts/intel_pipeline.py` | Pipeline de inteligência setorial |
| `scripts/local_datalake.py` | DataLake CLI local |

### 4.3 Gates e verdade operacional

| Path | Tipo |
|------|------|
| `scripts/consulting_readiness.py` | Consulting Readiness Gate |
| `scripts/freshness_gate.py` | Freshness / SLA |
| `scripts/coverage_truth.py` | Coverage Truth |
| `scripts/coverage_gate.py` | Coverage gate |
| `scripts/coverage/coverage_contract_cli.py` | Contrato de cobertura |
| `scripts/golden_path.py` | Golden path operacional |
| `scripts/ci_gate.sh` | Gate local espelhando CI |

### 4.4 Relatórios

| Path | Tipo |
|------|------|
| `scripts/reports/panorama.py` | Panorama executivo |
| `scripts/reports/coverage_weekly.py` | Cobertura semanal |
| `scripts/reports/commercial_sample_sc.py` | Amostra comercial SC |
| `scripts/reports/executive_report.py` / `executive_excel.py` | Entregáveis PDF/Excel |

---

## 5. Integrações externas

| Fonte | Tipo | Evidência em código |
|-------|------|---------------------|
| PNCP gov.br | REST API | múltiplos crawlers PNCP + bids/contracts |
| Compras.gov | REST API | `compras_gov_crawler.py` |
| SC Compras | scrape | `sc_compras_crawler.py` + fail-closed resilience |
| TCE-SC | scrape | `tce_sc_crawler.py` |
| DOE-SC | scrape + Selenium | `doe_sc_crawler.py`, `doe_sc_selenium_crawler.py` |
| DOM-SC / CIGA DOM | scrape | `dom_sc_crawler.py`, `ciga_dom_publications.py` |
| CIGA CKAN | CKAN API | `ciga_ckan_crawler.py`, discovery packages |
| Dados Abertos SC | open data | `dados_abertos_sc_crawler.py` |
| MIDES BigQuery | BigQuery | `mides_bigquery_crawler.py` |
| Portais Transparência | multi-template | `transparencia_crawler.py` + betha/egov/ipam/generico |
| PCP | scrape | `pcp_crawler.py` |
| E-Lic SC | stub | `elic_sc_stub.py` |
| IBGE | API + cache | enricher / geocode |
| OpenAI | LLM | `intel_llm_gate.py`, pipeline intel |
| Supabase / Postgres | DB | `supabase_client.py`, DSN env |

---

## 6. Banco de dados (superfície)

| Item | Valor |
|------|------:|
| Migrations `db/migrations/` | **59** (001 → 054 + variantes 041a/b) |
| Migrations Supabase | 8 |
| Dump schema | `supabase/current-schema.sql` |

**Migrations novas desde 2026-07-13 (amostra crítica 030–054):**

- reconciliação de snapshots, capability coverage, versionamento de contratos  
- supplier identity, value observations, reporting views  
- target universe snapshot/active  
- FK fixes, entity aliases, upsert dedup  
- **DLQ**, **pipeline watermarks/runs**, **record hashes**, PNCP resumable backfill  
- **contract date semantics**, **official_acts**, **entity_source_registry**, **local_resilience_contract**

---

## 7. Infra / deploy

| Componente | Detalhe |
|------------|---------|
| Docker Compose | `test-db` — `pgvector/pgvector:pg16` (port 5433) |
| systemd | 25 `.service` + 24 `.timer` em `deploy/systemd/` |
| Fontes agendadas | PNCP full/inc, contracts, CIGA, DOE, DOM, SC Compras, TCE, Transparência, Selenium, métricas, backup, health |
| Provisionamento | `deploy/provision-vps.sh`, `deploy/install.sh`, `deploy/hardening/` |
| Env template | `.env.example` (DATABASE_URL, PNCP_*, INGESTION_*, etc.) |

---

## 8. CI/CD e qualidade

Workflow: `.github/workflows/ci.yml`

| Stage | Ferramenta | Política |
|-------|------------|----------|
| Lint | ruff `scripts/` | fail-closed |
| Type check | mypy (boundary crítica) | fail-closed |
| Test | pytest critical readiness | fail-closed |
| Security | bandit, pip-audit | fail-closed (Regra #10 B2G) |

Dev tools em `pyproject.toml`: ruff (E/F/I/N/S/W/UP), target py312, line-length 120.

---

## 9. Cobertura de testes

| Dimensão | Valor |
|----------|------:|
| Arquivos de teste | 126 |
| LOC testes | ~32.473 |
| Layout | `tests/unit`, `integration`, `smoke`, `chaos`, `fixtures`, `scripts` |
| Focos novos | source_registry, workspace, coverage, resilience/chaos |

---

## 10. Delta vs extração 2026-07-13

| Métrica | 2026-07-13 | 2026-07-17 | Δ |
|---------|------------|------------|---|
| LOC Python | ~137k | ~179k | +~42k |
| `.py` (git) | 277 (surface) | 435 | +158 |
| Módulos Scout | 17 | **25** | +8 |
| Migrations db | ~33 | **59** | +26 |
| Testes | 64 | **126** | +62 |
| systemd services | ~20 | **25** | +5 |

**Novos módulos de domínio:** `source_registry`, `workspace`, `buyer_intel`, `extra_ledger`, `ops`, `schema`, `clients`, `ingestion` (top-level).

**Temas dominantes do delta:**

1. Plataforma B2G operacional (coverage contract, source registry, workspace)  
2. Ingestão real multi-fonte SC (DOE/DOM/Compras) + `official_acts`  
3. Evidence ledger / path proof / sellos de sessão (DoD §40–§44)  
4. Local resilience fail-closed (pré-VPS)  
5. Honestidade de cobertura comercial (0/1093 strict → headlines operacionais auditáveis)

---

## 11. Organização sugerida das specs

- **Granularidade:** `module` 🟢  
- **Razão:** pastas top-level em `scripts/` por domínio funcional; já persistido em `.reversa/config.toml`.  
- **Não alterar** `scout_suggestion` em re-run (RF-14).

---

## 12. Artefatos gerados nesta fase

| Artefato | Path |
|----------|------|
| Inventário | `_reversa_sdd/inventory.md` |
| Dependências | `_reversa_sdd/dependencies.md` |
| Superfície estruturada | `.reversa/context/surface.json` |
