# System Architecture — Extra Consultoria

> **Gerado em:** 2026-07-13
> **Propósito:** Brownfield Discovery — Fase 1: Documentacao do Sistema (Refinamento)
> **Autor:** Aria (Visionary Architect)
> **Versão:** v2.0 (atualizacao pos QW-01, Contract Intel, Opportunity Intel)

---

## 1. Executive Summary

A Extra Consultoria e uma plataforma CLI de inteligencia em licitacoes publicas, single-client (Extra Construtora), operada pelo consultor Tiago Sasaki. O sistema e uma maquina de crawling multi-source que monitora 2.085 orgaos publicos de Santa Catarina em 12+ fontes de dados abertos, combinando ingestao continua (systemd timers) com pipelines de inteligencia sob demanda (CLI).

**Cobertura funcional atual (Julho/2026):**
- 12 fontes de dados cadastradas (registry centralizado)
- 29 migrations SQL (4.273 linhas) — schema maduro com coverage evidence ledger
- ~61 arquivos de teste (pytest) com fixtures de banco real (PostgreSQL containerizado)
- 3 subsistemas de inteligencia: Opportunity Intel (QW-01), Contract Intel (Truth V1), Intel-Busca Pipeline
- 44 services/timers systemd para automacao de crawl
- ~117.099 linhas Python + SQL

**Arquitetura:** DataLake PostgreSQL centralizado rodando em Hetzner VPS, com crawlers Python async/await que coletam, transformam e fazem upsert de dados de licitacoes publicas. Tres pipelines de inteligencia independentes operam sobre o DataLake: Intel-Busca (sob demanda), Opportunity Intel (radar QW-01 agendado), Contract Intel (consultas analiticas).

---

## 2. Technology Stack

| Camada | Tecnologia | Versao | Justificativa |
|--------|-----------|--------|---------------|
| Linguagem | Python | 3.12 | Ecossistema rico para crawling e LLM |
| Database | PostgreSQL 17 + PostGIS | 17 / 3.4 | Single-user, pg_trgm fuzzy, PostGIS geo |
| HTTP Async | httpx | >=0.28.1 | Async nativo para crawl concorrente |
| LLM Classificacao | OpenAI GPT-4.1-nano | - | Custo baixo, qualidade suficiente |
| PDF Generation | ReportLab | >=4.5.1 | Relatorios estilo Big Four |
| Excel Generation | openpyxl | >=3.1.5 | Planilhas de analise |
| CLI Output | rich | >=13.0.0 | Tabelas e paineis no terminal |
| HTML Parsing | lxml + beautifulsoup4 | >=5.0.0 / >=4.12.0 | Crawling de portais |
| Fuzzy Matching | rapidfuzz | >=3.0.0 | Entity matching 3-level cascade |
| Database Driver | psycopg2-binary | >=2.9.9 | Driver PostgreSQL nativo |
| Config | python-dotenv + PyYAML | >=1.0.0 / >=6.0 | 12-factor app |
| Scheduler | systemd timers | Nativo Linux | Zero dependencia externa |
| Pre-commit | ruff + mypy + bandit | v0.9.5 / v1.13.0 / v1.8.0 | Quality gates pre-commit |
| Test DB | PostgreSQL + PostGIS (Docker) | 16-3.4 | Container temporario para integration tests |
| Deploy | Hetzner VPS + Ubuntu | 24.04 | Cloud host dedicado |

---

## 3. Project Structure

