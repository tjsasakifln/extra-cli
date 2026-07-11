# Inventário do Projeto — Extra Consultoria

> Atualizado pelo Scout em 2026-07-11T19:00:00Z (re-scout pós commit e9729e1)
> doc_level: completo

---

## Sumário

| Métrica | Valor Anterior | Valor Atual | Delta |
|---------|---------------|-------------|-------|
| Arquivos Python | 58 | 139 | +81 |
| LOC Python | 50.651 | 98.247 | +47.596 |
| Arquivos SQL | 12 | 26 | +14 |
| LOC SQL | 771 | 5.328 | +4.557 |
| Arquivos de teste | 10 | 17 | +7 |
| Migrations DB | 12 | 19 | +7 |
| Supabase migrations | 0 | 7 | +7 |
| Systemd timers | 13 | 37 | +24 |
| Módulos | 8 | 9 | +1 (matching) |
| Epics concluídos | 1 | 3 | +2 |

---

## Estrutura de Diretórios

```
/
├── scripts/                     # 139 arquivos Python (98.247 LOC)
│   ├── crawl/                   # 30 arquivos — crawlers + orquestrador (8 fontes)
│   │   ├── monitor.py           # Orquestrador multi-source
│   │   ├── orchestrator.py      # Lógica de orquestração
│   │   ├── checkpoint.py        # Checkpoint/resume de crawls
│   │   ├── circuit_breaker.py   # Proteção contra falhas em cascata
│   │   ├── config.py            # Configuração dos crawlers
│   │   ├── common.py            # Utilitários comuns
│   │   ├── security.py          # Sanitização de SQL
│   │   ├── async_client.py      # Cliente HTTP assíncrono
│   │   ├── sync_client.py       # Cliente HTTP síncrono
│   │   ├── _parallel_mixin.py   # Mixin de paralelismo
│   │   ├── retry.py             # Retry com backoff
│   │   ├── adapter.py           # Adaptador de fonte
│   │   ├── transformer.py       # Transformação de dados
│   │   ├── enricher.py          # Enriquecimento (IBGE, BrasilAPI)
│   │   ├── loader.py            # Carga no PostgreSQL
│   │   ├── pncp_crawler.py      # PNCP (API v1)
│   │   ├── pncp_pca_crawler.py  # PNCP PCA (planos de contratação)
│   │   ├── pncp_arp_crawler.py  # PNCP ARP (atas de registro de preço)
│   │   ├── pncp_crawler_adapter.py # Adaptador PNCP
│   │   ├── compras_gov_crawler.py  # ComprasGov v3
│   │   ├── contracts_crawler.py    # Contratos (PNCP)
│   │   ├── pcp_crawler.py         # PCP v2
│   │   ├── bids_crawler.py        # Licitações
│   │   ├── transparencia_crawler.py # Transparência (maior: 41K)
│   │   ├── tce_sc_crawler.py      # TCE-SC ESFINGE
│   │   ├── sc_compras_crawler.py  # SC Compras
│   │   ├── doe_sc_crawler.py      # DOE-SC
│   │   ├── dom_sc_crawler.py      # DOM-SC
│   │   └── sanctions.py           # SICAF (requer Playwright)
│   ├── intel_pipeline.py       # Pipeline principal (orquestrador 7 stages)
│   ├── intel-collect.py        # Stage 1 — Coleta (3.2K LOC)
│   ├── intel-enrich.py         # Stage 2 — Enriquecimento
│   ├── intel-validate.py       # Stage 3 — Validação
│   ├── intel-analyze.py        # Stage 4 — Análise GPT (1.8K LOC)
│   ├── intel-extract-docs.py   # Stage 5 — Extração docs
│   ├── intel-excel.py          # Stage 6 — Geração Excel
│   ├── intel-report.py         # Stage 7 — Relatório final (2.2K LOC)
│   ├── intel_llm_gate.py       # Gate de qualidade LLM
│   ├── intel_sector_loader.py  # Carregador de setores
│   ├── local_datalake.py       # CLI DataLake (search, stats, supplier)
│   ├── datalake_helper.py      # Helpers do DataLake
│   ├── datalake-sc-200km.py    # DataLake SC raio 200km
│   ├── export-sc-200km-final.py # Export SC 200km
│   ├── matching/               # 2 arquivos — Entity matching
│   │   ├── __init__.py
│   │   └── entity_matcher.py   # Casamento de entidades (fuzzy)
│   ├── reports/                # 3 arquivos — Relatórios
│   │   ├── panorama.py         # Panorama setorial
│   │   ├── coverage_gaps.py    # Análise de gaps de cobertura
│   │   └── coverage_weekly.py  # Relatório semanal de cobertura
│   ├── lib/                    # 10 arquivos — Biblioteca compartilhada
│   │   ├── bid_simulator.py    # Simulador de licitações
│   │   ├── cost_estimator.py   # Estimador de custos
│   │   ├── victory_profile.py  # Perfil de vitória
│   │   ├── win_loss_tracker.py # Rastreador win/loss
│   │   ├── name_normalizer.py  # Normalização de nomes
│   │   ├── doc_templates.py    # Templates de documentos
│   │   ├── cli_validation.py   # Validação CLI
│   │   ├── intel_logging.py    # Logging do pipeline
│   │   ├── retry.py            # Retry (lib-level)
│   │   └── constants.py        # Constantes
│   ├── generate_report_b2g.py  # Relatório B2G (6.5K LOC — maior script)
│   ├── generate_proposta_pdf.py # PDF proposta comercial
│   ├── generate_consultoria_pdf.py # PDF consultoria
│   ├── demo_b2g_setorial.py    # Demo setorial B2G
│   ├── health-dashboard.py     # Dashboard health crawlers
│   ├── health_check.py         # Health check rápido
│   ├── healthcheck.py          # Health check alternativo
│   ├── notify.py               # Notificações
│   ├── pricing-b2g-collect.py  # Coleta Pricing B2G
│   ├── radar-b2g-collect.py    # Coleta Radar B2G
│   ├── retention-b2g-collect.py # Coleta Retention B2G
│   ├── war-room-b2g-collect.py # Coleta War Room B2G
│   ├── validate-report-data.py # Validação dados relatório
│   ├── report_dedup.py         # Deduplicação de relatórios
│   ├── auditor_deterministic_checks.py # Auditoria determinística
│   ├── build-proposta-data.py  # Build dados proposta
│   ├── check-alerts.py         # Verificação de alertas
│   ├── collect-metrics.py      # Coleta de métricas
│   ├── collect-report-data.py  # Coleta dados relatório
│   ├── collect_report_data.py  # ⚠️ DUPLICADO de collect-report-data.py
│   ├── _pt_accents.py          # Normalização de acentos PT-BR
│   └── conftest.py             # Config pytest raiz
├── config/                     # Configuração
│   ├── settings.py             # Settings central
│   ├── logging_config.py       # Config de logging
│   ├── sectors_config.yaml     # Config de setores
│   ├── sectors_data.yaml       # Dados de setores
│   ├── abbreviations.yaml      # Abreviações
│   └── transparencia_config.yaml # Config transparência
├── db/                         # Database
│   ├── migrations/             # 19 migrations SQL
│   ├── seed/                   # Seed 2.085 órgãos SC
│   ├── setup_db.sh             # Provisionamento
│   ├── apply-migrations.sh     # Aplicação de migrations
│   ├── backup-database.sh      # Backup
│   ├── restore-database.sh     # Restore
│   ├── verify-schema-divergence.sh # Verificação schema
│   └── cleanup-expired-entities.sql # Limpeza entidades expiradas
├── supabase/                   # Supabase
│   └── migrations/             # 7 migrations Supabase
├── deploy/                     # Infraestrutura
│   ├── install.sh              # Instalação VPS
│   ├── provision-vps.sh        # Provisionamento inicial
│   ├── systemd/                # 37 units (18 serviços + 18 timers + 1 template)
│   └── hardening/              # Hardening segurança
│       ├── fail2ban-jail.conf
│       ├── pg_hba.conf
│       └── ufw-rules.sh
├── docs/                       # Documentação
│   ├── prd/                    # PRDs
│   ├── architecture/           # Documentação de arquitetura
│   ├── guides/                 # Guias
│   ├── ops/                    # Operações
│   ├── qa/                     # QA gates e relatórios
│   ├── reports/                # Relatórios de projeto
│   ├── research/               # Pesquisas
│   ├── reviews/                # Revisões
│   ├── sessions/               # Logs de sessão
│   ├── stories/                # Stories de desenvolvimento
│   │   └── epics/              # 3 epics documentados
│   └── td-001/                 # Technical Debt 001
│       └── coverage-reports/   # Relatórios de cobertura
├── tests/                      # 17 arquivos de teste
│   ├── test_cache_ibge.py
│   ├── test_checkpoint.py
│   ├── test_common.py
│   ├── test_compras_gov_crawler.py
│   ├── test_contracts_crawler.py
│   ├── test_coverage_calculator.py
│   ├── test_crawler_pncp.py
│   ├── test_datalake_helper.py
│   ├── test_entity_matcher.py
│   ├── test_intel_pipeline.py
│   ├── test_orchestrator.py
│   ├── test_pcp_crawler.py
│   ├── test_report_dedup.py
│   ├── test_transformer.py
│   ├── test_transparencia_crawler.py
│   ├── test_upsert_contracts.py
│   └── scripts/test_monitoring.py
├── .github/agents/             # 12 definições de agentes AIOX
├── .env.example
├── requirements.txt
├── pyproject.toml              # ruff + mypy + pytest config
├── .python-version             # 3.12
└── CLAUDE.md                   # Instruções do projeto
```

