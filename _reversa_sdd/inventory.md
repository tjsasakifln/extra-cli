# Inventário do Projeto — Extra Consultoria

> Gerado pelo Scout em 2026-07-13
> Reexecução completa — 30 commits após última análise (2026-07-11)

---

## 1. Visão Geral

| Métrica | Valor |
|---------|-------|
| **Total de arquivos fonte** | 7,474 |
| **Arquivos Python (.py)** | 277 |
| **LOC Python total** | ~137,346 |
| **Arquivos SQL (.sql)** | 58 |
| **Arquivos YAML/YML** | 88 |
| **Shell scripts (.sh)** | 21 |
| **Documentação (.md)** | 289 |
| **Arquivos de teste** | 64 |
| **Linguagem principal** | Python 3.12 |
| **Gerenciador de pacotes** | pip (requirements.txt) |

---

## 2. Estrutura de Diretórios

```
extra-consultoria/
├── scripts/                        # Código-fonte principal (137K LOC)
│   ├── crawl/                      # Crawlers web (51 .py, ~65K LOC)
│   │   ├── clients/                # APIs tipadas (PNCP, base)
│   │   ├── ingestion/              # Pipeline de ingestão (6 .py)
│   │   ├── transparencia_templates/# Templates de portais (7 .py)
│   │   ├── monitor.py              # Orquestrador de crawlers (71K)
│   │   ├── transparencia_crawler.py# Crawler de transparência (57K)
│   │   ├── contracts_crawler.py    # Crawler de contratos (29K)
│   │   ├── ciga_ckan_crawler.py    # Crawler CIGA/CKAN (34K)
│   │   ├── tce_sc_crawler.py       # Crawler TCE-SC (26K)
│   │   ├── doe_sc_crawler.py       # Crawler DOE-SC (28K)
│   │   ├── selenium_crawler.py     # Crawler Selenium genérico (28K)
│   │   └── ...                     # +40 arquivos adicionais
│   ├── opportunity_intel/          # Opportunity Intelligence (16 .py, ~15K LOC)
│   │   ├── cli.py                  # CLI principal (23K)
│   │   ├── radar.py                # QW-01 Radar operacional (33K)
│   │   ├── crawler_base.py         # Base de crawlers (23K)
│   │   ├── transformer.py          # Transformador de dados (18K)
│   │   ├── status.py               # Status/readiness gates (16K)
│   │   ├── pncp_audit.py           # Auditoria PNCP (20K)
│   │   ├── ranking.py              # Competitive intelligence (14K)
│   │   ├── scoring.py              # Scoring de oportunidades (9K)
│   │   ├── models.py               # Modelos SQLAlchemy (8K)
│   │   ├── schema.py               # Schema DDL (5K)
│   │   ├── dedup.py                # Deduplicação (7K)
│   │   ├── backfill.py             # Backfill histórico (14K)
│   │   ├── manifest.py             # Manifestos de cobertura (12K)
│   │   └── profile.py              # Perfis de fornecedor (5K)
│   ├── contract_intel/             # Contract Intelligence (3 .py, ~60K LOC)
│   │   ├── cli.py                  # CLI contratos (47K)
│   │   └── target_universe.py      # Universo-alvo determinístico (12K)
│   ├── lib/                        # Biblioteca compartilhada (15 .py, ~12K LOC)
│   │   ├── universe.py             # CANONICAL_UNIVERSE (14K)
│   │   ├── doc_templates.py        # Templates de documentos (14K)
│   │   ├── entity_hierarchy.py     # Hierarquia de entidades (13K)
│   │   ├── geocode.py              # Geocodificação (12K)
│   │   ├── name_normalizer.py      # Normalização de nomes (10K)
│   │   ├── value_semantics.py      # Semântica de valores (9K)
│   │   ├── victory_profile.py      # Perfil de vitória (12K)
│   │   ├── bid_simulator.py        # Simulador de licitações (12K)
│   │   ├── cost_estimator.py       # Estimador de custos (10K)
│   │   └── ...
│   ├── matching/                   # Entity matching (3 .py, ~28K LOC)
│   │   ├── entity_matcher.py       # Matcher cascade 3 níveis (20K)
│   │   └── measure_baseline.py     # Baseline de acurácia (8K)
│   ├── coverage/                   # Cobertura e validação (4 .py, ~44K LOC)
│   │   ├── validate_coverage.py    # Validador de cobertura (34K)
│   │   ├── calculator.py           # Calculadora de cobertura (5K)
│   │   ├── measure_pncp_expansion.py# Medição de expansão PNCP (4K)
│   │   └── run_matching.py         # Execução de matching (2K)
│   ├── reports/                    # Relatórios (4 .py, ~64K LOC)
│   │   ├── coverage_weekly.py      # Relatório semanal (44K)
│   │   ├── panorama.py             # Panorama (12K)
│   │   └── coverage_gaps.py        # Gaps de cobertura (7K)
│   ├── fix/                        # Scripts de reparo (7 .py, ~165K LOC)
│   │   ├── scrape_residual_portals.py# Scrape residual (51K)
│   │   ├── activate_dormant_sources.py# Ativação de fontes (34K)
│   │   ├── resolve_unresolved_entities.py# Resolução de entidades (16K)
│   │   ├── rebuild_evidence_ledger.py# Reconstrução de ledger (15K)
│   │   ├── sc_dados_abertos_backfill.py# Backfill SC dados abertos (21K)
│   │   └── geocode_missing_entities.py# Geocodificação pendente (13K)
│   ├── pipeline/                   # Pipeline de backfill (2 .py, ~34K LOC)
│   │   └── backfill_multi_source.py# Backfill multi-fonte (34K)
│   ├── diagnose/                   # Diagnóstico (1 .py, ~25K LOC)
│   │   └── dom_sc_diagnostic.py    # Diagnóstico DOM-SC (25K)
│   ├── transparencia/              # Detecção de portais (1 .py, ~14K LOC)
│   │   └── run_detect_all.py       # Detector automático (14K)
│   ├── [root scripts]              # ~40 scripts CLI top-level (~500K+ LOC)
│   │   ├── intel_pipeline.py       # Pipeline de inteligência (50K)
│   │   ├── intel_collect.py        # Coleta de inteligência (138K)
│   │   ├── intel_analyze.py        # Análise de inteligência (71K)
│   │   ├── intel_report.py         # Relatório de inteligência (99K)
│   │   ├── consulting_readiness.py # Readiness gate (88K)
│   │   ├── coverage_truth.py       # Coverage truth (39K)
│   │   ├── freshness_gate.py       # Freshness gate (10K)
│   │   ├── generate_consultoria_pdf.py# PDF consultoria (66K)
│   │   ├── generate_report_b2g.py  # Relatório B2G (287K)
│   │   ├── local_datalake.py       # CLI DataLake (26K)
│   │   └── ...
├── config/                         # Configuração
│   ├── settings.py                 # Settings centralizados
│   ├── constants.py                # Constantes
│   ├── sectors_config.yaml         # Config de setores B2G (61K)
│   ├── sectors_data.yaml           # Dados setoriais (177K)
│   ├── transparencia_config.yaml   # Config de transparência (19K)
│   ├── municipio_population.yaml   # População por município
│   ├── abbreviations.yaml          # Abreviações
│   └── client_profiles/            # Perfis de cliente
├── db/                             # Database
│   ├── migrations/                 # 33 migrations SQL
│   ├── rollback/                   # Rollback scripts
│   ├── seed/                       # Seed data
│   └── setup_db.sh                 # Setup script
├── supabase/                       # Supabase
│   ├── migrations/                 # 8 migrations versionadas
│   └── docs/                       # Documentação do schema
├── deploy/                         # Deploy
│   ├── systemd/                    # 20 pares service+timer
│   ├── hardening/                  # Hardening scripts
│   ├── install.sh                  # Instalação
│   └── provision-vps.sh            # Provisionamento VPS
├── tests/                          # 64 arquivos de teste
│   ├── fixtures/                   # Fixtures
│   ├── smoke/                      # Smoke tests
│   └── scripts/                    # Scripts auxiliares
├── docs/                           # 590 arquivos de documentação
│   ├── architecture/               # Arquitetura
│   ├── stories/                    # Stories de desenvolvimento
│   │   └── epics/                  # 7 epics
│   ├── prd/                        # PRDs
│   ├── decisions/                  # ADRs
│   ├── coverage-truth/             # Coverage truth docs
│   ├── ops/                        # Runbooks operacionais
│   ├── qa/                         # QA gates e reports
│   └── ...
├── data/                           # Dados locais (51 arquivos)
│   ├── intel/                      # Dados de inteligência
│   ├── reports/                    # Relatórios
│   ├── dumps/                      # Dumps
│   └── contracts_checkpoints/      # Checkpoints
├── output/                         # Outputs (25 arquivos)
│   ├── pdfs/                       # PDFs gerados
│   ├── excels/                     # Excels gerados
│   ├── logs/                       # Logs
│   ├── qw-01/                      # QW-01 radar runs
│   ├── readiness/                  # Readiness reports
│   └── reports/                    # Relatórios
├── pipeline/                       # Estado de pipelines
├── plan/                           # Planos e checklists DoD
├── .github/workflows/ci.yml        # CI/CD (GitHub Actions)
├── docker-compose.yml              # PostgreSQL para testes
├── requirements.txt                # Dependências Python
├── pyproject.toml                  # Config ruff + mypy + bandit
└── .env.example                    # Template de variáveis
```