```
/mnt/d/extra consultoria/
├── config/                              # Configuracoes centralizadas
│   ├── settings.py                      # Env vars loading (DSN, APIs, crawlers, etc.)
│   ├── constants.py                     # Constantes de dominio
│   ├── logging_config.py               # Logging estruturado (JSON)
│   ├── sectors_config.yaml             # 14 setores com CNAEs, heuristicas (61149 bytes)
│   ├── sectors_data.yaml               # Dados complementares por setor
│   ├── transparencia_config.yaml       # Config portal da transparencia (19432 bytes)
│   ├── abbreviations.yaml              # Abreviacoes para normalizacao textual
│   ├── municipio_population.yaml       # Populacao dos municipios
│   ├── transparencia_config.yaml.bak   # Backup de config anterior
│   ├── mides-bigquery-sa.json          # Service account (gitignored?)
│   └── client_profiles/                # Perfis de cliente
│       └── extra.yaml                  # Perfil Extra Construtora
│
├── scripts/                             # Codigo fonte Python (~117k linhas)
│   ├── crawl/                          # SUBSISTEMA 1: Crawl Multi-Source
│   │   ├── monitor.py                  # ORQUESTRADOR PRINCIPAL (CLI + systemd)
│   │   ├── registry.py                 # Registro centralizado de fontes (SourceInfo)
│   │   ├── orchestrator.py            # Orquestrador antigo (pre-registry)
│   │   ├── pncp_crawler_adapter.py     # PNCP API adapter (sync)
│   │   ├── dom_sc_crawler.py           # DOM-SC Portal crawler
│   │   ├── pcp_crawler.py              # PCP v2 API crawler
│   │   ├── compras_gov_crawler.py      # ComprasGov v3 API crawler
│   │   ├── sc_compras_crawler.py       # SC Compras crawler
│   │   ├── tce_sc_crawler.py           # TCE-SC SCMWeb crawler
│   │   ├── doe_sc_crawler.py           # DOE-SC crawler (requer login)
│   │   ├── contracts_crawler.py        # Contratos PNCP crawler
│   │   ├── transparencia_crawler.py    # Portal Transparencia crawler
│   │   ├── ciga_ckan_crawler.py        # CIGA CKAN (coverage assessment)
│   │   ├── mides_bigquery_crawler.py   # MIDES BigQuery crawler (PULADO)
│   │   ├── selenium_crawler_adapter.py # Selenium batch crawler adapter
│   │   ├── doe_sc_selenium_crawler.py  # DOE-SC com Selenium
│   │   ├── selenium_crawler.py         # Selenium base crawler
│   │   ├── bids_crawler.py             # BidsCrawler class (legacy, imports quebrados)
│   │   ├── pncp_arp_crawler.py         # Atas de Registro de Precos
│   │   ├── pncp_pca_crawler.py         # Planos de Contratacoes Anuais
│   │   ├── pncp_engineering.py         # Classificador de engenharia
│   │   ├── pncp_geo.py                 # Resolvedor geografico (200km Fpolis)
│   │   ├── pncp_contract.py            # Parse de target para oportunidades
│   │   ├── enricher.py                 # Enriquecimento (BrasilAPI, IBGE)
│   │   ├── transformer.py              # Transform raw API -> unified schema
│   │   ├── loader.py                   # Upsert via RPC
│   │   ├── adapter.py                  # PNCPLegacyAdapter
│   │   ├── checkpoint.py               # Checkpoints resumable
│   │   ├── circuit_breaker.py          # Circuit breaker pattern
│   │   ├── retry.py                    # Retry com exponential backoff
│   │   ├── rate_limiter.py             # Rate limiter HTTP
│   │   ├── credentials_validator.py    # Validador de credenciais por source
│   │   ├── degradation.py              # Degradacao gradual
│   │   ├── middleware.py               # Middleware HTTP
│   │   ├── metrics.py                  # Metricas de crawl
│   │   ├── security.py                 # Security helpers
│   │   ├── sanctions.py                # Checagem de sancionados
│   │   ├── common.py                   # Funcoes comuns compartilhadas
│   │   ├── exceptions.py               # Excecoes tipadas
│   │   ├── redis_pool.py               # Pool Redis (opcional)
│   │   ├── supabase_client.py          # Supabase client (legacy)
│   │   ├── async_client.py             # HTTP async client
│   │   ├── sync_client.py              # HTTP sync client fallback
│   │   ├── playwright_fallback.py      # Playwright fallback (JS rendering)
│   │   ├── selenium_smoke_test.py      # Smoke test Selenium
│   │   ├── batch_detect_platforms.py   # Deteccao batch de plataformas
│   │   ├── batch_detect_platforms_pass2.py
│   │   ├── generate_transparencia_config.py
│   │   ├── _parallel_mixin.py          # Mixin paralelo (MRO)
│   │   ├── ingestion/                  # Subpackage de ingestao
│   │   │   ├── _base/
│   │   │   │   ├── crawler.py          # CrawlerResult, CrawlRequest, Protocol
│   │   │   │   └── __init__.py
│   │   │   ├── __init__.py
│   │   │   ├── config.py               # Config especifica de ingestao
│   │   │   ├── checkpoint.py           # Checkpoint de ingestao
│   │   │   ├── loader.py               # Loader de ingestao
│   │   │   ├── metrics.py              # Metricas de ingestao
│   │   │   └── transformer.py          # STUB: Ingestion transformer
│   │   ├── clients/                    # Clientes HTTP especializados
│   │   │   ├── base/base.py            # Base HTTP client
│   │   │   └── pncp/                   # Cliente PNCP async
│   │   │       ├── async_client.py
│   │   │       ├── _parallel_mixin.py
│   │   │       ├── circuit_breaker.py
│   │   │       └── retry.py
│   │   └── transparencia_templates/    # Templates de portal
│   │       ├── base.py, betha.py, egov.py, generico.py
│   │       ├── ipam.py, selenium_base.py
│   │
│   ├── opportunity_intel/              # SUBSISTEMA 2: Opportunity Intelligence
│   │   ├── cli.py                      # CLI principal (list, show, explain, update)
│   │   ├── radar.py                    # QW-01 Auditable Radar (PostgreSQL-only)
│   │   ├── pncp_crawler.py             # PNCP Opportunity Crawler
│   │   ├── pncp_audit.py              # PNCP Audit (monitoring threshold)
│   │   ├── crawler_base.py             # CrawlRequest base class
│   │   ├── models.py                   # Modelos de dados
│   │   ├── schema.py                   # Schema validation (fingerprint, git identity)
│   │   ├── scoring.py                  # RadarScores, score_opportunity
│   │   ├── ranking.py                  # Ranking de oportunidades
│   │   ├── profile.py                  # ClientProfile loader
│   │   ├── dedup.py                    # Deduplicacao
│   │   ├── transformer.py              # Transform para opportunity_intel
│   │   ├── manifest.py                 # Manifestos de cobertura
│   │   ├── backfill.py                 # Backfill de oportunidades
│   │   └── status.py                   # Status tracking
│   │
│   ├── contract_intel/                 # SUBSISTEMA 3: Contract Intelligence
│   │   ├── cli.py                      # CLI (historical_contracts, competitor_winners, etc.)
│   │   └── target_universe.py          # Target universe 200km
│   │
│   ├── coverage/                       # SUBSISTEMA 4: Coverage Analytics
│   │   ├── calculator.py               # Calculadora de cobertura
│   │   ├── measure_pncp_expansion.py   # Medicao de expansao PNCP
│   │   ├── run_matching.py             # Execucao de matching
│   │   └── validate_coverage.py        # Validacao de cobertura
│   │
│   ├── matching/                       # SUBSISTEMA 5: Entity Matching
│   │   ├── entity_matcher.py           # Matcher de entidades (dedicado)
│   │   └── measure_baseline.py         # Baseline measurement
│   │
│   ├── fix/                            # SUBSISTEMA 6: Data Repair
│   │   ├── activate_dormant_sources.py # Ativar fontes dormentes
│   │   ├── geocode_missing_entities.py # Geocode de entidades faltantes
│   │   ├── rebuild_evidence_ledger.py  # Reconstruir ledger de evidencia
│   │   ├── resolve_unresolved_entities.py # Resolver entidades nao resolvidas
│   │   ├── sc_dados_abertos_backfill.py   # Backfill SC Dados Abertos
│   │   └── scrape_residual_portals.py  # Scrape de portais residuais
│   │
│   ├── lib/                            # Bibliotecas compartilhadas
│   │   ├── name_normalizer.py          # Normalizacao de nomes (entity matching)
│   │   ├── intel_logging.py            # Logging estruturado
│   │   ├── constants.py                # Constantes do intel pipeline
│   │   ├── cli_validation.py           # Validacao de argumentos CLI
│   │   ├── retry.py                    # Funcoes de retry genericas
│   │   ├── cost_estimator.py           # Estimativa de custos
│   │   ├── bid_simulator.py            # Simulacao de vitoria
│   │   ├── doc_templates.py            # Templates de documentos PDF
│   │   ├── victory_profile.py          # Perfil de vitoria
│   │   ├── win_loss_tracker.py         # Tracking de win/loss
│   │   ├── universe.py                 # CanonicalUniverse, CanonicalEntity
│   │   ├── entity_hierarchy.py         # Hierarquia de entidades
│   │   ├── geocode.py                  # Geocode utilities
│   │   └── value_semantics.py          # Semantica de valores
│   │
│   ├── reports/                        # Relatorios
│   │   ├── panorama.py                 # Panorama de mercado (Excel + terminal)
│   │   ├── coverage_gaps.py            # Gap analysis de cobertura
│   │   └── coverage_weekly.py          # Relatorio semanal de cobertura
│   │
│   ├── pipeline/                       # Pipeline utilities
│   │   └── backfill_multi_source.py    # Backfill multi-source
│   │
│   ├── diagnose/                       # Diagnosticos
│   │   └── dom_sc_diagnostic.py        # Diagnostico DOM-SC
│   │
│   ├── local_datalake.py               # CLI do DataLake (search, supplier, stats)
│   ├── datalake_helper.py              # Helpers do datalake
│   ├── datalake-sc-200km.py            # DataLake no raio 200km
│   ├── export-sc-200km-final.py        # Exportacao final 200km
│   │
│   ├── intel_pipeline.py               # Intel-Busca Pipeline (7 steps + 5 gates)
│   ├── intel_collect.py                # Intel Step 1
│   ├── intel_enrich.py / intel-enrich.py     # Intel Step 2
│   ├── intel_llm_gate.py              # Intel Step 3
│   ├── intel_extract_docs.py          # Intel Step 4
│   ├── intel_analyze.py / intel-analyze.py  # Intel Step 5 (manual)
│   ├── intel_excel.py / intel-excel.py      # Intel Step 6
│   ├── intel_report.py / intel-report.py    # Intel Step 7
│   ├── intel_validate.py / intel-validate.py # Validacao
│   ├── intel_sector_loader.py          # Loader setorial
│   ├── intel_feedback.py              # Feedback loop (win/loss)
│   │
│   ├── consulting_readiness.py         # Consulting Readiness Gate
│   ├── freshness_gate.py              # Freshness Gate SLA
│   ├── health_check.py / healthcheck.py # Healthchecks
│   ├── check_imports.py               # Verificador de imports
│   ├── check-alerts.py                # Alertas
│   ├── collect-metrics.py             # Coleta de metricas
│   ├── notify.py                      # Notificacoes (SMTP/Webhook)
│   ├── report_dedup.py                # Dedup de relatorios
│   ├── coverage_truth.py              # Coverage Truth
│   ├── auditor_deterministic_checks.py # Auditoria deterministica
│   ├── demo_b2g_setorial.py           # Demo B2G setorial
│   ├── generate_consultoria_pdf.py    # PDF de consultoria
│   ├── generate_proposta_pdf.py       # PDF de proposta
│   ├── _pt_accents.py                 # Utilitario de acentos PT-BR
│   ├── pncp_client.py                 # PNCP client generico
│   └── scripts diversos com hyphen:   # (backward compat)
│       collect-metrics.py, collect-report-data.py, generate-proposta-pdf.py,
│       generate-report-b2g.py, health-dashboard.py, radar-b2g-collect.py,
│       retention-b2g-collect.py, war-room-b2g-collect.py, etc.
│
├── tests/                              # Testes automatizados (~61 arquivos)
│   ├── conftest.py                     # Fixtures compartilhadas (ex: sample_pncp_item)
│   ├── conftest_db.py                 # Fixtures de banco real (docker-compose)
│   ├── fixtures/                       # Dados de fixture
│   │   └── ciga_ckan_ac_data.py       # Fixture CIGA CKAN AC
│   ├── smoke/                          # Smoke tests
│   │   ├── test_qw01_pncp_smoke.py
│   │   ├── test_smoke_contract_intel.py
│   │   └── test_smoke_sources.py
│   ├── test_backfill_*.py             # Testes de backfill (2 arquivos)
│   ├── test_cache_ibge.py             # Teste de cache IBGE
│   ├── test_checkpoint.py             # Teste de checkpoint
│   ├── test_ciga_*.py                 # Testes CIGA CKAN (2 arquivos)
│   ├── test_common.py                 # Testes de common.py
│   ├── test_compras_gov_crawler.py    # Teste crawler ComprasGov
│   ├── test_consulting_readiness.py   # Teste readiness gate
│   ├── test_contract_intel_*.py       # Testes Contract Intel (4 arquivos)
│   ├── test_coverage_*.py             # Testes de cobertura (3 arquivos)
│   ├── test_crawler_*.py              # Testes de crawler (5+ arquivos)
│   ├── test_datalake_helper.py        # Teste datalake helper
│   ├── test_date_propagation.py       # Teste propagacao de data
│   ├── test_doe_sc_crawler.py         # Teste crawler DOE-SC
│   ├── test_e2e_external.py           # Teste end-to-end externo
│   ├── test_entity_*.py               # Testes de entidade (2 arquivos)
│   ├── test_evidence_*.py             # Testes de evidencia (2 arquivos)
│   ├── test_fetch_result.py           # Teste fetch result
│   ├── test_freshness_gate.py         # Teste freshness gate
│   ├── test_geocode.py                # Teste geocode
│   ├── test_integration_crawl.py      # Teste integracao crawl
│   ├── test_intel_pipeline.py         # Teste pipeline intel
│   ├── test_manifest.py               # Teste de manifesto
│   ├── test_mides_bigquery_crawler.py # Teste MIDES crawler
│   ├── test_opportunity_*.py          # Testes Opportunity Intel (5 arquivos)
│   ├── test_orchestrator.py           # Teste orquestrador
│   ├── test_pcp_crawler.py            # Teste PCP crawler
│   ├── test_pncp_*.py                 # Testes PNCP (5+ arquivos)
│   ├── test_qw01_*.py                 # Testes QW-01 (2 arquivos)
│   ├── test_report_dedup.py           # Teste dedup relatorio
│   ├── test_sc_*.py                   # Testes SC (2 arquivos)
│   ├── test_scrape_residual_portals.py
│   ├── test_selenium_crawler_adapter.py
│   ├── test_tce_sc_live.py           # Teste TCE-SC live
│   ├── test_transformer.py            # Teste transformer
│   ├── test_transparencia_crawler.py  # Teste transparencia crawler
│   └── test_universe.py              # Teste canonical universe
│
├── db/                                 # Database
│   ├── migrations/                     # 29 migrations SQL (4.273 linhas)
│   │   ├── 001-009: Core schema (pncp_raw_bids, contracts, entities, etc.)
│   │   ├── 010-020: Match logging, coverage, indexes, TTL, GIN, etc.
│   │   ├── 021-025: Entity hierarchy, evidence ledger, contract intel views
│   │   ├── 026: Contract Intelligence Truth V1 (views analiticas)
│   │   ├── 027-028: Opportunity Intelligence (schema + indexes)
│   │   └── 029: QW-01 Auditable Radar (radar runs, monitoring)
│   ├── rollback/                       # Rollback scripts
│   │   └── 029_qw01_auditable_radar.sql
│   ├── seed/                           # Seed data
│   │   ├── 001_sc_entities.py          # 2.085 orgaos SC
│   │   ├── seed_sc_entities.py         # Script de seed
│   │   └── README.md
│   └── setup_db.sh                     # Script de setup
│
├── deploy/                             # Deploy & Operacao
│   ├── install.sh                      # Script de instalacao
│   ├── provision-vps.sh               # Provisionamento Hetzner (18.746 bytes)
│   ├── hardening/                      # Hardening de seguranca
│   │   ├── fail2ban-jail.conf
│   │   ├── pg_hba.conf
│   │   └── ufw-rules.sh
│   └── systemd/                        # 44 services + timers
│       ├── pncp-crawl-full.service/.timer
│       ├── pncp-crawl-inc.service/.timer
│       ├── pncp-enrich.service/.timer
│       ├── pncp-purge.service/.timer
│       ├── pncp-contracts.service/.timer
│       ├── dom-sc-crawl.service/.timer
│       ├── pcp-crawl.service/.timer
│       ├── compras-gov-crawl.service/.timer
│       ├── sc-compras-crawl.service/.timer
│       ├── tce-sc-crawl.service/.timer
│       ├── transparencia-crawl.service/.timer
│       ├── doe-sc-crawl.service/.timer (2 services)
│       ├── extra-crawl-selenium.service/.timer
│       ├── extra-crawl-ciga-ckan.service/.timer
│       ├── extra-crawl-doe-sc.service/.timer
│       ├── coverage-report.service/.timer
│       ├── coverage-report-weekly.service/.timer
│       ├── pncp-report-weekly.service/.timer
│       ├── extra-db-backup.service/.timer
│       ├── extra-health-check.service/.timer
│       ├── extra-collect-metrics.service/.timer
│       ├── extra-check-alerts.service/.timer
│       └── extra-onfailure@.service / onfailure@.service
│
├── backend/                            # Backend data files
│   ├── local_datalake.py              # DataLake CLI (copia?)
│   ├── intel_sectors_config.yaml      # Config setorial (copia?)
│   └── sectors_data.yaml              # Dados setoriais (copia?)
│
├── config/                             # (vide config/ no raiz)
├── data/                               # Dados locais
│   ├── intel/                         # JSON intermediario pipeline intel
│   └── reports/                       # Dados de relatorios
├── output/                             # Artefatos gerados
│   ├── pdfs/
│   ├── excels/
│   ├── logs/
│   └── qw-01/                        # Resultados do QW-01 radar
├── pipeline/                           # Pipeline state
│   ├── backfill_checkpoint.json
│   └── backfill_status.json
├── plan/                               # Planos e estrategias
├── docs/                               # Documentacao
│   ├── architecture/
│   │   ├── architecture.md             # Diagrama C4
│   │   ├── schema-v3.md                # Schema v3
│   │   └── system-architecture.md     # (este documento)
│   ├── prd/                            # PRDs
│   │   ├── PRD-consultoria-extra.md
│   │   ├── technical-debt-DRAFT.md
│   │   └── technical-debt-assessment.md
│   ├── decisions/                      # ADRs
│   │   ├── adr-002-preco-praticado.md
│   │   ├── adr-003-supabase-self-hosted.md
│   │   ├── contract-intelligence-truth-v1.md
│   │   └── qw-01-canonical-opportunity-pipeline.md
│   ├── epic-coverage/                  # Epic de cobertura
│   ├── ops/                            # Runbooks operacionais
│   │   ├── README.md, backup.md, monitoring.md, onboarding.md
│   │   ├── runbook.md, troubleshooting.md, vps-access.md
│   │   └── vps-provisioning.md
│   ├── guides/                         # Guias
│   ├── stories/                        # Development stories
│   └── framework/                      # Framework docs
│
├── docker-compose.yml                  # PostgreSQL + PostGIS para testes
├── pyproject.toml                      # Ruff, mypy, bandit config
├── pytest.ini                          # Config pytest (coverage, markers)
├── conftest.py                         # Fixtures compartilhadas
├── requirements.txt                    # Dependencias Python
├── CLAUDE.md                           # Instrucoes do projeto
├── README.md                           # Documentacao principal
├── .env                                # Env vars (gitignored)
├── .env.example                        # Template de env vars
├── .pre-commit-config.yaml            # Hooks pre-commit
├── .python-version                     # Python 3.12
└── .gitignore
```