---

## Módulos Identificados (9)

| # | Módulo | Arquivos | LOC | Descrição |
|---|--------|----------|-----|-----------|
| 1 | **crawl** | 30 | ~27.000 | Crawlers multi-source (8 fontes) + orquestrador |
| 2 | **intel** | 17 | ~38.000 | Pipeline 7 stages + scripts kebab + LLM gate |
| 3 | **reports** | 4 | ~6.000 | Panorama setorial, coverage gaps, weekly |
| 4 | **lib** | 10 | ~3.200 | Simulação, estimativa, normalização, templates |
| 5 | **matching** | 2 | ~300 | Entity matching com fuzzy |
| 6 | **config** | 6 | ~400 | Settings, logging, YAMLs de setores |
| 7 | **db** | 26 | ~5.328 | 19 migrations + 7 supabase + scripts |
| 8 | **deploy** | 41 | ~3.556 | 37 systemd units + hardening + provision |
| 9 | **docs** | ~50 | — | PRDs, arquitetura, stories, QA gates |

---

## Entry Points (27 CLIs)

| Entry Point | Tipo | Descrição |
|-------------|------|-----------|
| `scripts/crawl/monitor.py` | CLI | Orquestrador de crawlers |
| `scripts/intel_pipeline.py` | CLI | Pipeline inteligência 7 stages |
| `scripts/intel-collect.py` | CLI | Coleta dados licitação |
| `scripts/intel-enrich.py` | CLI | Enriquecimento IBGE/BrasilAPI |
| `scripts/intel-validate.py` | CLI | Validação dados |
| `scripts/intel-analyze.py` | CLI | Análise GPT-4.1-nano |
| `scripts/intel-extract-docs.py` | CLI | Extração documentos |
| `scripts/intel-excel.py` | CLI | Geração Excel |
| `scripts/intel-report.py` | CLI | Relatório final |
| `scripts/local_datalake.py` | CLI | DataLake search/stats/supplier |
| `scripts/reports/panorama.py` | CLI | Panorama setorial |
| `scripts/generate_report_b2g.py` | CLI | Relatório B2G |
| `scripts/generate_proposta_pdf.py` | CLI | PDF proposta |
| `scripts/health-dashboard.py` | CLI | Dashboard health |
| `scripts/healthcheck.py` | CLI | Health check |
| `scripts/notify.py` | CLI | Notificações |
| `scripts/war-room-b2g-collect.py` | CLI | War Room B2G |
| `scripts/radar-b2g-collect.py` | CLI | Radar B2G |
| `scripts/pricing-b2g-collect.py` | CLI | Pricing B2G |
| `scripts/retention-b2g-collect.py` | CLI | Retention B2G |
| `scripts/validate-report-data.py` | CLI | Validação relatório |
| `scripts/auditor_deterministic_checks.py` | CLI | Auditoria |
| `db/setup_db.sh` | Shell | Provisionamento DB |
| `db/backup-database.sh` | Shell | Backup |
| `deploy/install.sh` | Shell | Instalação VPS |
| `deploy/provision-vps.sh` | Shell | Provisionamento VPS |