---

## 3. Entry Points (CLI)

O sistema é **CLI-first** (Artigo I da Constitution AIOX). Entry points principais:

| Entry Point | Tipo | Descrição |
|-------------|------|-----------|
| `scripts/crawl/monitor.py` | Orquestrador | Crawl completo/incremental PNCP + todas as fontes |
| `scripts/opportunity_intel/cli.py` | CLI | Opportunity Intelligence (list, show, explain, update, export) |
| `scripts/opportunity_intel/radar.py` | Radar | QW-01 Auditable Opportunity Radar |
| `scripts/contract_intel/cli.py` | CLI | Contract Intelligence (consult, export, stats) |
| `scripts/intel_pipeline.py` | Pipeline | Pipeline de inteligência para 1 CNPJ |
| `scripts/local_datalake.py` | CLI | DataLake local (search, supplier, stats) |
| `scripts/coverage_truth.py` | Análise | Coverage truth assessment |
| `scripts/consulting_readiness.py` | Gate | Consulting Readiness Gate |
| `scripts/freshness_gate.py` | Gate | Freshness Gate SLA check |
| `scripts/reports/panorama.py` | Relatório | Panorama setorial |
| `scripts/reports/coverage_weekly.py` | Relatório | Relatório semanal de cobertura |
| `scripts/pipeline/backfill_multi_source.py` | Pipeline | Backfill multi-fonte |