---

## 4. Component Architecture

### 4.1 Subsistemas Principais

```
┌──────────────────────────────────────────────────────────────────┐
│                    EXTRA CONSULTORIA PLATFORM                     │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────────────────┐  ┌──────────────────────────────┐   │
│  │ SUBSISTEMA 1            │  │ SUBSISTEMA 2+3              │   │
│  │ CRAWL MULTI-SOURCE      │  │ PIPELINES DE INTELIGENCIA   │   │
│  │ (systemd schedulers)    │  │ (CLI sob demanda)            │   │
│  │                         │  │                              │   │
│  │ 12 fontes cadastradas   │  │ Intel-Busca Pipeline        │   │
│  │ 10 crawlers ativos      │  │   (7 steps + 5 gates)       │   │
│  │ 44 systemd timers       │  │                              │   │
│  │                         │  │ Opportunity Intel           │   │
│  │ monitor.py (main)       │  │   (QW-01 Radar)             │   │
│  │ orchestrator.py (legacy)│  │                              │   │
│  │                         │  │ Contract Intel              │   │
│  │ CrawlRequest protocol   │  │   (Truth V1 views)          │   │
│  │ CrawlerResult dataclass │  │                              │   │
│  └──────────┬──────────────┘  └──────────────┬───────────────┘   │
│             │                                 │                   │
│             └──────────┬──────────────────────┘                   │
│                        ▼                                         │
│           ┌────────────────────────┐                             │
│           │  DATA LAKE (PostgreSQL) │                             │
│           │  Hetzner VPS           │                             │
│           │  pncp_raw_bids         │                             │
│           │  pncp_supplier_contracts│                             │
│           │  sc_public_entities    │                             │
│           │  entity_coverage       │                             │
│           │  coverage_evidence     │                             │
│           │  engineering_opportunities│                           │
│           │  opportunity_intel     │                             │
│           │  contract intel views │                             │
│           └────────────────────────┘                             │
└──────────────────────────────────────────────────────────────────┘
```