---

## Linguagens e Frameworks

- **Python 3.12** — 98.247 LOC em 139 arquivos
- **PostgreSQL 17** — 5.328 LOC SQL em 26 arquivos
- **Shell** — 3.556 LOC em 5 scripts
- **YAML** — 404 LOC em 4 arquivos de configuração

### Stack Principal
- **HTTP:** httpx 0.28.1 (sync + async)
- **LLM:** OpenAI 1.55.0 (gpt-4.1-nano)
- **DB:** psycopg2-binary 2.9.9
- **PDF:** reportlab 4.5.1
- **Excel:** openpyxl 3.1.5
- **CLI:** rich 13.0.0
- **Fuzzy:** rapidfuzz 3.0.0
- **HTML:** lxml 5.0.0, beautifulsoup4 4.12.0

### Dev Tools
- **Lint/Format:** ruff (pyproject.toml)
- **Type Check:** mypy (strict mode)
- **Test:** pytest + pytest-cov

---

## Integrações Externas (9)

| # | Nome | Tipo | Auth |
|---|------|------|------|
| 1 | PNCP API | REST | Pública |
| 2 | DOM-SC | Web | API Key |
| 3 | PCP v2 | REST | Pública |
| 4 | ComprasGov v3 | REST | Pública |
| 5 | TCE-SC ESFINGE | Web | Pública |
| 6 | DOE-SC | Web | Pública |
| 7 | OpenAI | LLM | API Key |
| 8 | BrasilAPI | REST | Pública |
| 9 | IBGE API | REST | Pública |