---

## 4. Banco de Dados (Superficial)

| Componente | Descrição |
|------------|-----------|
| **SGDB** | PostgreSQL 16 + PostGIS |
| **Migrations** | 33 SQL files em `db/migrations/` |
| **Supabase** | 8 migrations versionadas em `supabase/migrations/` |
| **Schema atual** | `supabase/current-schema.sql` (25K) |
| **Seed** | `db/seed/` |
| **Índices** | GIN, HNSW, B-tree (conforme migrations) |
| **Funções** | RPCs: search_datalake, upsert, purge, coverage |
| **Modelos** | `scripts/opportunity_intel/models.py` (SQLAlchemy) |

---

## 5. Cobertura de Testes

| Métrica | Valor |
|---------|-------|
| **Framework** | pytest |
| **Total de arquivos** | 64 |
| **Tipos** | Unitários, integração, smoke, E2E externo |
| **Banco de testes** | PostgreSQL via docker-compose (`TEST_DSN`) |
| **Marcadores** | `unit`, `integration`, `smoke`, `external` |
| **CI** | GitHub Actions (`ci.yml`) |
| **Cobertura** | pytest-cov disponível |

---

## 6. CI/CD

| Componente | Path |
|------------|------|
| **CI** | `.github/workflows/ci.yml` (7KB) |
| **Lint** | ruff (config em `pyproject.toml`) |
| **Type check** | mypy (strict config em `pyproject.toml`) |
| **Security** | bandit (config em `pyproject.toml`) |
| **Pre-commit** | `/quality-gate` + `/code-review` via AIOX |