### 4.2 Crawl Multi-Source (Subsistema 1)

**Entry point:** `scripts/crawl/monitor.py`
**Orquestrador:** `crawl_source()` — pipeline de 4 fases por fonte
**Registry:** `scripts/crawl/registry.py` — registro centralizado de fontes (SourceInfo)

**Fontes cadastradas:**

| # | Fonte | Modulo | Proposito | Autenticacao | Ordem |
|---|-------|--------|-----------|-------------|-------|
| 1 | PNCP | `pncp_crawler_adapter` | Bids | Publica | 1 |
| 2 | DOM-SC | `dom_sc_crawler` | Bids | API Key | 2 |
| 3 | PCP | `pcp_crawler` | Bids | Publica | 3 |
| 4 | ComprasGov | `compras_gov_crawler` | Bids | Publica | 4 |
| 5 | SC Compras | `sc_compras_crawler` | Bids | Publica | 5 |
| 6 | Contracts | `contracts_crawler` | Bids | Publica | 6 |
| 7 | Transparencia | `transparencia_crawler` | Bids | Publica | 7 |
| 8 | TCE-SC | `tce_sc_crawler` | Bids | Publica | 8 |
| 9 | DOE-SC | `doe_sc_crawler` | Bids | Login/Password | 9 |
| 10 | CIGA CKAN | `ciga_ckan_crawler` | Coverage only | Publica | 10 |
| 11 | MIDES BigQuery | `mides_bigquery_crawler` | Bids | GCP SA | 11 |
| 12 | Selenium | `selenium_crawler_adapter` | Bids | Variada | 12 |

**Pipeline de 4 fases por fonte:**
1. **Crawl** — `crawler.crawl(mode)` -> raw_records[]
2. **Transform** — `crawler.transform(records)` -> normalized records[]
3. **Upsert** — RPC `upsert_pncp_raw_bids()` ou `upsert_pncp_supplier_contracts()`
4. **Entity Match** — 3-level cascade (CNPJ -> nome -> fuzzy)

**Entity Matching (3-level cascade):**
- Level 1: CNPJ exact match (8-digit base) -> confidence: high
- Level 2: Normalized name + municipio constraint -> confidence: high
- Level 3: Fuzzy matching (rapidfuzz/difflib) -> confidence: high|medium|low

### 4.3 Intel-Busca Pipeline (Subsistema 2)

**Entry point:** `scripts/intel_pipeline.py`
**Pipeline:** 7 steps + 5 quality gates