---

## Infraestrutura

- **Plataforma:** Hetzner VPS (Ubuntu 24.04)
- **Scheduler:** systemd (37 units: 18 serviços + 18 timers + 1 template)
- **Banco:** PostgreSQL 17 self-hosted
- **Backup:** systemd timer `extra-db-backup`
- **Hardening:** fail2ban + ufw
- **Acesso:** SSH terminal

---

## Cobertura de Testes

- **Framework:** pytest + pytest-cov
- **Arquivos:** 17 (era 10)
- **Cobertura estimada:** baixa (<30% de 98K LOC)
- **Categorias:** unit, integration, slow

---

## ⚠️ Duplicações Detectadas

| Arquivo 1 | Arquivo 2 | Tamanho |
|-----------|-----------|---------|
| `scripts/collect-report-data.py` | `scripts/collect_report_data.py` | 426 KB (idêntico) |
| `scripts/generate-report-b2g.py` | `scripts/generate_report_b2g.py` | 271 KB (idêntico) |
| `scripts/generate-proposta-pdf.py` | `scripts/generate_proposta_pdf.py` | ~40 KB |
| `scripts/intel-analyze.py` | `scripts/intel_analyze.py` | 70 KB (idêntico) |
| `scripts/intel-collect.py` | `scripts/intel_collect.py` | 127 KB (idêntico) |
| `scripts/intel-enrich.py` | `scripts/intel_enrich.py` | 24 KB (idêntico) |
| `scripts/intel-excel.py` | `scripts/intel_excel.py` | 38 KB (idêntico) |
| `scripts/intel-extract-docs.py` | `scripts/intel_extract_docs.py` | 34 KB (idêntico) |
| `scripts/intel-report.py` | `scripts/intel_report.py` | 87 KB (idêntico) |
| `scripts/intel-validate.py` | `scripts/intel_validate.py` | 40 KB (idêntico) |

**10 pares de arquivos duplicados** — scripts com nome kebab-case e snake_case idênticos. Infla o codebase em ~+50K LOC artificialmente.

---

## Notas do Scout (Re-run)

1. **Crescimento explosivo:** +93% LOC em 1 commit. Código gerado por IA (Claude) com possíveis inconsistências de estilo entre módulos.
2. **Duplicação sistemática:** 10 pares de scripts duplicados (kebab vs snake_case). Provável artefato de geração.
3. **Cobertura de testes diluída:** 17 testes para 98K LOC = densidade <1 teste por 5.7K LOC.
4. **Novo módulo `matching/`** não documentado nos artefatos SDD existentes.
5. **7 supabase migrations** — camada adicional de DB não coberta pelo ERD atual.
6. **Scripts B2G** (pricing, radar, retention, war-room) formam um subsistema de business intelligence não mapeado nas specs.