---

## 7. Deploy (VPS)

- **Orquestrador:** systemd (20 pares service+timer)
- **Provisionamento:** `deploy/provision-vps.sh`
- **Hardening:** `deploy/hardening/`
- **Backup:** `scripts/backup-database.sh` (systemd timer)
- **Monitoramento:** health-check, check-alerts, collect-metrics (todos systemd)

---

## 8. Módulos Identificados

| # | Módulo | Path | .py | Função |
|---|--------|------|-----|--------|
| 1 | **crawl** | `scripts/crawl/` | 51 | Crawlers web, ingestão, monitoramento |
| 2 | **opportunity_intel** | `scripts/opportunity_intel/` | 16 | Licitações abertas, QW-01 Radar, ranking |
| 3 | **lib** | `scripts/lib/` | 15 | Biblioteca compartilhada (universe, geocode, matching utils) |
| 4 | **contract_intel** | `scripts/contract_intel/` | 3 | Contract Intelligence, universo-alvo |
| 5 | **matching** | `scripts/matching/` | 3 | Entity matching cascade 3 níveis |
| 6 | **coverage** | `scripts/coverage/` | 4 | Cálculo e validação de cobertura |
| 7 | **reports** | `scripts/reports/` | 4 | Relatórios PDF/Excel executivos |
| 8 | **fix** | `scripts/fix/` | 7 | Scripts de reparo/backfill de dados |
| 9 | **pipeline** | `scripts/pipeline/` | 2 | Pipeline de backfill multi-fonte |
| 10 | **diagnose** | `scripts/diagnose/` | 1 | Diagnóstico de crawlers |
| 11 | **transparencia** | `scripts/transparencia/` | 1 | Detecção automática de portais |
| 12 | **config** | `config/` | 3 | Configuração centralizada (settings, constants) |
| 13 | **db** | `db/` + `supabase/` | — | 33 + 8 migrations SQL, schema |
| 14 | **deploy** | `deploy/` | — | 20 systemd timers, provisionamento |
| 15 | **tests** | `tests/` | 64 | Testes automatizados |
| 16 | **docs** | `docs/` | — | 590 arquivos de documentação |
| 17 | **root_scripts** | `scripts/*.py` | ~40 | Entry points CLI, pipelines, relatórios |

---

## 9. Novos Módulos (vs. última execução em 2026-07-11)

| Módulo | Descrição | Commits relacionados |
|--------|-----------|---------------------|
| QW-01 Radar | `opportunity_intel/radar.py` (33K) | `249340d`, `ce55095` |
| Competitive Intel | `opportunity_intel/ranking.py` (14K) | `77265b5` |
| Readiness Gates | `consulting_readiness.py` (88K), `freshness_gate.py` (10K) | `0fef9de`, `3eeb4d6`, `15177dc` |
| Contract Intel V1 | `contract_intel/` (3 arquivos) | `86fc886`, `2ee6f4f` |
| Coverage Truth | `coverage_truth.py` (39K), `scripts/coverage/` | `1195495`, `824af88` |
| Evidence Ledger | `db/migrations/024_coverage_evidence_ledger.sql` | `0ee490b` |
| Opportunity Schema | `db/migrations/027_opportunity_intel.sql` | `7454a0f` |