```
intel_pipeline.py --cnpj <CNPJ> --ufs SC,PR,RS
    │
    ├── Step 1: intel_collect.py → dados brutos do datalake + PNCP live
    │   └── GATE 1: COBERTURA (coverage check, UFs coverage, total > 0)
    │
    ├── Step 2: intel_enrich.py → enriquecimento cadastral (BrasilAPI, SICAF)
    │   └── GATE 2: CADASTRAL (sanctions, enrichment coverage)
    │
    ├── Step 2.5: Bid Score Computation (v2 weights: fit*0.20 + viab*0.15 + ...)
    │
    ├── Step 3: intel_llm_gate.py → classificacao LLM (GPT-4.1-nano)
    │   └── GATE 3: RUIDO (compatible ratio, spot check sample)
    │
    ├── Step 4: intel_extract_docs.py → download editais do PNCP
    │   └── GATE 4: CONTEUDO (document coverage, watermark detection)
    │
    ├── Step 5: intel_analyze.py → ANALISE MANUAL (pausa o pipeline)
    │
    ├── Step 6: intel_excel.py → geracao Excel
    │
    └── Step 7: intel_report.py → geracao PDF (ReportLab)
        └── GATE 5: RECOMENDACAO (check NAO PARTICIPAR, capacity)
```

### 4.4 Opportunity Intelligence (Subsistema 3)

**Entry point:** `scripts/opportunity_intel/cli.py`
**Comandos:** `list`, `show`, `explain`, `coverage`, `source-health`, `update`, `export`, `radar`

**QW-01 Auditable Radar** (`scripts/opportunity_intel/radar.py`):
- Pipeline PostgreSQL-only para geracao de oportunidades auditaveis
- Executa monitoramento PNCP com threshold de cobertura (95%)
- Gera planilha CSV com colunas canonicas (opportunity_key, source, valor, ranking, etc.)
- Schema validation via fingerprint + git identity

### 4.5 Contract Intelligence (Subsistema 4)

**Entry point:** `scripts/contract_intel/cli.py`
**Consultas canonicas:**
- `historical_contracts` — 3-year contract history (200km radius)
- `competitor_winners` — supplier rankings by count/value/ticket/concentration
- `expiring_contracts` — contracts ending in 90-180 days
- `manifesto` — per-capability readiness manifest

### 4.6 Coverage Analytics (Subsistema 5)

- `scripts/coverage/calculator.py` — Calcula metricas de cobertura
- `scripts/coverage/measure_pncp_expansion.py` — Mede expansao da cobertura PNCP
- `scripts/coverage/validate_coverage.py` — Validacao de claims de cobertura

---

## 5. Integration Map

### 5.1 External APIs & Services

| API/Servico | URL Base | Autenticacao | Consumido Por | Rate Limit |
|------------|----------|-------------|---------------|------------|
| PNCP Consulta | `https://pncp.gov.br/api/consulta/v3` | Publica | `pncp_crawler_adapter.py`, `pncp_opportunity_crawler.py` | Batch delay 1-2s |
| PNCP Arquivos | `https://pncp.gov.br/api/pncp/v1` | Publica | `intel_extract_docs.py` | - |
| DOM-SC | `https://www.diariomunicipal.sc.gov.br` | API Key | `dom_sc_crawler.py` | Nao documentado |
| PCP v2 | `https://compras.api.portaldecompraspublicas.com.br/v2` | Publica | `pcp_crawler.py` | - |
| ComprasGov v3 | `https://dadosabertos.compras.gov.br` | Publica | `compras_gov_crawler.py` | - |
| BrasilAPI | `https://brasilapi.com.br/api` | Publica | `enricher.py` | Nao documentado (CDN) |
| IBGE Localidades | `https://servicodados.ibge.gov.br/api/v1/localidades` | Publica | `enricher.py` | Nao documentado |
| OpenAI | `https://api.openai.com/v1` | API Key | `intel_llm_gate.py`, `loader.py` | Paga |
| Supabase | Configurado via `SUPABASE_URL` | Service Role Key | `supabase_client.py` (legacy) | Free tier limits |
| PostgreSQL | Hetzner VPS | `LOCAL_DATALAKE_DSN` | Todos os subsistemas | N/A |

### 5.2 Fluxo de Dados Entre Camadas

```
[Fontes Externas]
  PNCP API ──────┐
  DOM-SC  ───────┤
  PCP API ───────┤
  ComprasGov ────┤────► [Crawlers] ──► [Transformer] ──► [Upsert RPC] ──► [PostgreSQL]
  SC Compras ────┤                                            │
  TCE-SC  ───────┤                                     [content_hash]
  Transparencia ─┤                                       dedup
  DOE-SC  ───────┤
  CIGA CKAN ─────┤
  Selenium ──────┘
                                                              │
                                                              ▼
                                                    [Entity Matcher]
                                                    3-level cascade
                                                              │
                                                              ▼
                                              [coverage_evidence ledger]
                                              [entity_coverage trigger]
                                                              │
                    ┌─────────────────────────────────────────┤
                    │                                         │
                    ▼                                         ▼
      [Intel-Busca Pipeline]                     [Opportunity Intel]
      Sob demanda (CLI)                         QW-01 Radar (agendado)
      Steps: Collect→Enrich→LLM→                Monitoramento PNCP →
      Extract→Analyze→Excel→PDF                 Scoring → CSV export
                    │                                         │
                    ▼                                         ▼
      [Contract Intel]                           [Coverage Analytics]
      Truth V1 views                            Calculator, Expansion,
      historical_contracts,                     validate_coverage
      competitor_winners,
      expiring_contracts,
      manifesto
```

---

## 6. Configuration Overview

### 6.1 Environment Variables (config/settings.py)

Toda configuracao e carregada via `python-dotenv` em `config/settings.py`. Mais de 50 variaveis organizadas por dominio:

| Grupo | Exemplos | Qtd |
|-------|----------|-----|
| Database | `LOCAL_DATALAKE_DSN`, `DATALAKE_BACKEND` | 3 |
| OpenAI | `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_TIMEOUT_S` | 4 |
| PNCP API | `PNCP_BASE`, `PNCP_MAX_PAGES`, `PNCP_PAGE_SIZE` | 5 |
| DOM-SC | `DOM_SC_API_KEY`, `DOM_SC_BASE` | 2 |
| PCP | `PCP_BASE` | 1 |
| ComprasGov | `COMPRAS_GOV_BASE` | 1 |
| Ingestion | `INGESTION_UFS`, `INGESTION_MODALIDADES`, `INGESTION_DATE_RANGE_DAYS` | 10+ |
| Crawl config | `INGESTION_FULL_CRAWL_HOUR_UTC`, `INGESTION_INCREMENTAL_HOURS` | 30+ |
| Coverage | `COVERAGE_TARGET_PCT`, `COVERAGE_WINDOW_DAYS` | 2 |
| Enrichment | `ENTITY_ENRICHMENT_TTL_DAYS` | 1 |
| Logging | `INTEL_LOG_LEVEL`, `LOG_FORMAT`, `LOG_MAX_BYTES` | 5 |
| Monitoring | `ALERT_CONSECUTIVE_FAILURES`, `ALERT_DISK_WARN_PCT` | 4 |
| Notification | `NOTIFY_SMTP_*`, `NOTIFY_WEBHOOK_URL` | 7 |
| Backup | `BACKUP_STORAGE_BOX_SSH`, `BACKUP_RETENTION_*` | 6 |

### 6.2 Config Files YAML

| Arquivo | Tamanho | Conteudo |
|---------|---------|----------|
| `config/sectors_config.yaml` | 61KB | 14 setores com CNAE, heuristicas, padroes |
| `config/sectors_data.yaml` | 177KB | Dados complementares por setor |
| `config/transparencia_config.yaml` | 19KB | Config do Portal da Transparencia |
| `config/abbreviations.yaml` | 1.3KB | Abreviacoes para normalizacao |
| `config/municipio_population.yaml` | 1.7KB | Populacao dos municipios |
| `config/client_profiles/extra.yaml` | - | Perfil Extra Construtora |

### 6.3 Secrets Management

- `.env` gitignored contem credenciais reais
- `.env.example` commitado como template com todas as variaveis documentadas
- Service account JSON (`mides-bigquery-sa.json`) presente no repo (risco potencial)
- Nenhuma credencial hardcoded no codigo-fonte

### 6.4 Docker (Test Database)

```yaml
services:
  test-db:
    image: postgis/postgis:16-3.4
    environment:
      POSTGRES_DB: extra_test
      POSTGRES_USER: test
      POSTGRES_PASSWORD: test
    ports:
      - "5433:5432"
    tmpfs: /var/lib/postgresql/data
    healthcheck: pg_isready
```

### 6.5 Pre-commit Hooks (Quality Gates)

| Hook | Verificador | Acao |
|------|------------|------|
| ruff-format | Ruff formatter | Auto-formata Python |
| ruff-check | Ruff linter | Lint + auto-fix |
| mypy-types | mypy | Type check (production modules) |
| bandit-security | Bandit | Security scan (HIGH severity) |
| detect-aws-credentials | pre-commit-hooks | Detect AWS creds |
| detect-private-key | pre-commit-hooks | Detect private keys |

---

## 7. Identified Technical Debts

### 7.1 Table of Technical Debts

| ID | Debito | Severidade | Localizacao | Impacto | Esforco Est. |
|----|--------|------------|-------------|---------|--------------|
| TD-001 | Imports quebrados para `ingestion/` package inexistente | **CRITICAL** | `scripts/crawl/bids_crawler.py` | Crawl BidsCrawler nao executa sem criar diretorio | 2h |
| TD-002 | `DEFAULT_DSN` duplicado entre settings.py e monitor.py | MEDIUM | `monitor.py` vs `config/settings.py` | Risco de configuracao divergente | 1h |
| TD-003 | Type hints ausentes em funcoes de 300+ linhas | HIGH | `monitor.py:_match_entities_cascade` (341 linhas) | Dificuldade de manutencao | 4h |
| TD-004 | Estado global mutavel (cache IBGE module-level) | MEDIUM | `enricher.py` | Race condition potencial | 2h |
| TD-005 | Subprocess sem controle de output estruturado | LOW | `intel_pipeline.py` | Perda de logs estruturados | 2h |
| TD-006 | ANSI color codes manuais com rich disponivel | LOW | `intel_pipeline.py` | Codigo redundante | 1h |
| TD-007 | `import json` inline no meio de funcao | LOW | `monitor.py` | Violacao PEP 8 | 30min |
| TD-008 | Constantes espalhadas vs config/settings.py central | MEDIUM | `enricher.py` (_BRASILAPI_BASE, etc.) | Duplicacao de config | 3h |
| TD-009 | `supabase_client` importado inline | MEDIUM | `enricher.py` (4 ocorrencias) | Performance, violacao PEP 8 | 2h |
| TD-010 | monitor.py com ~1756 linhas, acopla orquestracao + entity matching + coverage | **CRITICAL** | `monitor.py` | Violacao SRP, dificil testar | 8h |
| TD-011 | Duas implementacoes de crawler PNCP (sync adapter + async BidsCrawler) | HIGH | `pncp_crawler_adapter.py` + `bids_crawler.py` | Duas implementacoes para mesma fonte | 6h |
| TD-012 | Fallback silencioso `rapidfuzz`->`difflib` sem alerta | LOW | `monitor.py` | Degradacao de performance silenciosa | 1h |
| TD-013 | Schema validation ausente nos YAML de config | MEDIUM | `config/sectors_config.yaml` | Erro de config silencioso | 4h |
| TD-014 | Sem renovacao automatica de API keys | MEDIUM | `settings.py` | Falha quando chave expira | 2h |
| TD-015 | Sem healthcheck unificado | MEDIUM | N/A | Nao ha endpoint de saude do sistema | 4h |
| TD-016 | SQL queries concatenadas com f-strings | HIGH | `monitor.py` (linhas 67-68 e outras) | Risco teorico de SQL injection | 3h |
| TD-017 | Scripts com hyphen vs underscore duplicados | MEDIUM | `scripts/` (ex: intel-enrich.py + intel_enrich.py) | Confusao de entry points | 4h |
| TD-018 | `backend/` e `config/` duplicam arquivos | MEDIUM | `backend/sectors_data.yaml` == `config/sectors_data.yaml` | Duplicacao de dados (177KB) | 1h |
| TD-019 | Import quebrado para `lib.cli_validation` (path relativo) | HIGH | `intel_pipeline.py:740` | Falha se PYTHONPATH nao configurado | 1h |
| TD-020 | `ingestion/transformer.py` e `_base/crawler.py` sao STUBS | MEDIUM | `scripts/crawl/ingestion/` | Implementacao adiada indefinidamente | 6h |
| TD-021 | PNCP `BASE_URL` divergente: settings.py usa v3, .env.example usa v1 | HIGH | `config/settings.py` vs `.env.example` | Inconsistencia de versao de API | 30min |
| TD-022 | Fallback de DSN hardcoded em varios CLIs | MEDIUM | `opportunity_intel/cli.py`, `local_datalake.py` | Risco de conexao acidental | 2h |
| TD-023 | Mides BigQuery PULADO sem aviso claro | LOW | `.aiox/gotchas.json` | Pode gerar expectativa falsa | 30min |
| TD-024 | Integracao de migrations falha silenciosamente em DB ja migrado | MEDIUM | `tests/conftest_db.py` | Erros de migration podem passar despercebidos | 3h |
| TD-025 | ORM ausente: queries SQL diretas sem abstracao | MEDIUM | Todo o projeto | Acoplamento forte ao schema PostgreSQL | 20h+ |
| TD-026 | Testes sem coverage minima definida | MEDIUM | `tests/` | Nao ha gate de cobertura minima | 2h |
| TD-027 | `monitor.py` contem `_match_entities_cascade()` duplicada do `matching/entity_matcher.py` | HIGH | `monitor.py` + `matching/entity_matcher.py` | Logica de matching duplicada | 4h |
| TD-028 | Sem CI/CD automatizado (GitHub Actions) | HIGH | N/A | Nao ha pipeline de build/test/deploy | 6h |
| TD-029 | Service account JSON no repo | MEDIUM | `config/mides-bigquery-sa.json` | Vazamento de credenciais GCP | 1h |
| TD-030 | scripts/opportunity_intel/schema.py e scripts/coverage/calculator.py sem testes | MEDIUM | `tests/` | Funcionalidades criticas sem cobertura | 4h |

### 7.2 Debt Distribution by Severity

| Severidade | Quantidade | Esforco Estimado |
|------------|-----------|-----------------|
| CRITICAL | 2 | 10h |
| HIGH | 8 | 30h |
| MEDIUM | 14 | 38h |
| LOW | 6 | 6h |
| **Total** | **30** | **~84h** |

### 7.3 Top 5 Recommendations (Architect)

1. **TD-010 Critical** — Refatorar `monitor.py` (1756 linhas): separar entity matching em modulo proprio, extrair database helpers, extrair cobertura reporting. Esforco: 8h. Impacto: viabiliza testes unitarios, reduz complexidade cognitiva.

2. **TD-024 Medium** — Implementar `REQUIRE_TEST_DB=1` como gate de CI: migrations devem aplicar cleanly em DB vazio. Esforco: 3h. Impacto: detecta quebra de schema precocemente.

3. **TD-028 High** — Adicionar GitHub Actions: ruff check, mypy, pytest com `REQUIRE_TEST_DB=1`. Esforco: 6h. Impacto: quality gates automaticos em todo commit.

4. **TD-027 High** — Unificar entity matching: remover duplicacao entre `monitor.py` e `matching/entity_matcher.py`. Esforco: 4h. Impacto: elimina fonte de bugs por divergencia.

5. **TD-001 Critical** — Corrigir imports quebrados no `bids_crawler.py`. Esforco: 2h. Impacto: destrava uso do BidsCrawler async.

---

## 8. Database Schema

### 8.1 Core Tables (29 Migrations)

| Tabela | Migration | Finalidade | Linhas Est. |
|--------|-----------|------------|-------------|
| `pncp_raw_bids` | 001 | Tabela central de licitacoes (unified schema) | Alta |
| `pncp_supplier_contracts` | 002 | Contratos de fornecedores | Media |
| `enriched_entities` | 003 | Cache de enriquecimento (TTL 30d) | Media |
| `sc_public_entities` | 007 | Catalogo 2.085 orgaos SC | 2.085 |
| `ingestion_runs` | 004 | Auditoria de execucao (schema v1+v2) | Media |
| `ingestion_checkpoints` | 004 | Checkpoints resumable | Baixa |
| `entity_coverage` | 009 | Cobertura por entidade (trigger update) | Alta |
| `pncp_enrichment_cache` | - | Cache de enriquecimento PNCP | Media |
| `engineering_opportunities` | - | Oportunidades classificadas engenharia | Media |
| `coverage_evidence` | 024 | Ledger de evidencia de cobertura | Alta |
| `entity_hierarchy` | 021 | Hierarquia de entidades | Baixa |
| `match_log` | 010 | Log de matching | Alta |
| `opportunity_intel` | 027-028 | Oportunidades inteligentes | Media |
| `opportunity_runs` | 027 | Runs do opportunity intel | Baixa |
| `radar_runs` | 029 | Runs do QW-01 radar | Baixa |
| `v_coverage_summary` | - | View de cobertura | - |
| `v_unmatched_bids` | 011 | Bids nao matchadas (view) | - |
| Views Contract Intel | 026 | historical_contracts, etc. | - |

### 8.2 Key Indexes

- GIN trgm para full-text search em portugues (objeto_compra, orgao_razao_social)
- HNSW para similaridade vetorial (se habilitado)
- Indexes por uf, modalidade, valor, orgao_cnpj, matched_entity_id
- UNIQUE em pncp_id, content_hash

---

## 9. Build/Deploy Setup

### 9.1 Ambiente de Desenvolvimento

```bash
# Setup
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
pip install pre-commit && pre-commit install

# Test database
docker compose up -d test-db
pytest -m integration
docker compose down

# Quality gate local
pre-commit run --all-files
pytest --cov=scripts --cov-report=term-missing
```

### 9.2 Ambiente de Producao (Hetzner VPS)

**Sistema:** Ubuntu 24.04
**Database:** PostgreSQL 17 + PostGIS
**Deploy:** `deploy/install.sh` + `deploy/provision-vps.sh`
**Scheduler:** 44 systemd services/timers
**Backup:** Hetzner Storage Box via `extra-db-backup.service`
**Logging:** `/var/log/extra-*.log` com rotacao
**Hardening:** fail2ban, UFW, pg_hba.conf restrito

### 9.3 Services Systemd por Categoria

| Categoria | Services | Frequencia |
|-----------|----------|------------|
| Crawl PNCP | 3 (full, inc, enrich/contracts/purge) | Full 1x/dia, Inc 3x/dia |
| Crawl DOM-SC | 1 | 1x/dia |
| Crawl PCP | 1 | 1x/dia |
| Crawl ComprasGov | 1 | 1x/dia |
| Crawl SC Compras | 1 | 1x/dia |
| Crawl TCE-SC | 1 | 1x/dia |
| Crawl Transparencia | 1 | 1x/dia |
| Crawl DOE-SC | 2 (HTTP + Selenium) | 1x/dia |
| Crawl Selenium | 1 | 1x/dia |
| Crawl CIGA CKAN | 1 | 1x/dia |
| Reporting | 3 (coverage, coverage-weekly, pncp-weekly) | Diario/Semanal |
| Operations | 5 (db-backup, health-check, metrics, alerts, onfailure) | Variada |

---

## 10. Security Observations

| Observacao | Severidade | Detalhe |
|-----------|------------|---------|
| Chaves em `.env` gitignored | OK | Segue 12-factor |
| Database DSN com senha em .env | OK | Nao commitado |
| PostgreSQL exposto sem firewall de aplicacao | MEDIO | Apenas network-level (Hetzner firewall) |
| SQL queries com f-strings | **ALTO** | `monitor.py` — risco teorico de SQL injection |
| Service account JSON no repo | MEDIO | `config/mides-bigquery-sa.json` exposto |
| Sem logging estruturado com correlation IDs | BAIXO | Dificulta debugging distribuido |
| Sem rate limiting adaptativo (headers HTTP) | INFORMATIVO | Delay fixo via config |
| Sem criptografia em repouso | INFORMATIVO | Dados publicos de licitacao |
| Sem autenticacao de aplicacao | INFORMATIVO | Single-user, acesso via VPS SSH |

---

## 11. Test Coverage Analysis

### 11.1 Test Suite Composition

| Categoria | Arquivos | Descricao |
|-----------|----------|-----------|
| Smoke tests | 3 | QW-01, Contract Intel, Sources |
| Unit tests | ~20 | Transformer, geocode, checkpoint, manifest, etc. |
| Integration tests | ~15 | Crawlers com DB real, pipeline, backfill |
| E2E tests | 1 | test_e2e_external.py |
| Database tests | ~15 | `test_pncp_*`, `test_evidence_*`, `test_coverage_*` |
| Entity tests | 2 | Hierarchy, matcher |
| QW-01 tests | 2 | Radar, postgres |

### 11.2 Coverage Gaps

| Modulo | Cobertura | Risco |
|--------|-----------|-------|
| `scripts/crawl/` | Parcial (crawlers individuais testados) | Medio |
| `scripts/opportunity_intel/` | Parcial (models, dedup, transformer) | Alto |
| `scripts/contract_intel/` | Baixo | Alto |
| `scripts/matching/` | Baixo | Alto |
| `scripts/coverage/` | Baixo | Medio |
| `scripts/lib/` | Parcial (name_normalizer) | Medio |

### 11.3 CI Quality Gates

| Gate | Ferramenta | Bloqueia? |
|------|------------|-----------|
| Format | ruff format | Pre-commit |
| Lint | ruff check | Pre-commit |
| Type Check | mypy | Pre-commit |
| Security | bandit | Pre-commit |
| Testes | pytest --cov | Nao automatizado (sem CI) |
| Secrets | pre-commit-hooks | Pre-commit |

---

## 12. Code Quality & Patterns

### 12.1 Padroes Positivos

| Padrao | Localizacao | Beneficio |
|--------|-------------|-----------|
| Registry centralizado de fontes | `scripts/crawl/registry.py` | Elimina 6 listas duplicadas |
| Protocol-based crawler contract | `ingestion/_base/crawler.py` (CrawlerProtocol) | Contrato explicito para crawlers |
| Coverage evidence ledger | `coverage_evidence` table | Rastreabilidade auditavel |
| Quality gates pipeline | `intel_pipeline.py` | Validacao estruturada em cadeia |
| Schema validation + fingerprint | `opportunity_intel/schema.py` | Integridade de schema |
| Graceful degradation | Circuit breaker + fallbacks | Resiliencia a falhas externas |
| Checkpoint resumable | `checkpoint.py` | Crawl nao perde progresso |
| Config centralizada | `config/settings.py` | Single source of truth |
| Pre-commit automation | `.pre-commit-config.yaml` | Qualidade consistente |

### 12.2 Anti-Padroes Identificados

| Anti-Padrao | Localizacao | Severidade |
|-------------|-------------|------------|
| monitor.py com 1756 linhas | `monitor.py` | CRITICAL |
| Entity matching duplicado | `monitor.py` + `matching/entity_matcher.py` | HIGH |
| Scripts hyphen + underscore | `scripts/intel-enrich.py` + `intel_enrich.py` | MEDIUM |
| backend/ e config/ duplicam dados | `backend/sectors_data.yaml` | MEDIUM |
| Import quebrado lib. prefix | `intel_pipeline.py` linha 740 | HIGH |
| STUB incompleto | `scripts/crawl/ingestion/transformer.py` | MEDIUM |
| ANSI codes manuais vs rich | `intel_pipeline.py` | LOW |
| import inline no meio de funcao | `monitor.py` | LOW |
| f-strings em SQL queries | `monitor.py` | HIGH |

---

## 13. Recommendations

### 13.1 Curto Prazo (Sprint 0 — ~20h)

1. **TD-010 (8h)**: Refatorar `monitor.py` — extrair entity matching para `matching/`, extrair database helpers para `scripts/lib/db.py`, extrair coverage reporting para `scripts/coverage/`.
2. **TD-001 (2h)**: Corrigir imports quebrados no `bids_crawler.py` ou remover o arquivo orphan.
3. **TD-024 (3h)**: Implementar `REQUIRE_TEST_DB=1` como gate de CI — migrations devem aplicar cleanly.
4. **TD-029 (1h)**: Remover `config/mides-bigquery-sa.json` do repo (adicionar ao .gitignore).
5. **TD-019 (1h)**: Corrigir import quebrado para `lib.cli_validation` em `intel_pipeline.py`.
6. **TD-021 (30min)**: Alinhar PNCP_BASE entre settings.py (v3) e .env.example (v1).

### 13.2 Medio Prazo (Sprint 1-2 — ~30h)

7. **TD-027 (4h)**: Unificar entity matching: eliminar duplicacao monitor.py vs entity_matcher.py.
8. **TD-028 (6h)**: Adicionar GitHub Actions: ruff, mypy, pytest com REQUIRE_TEST_DB=1.
9. **TD-025 (6h, parcial)**: Adicionar camada de abstracao de banco (pydantic/psycopg2.sql).
10. **TD-011 (6h)**: Consolidar implementacoes de crawler PNCP (sync adapter + async BidsCrawler).
11. **TD-016 (3h)**: Substituir f-strings em SQL por psycopg2.sql ou parametros %s.
12. **TD-018 (1h)**: Eliminar duplicacao entre `backend/` e `config/`.

### 13.3 Longo Prazo

13. Healthcheck unificado do sistema (conexao DB, APIs externas, cobertura).
14. Schema validation com Pydantic para YAML de config.
15. Renovacao automatica de API keys com alertas de expiracao.
16. Logging estruturado com correlation IDs para debugging distribuido.
17. CI/CD completo com GitHub Actions + deploy automatizado.

---

## 14. Recent Git History (Context)

```
249340d feat: finalize QW-01 operational radar run
ce55095 feat: add QW-01 auditable opportunity radar
0fef9de fix: restore critical readiness CI gates
1c8b63f Document freshness gate in operations runbooks
3eeb4d6 Make freshness gate SLA configurable
15177dc Add freshness gate for critical local sources
da81611 Clarify freshness-first scope and stabilize readiness semantics
8f55fd6 fix: market share ORDER BY total_value, remove duplicate win_rate key
722381d fix: update test_manifest.py import — CANONICAL_UNIVERSE from scripts.lib.universe
5754194 docs: CI gates documentation in README, update story FIX-UNIVERSE status
77265b5 feat: competitive intelligence — market share, HHI, supplier ranking
132df3e fix: desagio reclassified as LIMITED
824af88 feat: P1 remediation — canonical universe, source health, CI fail-closed
5e7af23 fix: Phase 0 remediation — truth before features
1195495 feat: B2G readiness gate — verified coverage, fixed crawlers, unified schema
7454a0f feat: Opportunity Intelligence Truth V1
86fc886 feat: Contract Intelligence Truth v1
9e2ff90 feat: Consulting Readiness Gate
2ee6f4f feat: Contract Intelligence vertical slice
0ee490b feat: entity-level evidence projection for PNCP coverage truth
```

**Tendencias observadas:**
- Foco recente em readiness gates e qualidade (freshness, CI gates, coverage truth)
- Amadurecimento dos subsistemas de inteligencia (QW-01, Contract Intel Truth V1)
- Remediacao de divida tecnica (Phase 0, P1 remediation)
- Ausencia de CI/CD automatizado (gates manuais via pre-commit)

---

> **Documento gerado por Aria (Visionary Architect).**
> **Total analisado:** ~117k linhas Python + SQL, 29 migrations, 44 systemd services, 61 test files, 12 fontes de dados.
> **Debitos identificados:** 30 (2 CRITICAL, 8 HIGH, 14 MEDIUM, 6 LOW) — ~84h estimados para resolucao.
> **Proxima fase:** Brownfield Discovery — Fase 2: Database Schema Audit (Dara).
