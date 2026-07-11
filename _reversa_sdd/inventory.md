# Inventário do Projeto — Extra Consultoria

> Gerado pelo Scout em 2026-07-11T12:00:00Z
> Projeto: Extra Consultoria — Inteligência em Licitações

---

## Visão Geral

Plataforma CLI de consultoria estratégica para licitações públicas. Single-client (Extra Construtora). DataLake PostgreSQL no Hetzner VPS. Multi-source data ingestion com systemd timers. Relatórios PDF/Excel sob demanda.

- **Propósito:** Monitorar 100% dos 2.085 órgãos públicos de SC, coletar licitações, gerar inteligência de mercado
- **Persona:** Tiago Sasaki — Consultor de Inteligência em Licitações
- **Acesso:** SSH terminal (WSL → Hetzner VPS)
- **Stack:** Python 3.12 + PostgreSQL 17 + systemd timers + OpenAI GPT-4.1-nano

---

## Estrutura de Pastas

```
extra consultoria/
├── config/                  # Configurações centralizadas
│   ├── settings.py          # Settings from env vars (12-factor)
│   ├── sectors_config.yaml  # 13 setores com CNAEs, heurísticas, pesos
│   ├── sectors_data.yaml    # Dados complementares de setores
│   ├── abbreviations.yaml   # Abreviações para normalização
│   └── transparencia_config.yaml  # Config de portais de transparência
├── scripts/                 # Pipeline de inteligência (50.651 LOC Python)
│   ├── crawl/               # Crawlers multi-source (25 arquivos)
│   │   ├── monitor.py              # Orquestrador multi-source (687 linhas)
│   │   ├── pncp_crawler_adapter.py # Adapter PNCP API → unified schema
│   │   ├── dom_sc_crawler.py       # DOM-SC (~280 municípios)
│   │   ├── pcp_crawler.py          # PCP v2 (100+ municípios)
│   │   ├── compras_gov_crawler.py  # ComprasGov v3 (federal)
│   │   ├── sc_compras_crawler.py   # SC Compras
│   │   ├── contracts_crawler.py    # Contratos (histórico)
│   │   ├── transparencia_crawler.py # Portais de transparência
│   │   ├── tce_sc_crawler.py       # TCE-SC (ESFINGE)
│   │   ├── pncp_arp_crawler.py     # Atas de Registro de Preço
│   │   ├── pncp_pca_crawler.py     # Plano de Contratação Anual
│   │   ├── enricher.py             # BrasilAPI CNPJ + IBGE
│   │   ├── sanctions.py            # SICAF checking
│   │   ├── transformer.py          # Normalização multi-source
│   │   ├── loader.py               # Upsert PostgreSQL
│   │   ├── adapter.py              # Interface comum de crawler
│   │   ├── async_client.py         # HTTP async
│   │   ├── sync_client.py          # HTTP sync
│   │   ├── checkpoint.py           # Crawl resumable
│   │   ├── circuit_breaker.py      # Circuit breaker pattern
│   │   ├── retry.py                # Retry logic
│   │   └── config.py               # Config do módulo crawl
│   ├── reports/             # Relatórios (4 arquivos)
│   │   ├── panorama.py             # Panorama de mercado setorial
│   │   ├── coverage_gaps.py        # Gap detection
│   │   └── coverage_weekly.py      # Relatório semanal
│   ├── lib/                 # Bibliotecas compartilhadas (11 arquivos)
│   │   ├── name_normalizer.py      # Normalização de nomes (PT-BR)
│   │   ├── bid_simulator.py        # Simulador de lances
│   │   ├── cost_estimator.py       # Estimativa de custos
│   │   ├── victory_profile.py      # Perfil de vitória de concorrente
│   │   ├── win_loss_tracker.py     # Tracking win/loss
│   │   ├── doc_templates.py        # Templates de documentos
│   │   ├── constants.py            # Constantes do projeto
│   │   ├── intel_logging.py        # Logging estruturado
│   │   ├── cli_validation.py       # Validação CLI
│   │   └── retry.py                # Retry decorator
│   ├── intel_pipeline.py    # Orquestrador pipeline (7 stages + 5 gates)
│   ├── intel_collect.py     # Coleta de licitações
│   ├── intel_enrich.py      # Enriquecimento cadastral
│   ├── intel_llm_gate.py    # Gate LLM (classificação)
│   ├── intel_extract_docs.py # Extração de documentos
│   ├── intel_analyze.py     # Análise (OpenAI)
│   ├── intel_validate.py    # Validação de dados
│   ├── intel_report.py      # Geração de relatório
│   ├── intel_excel.py       # Export Excel estilizado
│   ├── intel_sector_loader.py # Loader de setores (YAML → Python)
│   ├── local_datalake.py    # CLI do DataLake
│   ├── datalake_helper.py   # Helpers de banco
│   ├── generate_proposta_pdf.py   # PDF de proposta comercial
│   ├── generate_consultoria_pdf.py # PDF de consultoria
│   ├── generate_report_b2g.py     # Relatório B2G
│   └── collect_report_data.py     # Coleta de dados para relatório
├── db/                     # Database (12 migrations + seed)
│   ├── migrations/         # 12 arquivos SQL (001 a 012)
│   ├── seed/               # Seed de órgãos SC (1.006 LOC Python)
│   └── setup_db.sh         # Script de provisionamento
├── deploy/                 # Deployment
│   ├── install.sh          # Script de instalação no Hetzner
│   └── systemd/            # 13 timers + 13 services + 1 template onFailure
├── docs/                   # Documentação
│   ├── architecture/       # Arquitetura C4
│   ├── prd/                # PRD (Product Requirements Document)
│   ├── stories/            # Stories do EPIC-001
│   ├── qa/gates/           # 7 QA gates executados
│   ├── research/           # Pesquisas (TCE-SC ESFINGE)
│   ├── guides/             # Guias (Hetzner + Supabase)
│   └── sessions/           # Handoffs de sessão
├── data/                   # Dados locais
│   ├── intel/              # Cache de inteligência
│   ├── reports/            # Relatórios gerados
│   └── dumps/              # SQL dumps
├── output/                 # Saída
│   ├── pdfs/               # PDFs gerados
│   ├── excels/             # Excels gerados
│   ├── reports/            # Relatórios de cobertura
│   └── logs/               # Logs
├── plan/                   # Planejamento de execução
├── .env.example            # Template de variáveis de ambiente
├── .python-version         # Python 3.12
├── requirements.txt        # Dependências Python
└── README.md               # Documentação principal
```

---

## Linguagens e Frameworks

| Linguagem | Arquivos | LOC | Percentual |
|-----------|----------|-----|------------|
| Python | 58 | 50.651 | 96.4% |
| SQL | 12 | 771 | 1.5% |
| Shell | 2 | ~100 | 0.2% |
| YAML | 5 | ~2.100 | — (config) |
| Markdown | 15 | — | — (docs) |

**Linguagem principal:** Python 3.12

**Frameworks e bibliotecas principais:**

| Biblioteca | Versão | Uso |
|-----------|--------|-----|
| httpx | >=0.28.1 | HTTP client async |
| openai | >=1.55.0 | GPT-4.1-nano (análise de editais) |
| psycopg2-binary | >=2.9.9 | PostgreSQL driver |
| python-dotenv | >=1.0.0 | Env vars |
| pyyaml | >=6.0 | Config YAML |
| reportlab | >=4.5.1 | PDF generation |
| openpyxl | >=3.1.5 | Excel generation |
| rich | >=13.0.0 | Terminal UI |
| lxml | >=5.0.0 | XML/HTML parsing |
| beautifulsoup4 | >=4.12.0 | HTML parsing |
| rapidfuzz | >=3.0.0 | Fuzzy string matching |

**Gerenciador de pacotes:** pip (requirements.txt)

---

## Entry Points

| Arquivo | Tipo | Descrição |
|---------|------|-----------|
| `scripts/crawl/monitor.py` | CLI principal | Orquestrador multi-source de crawlers |
| `scripts/intel_pipeline.py` | CLI pipeline | Pipeline de inteligência (7 stages) |
| `scripts/local_datalake.py` | CLI datalake | DataLake queries (search, stats, supplier) |
| `scripts/reports/panorama.py` | CLI relatório | Panorama de mercado setorial |
| `scripts/generate_proposta_pdf.py` | CLI PDF | Geração de proposta comercial |
| `scripts/generate_report_b2g.py` | CLI relatório | Relatório B2G |
| `db/setup_db.sh` | Setup | Provisionamento do banco |
| `deploy/install.sh` | Deploy | Instalação no Hetzner |

---

## Configuração e CI/CD

**Arquivos de configuração:**
- `.env.example` — 148 linhas, 40+ variáveis documentadas
- `config/settings.py` — Settings centralizado (122 linhas)
- `config/sectors_config.yaml` — 13 setores com CNAEs e heurísticas (2.116 linhas)
- `config/sectors_data.yaml` — Dados complementares
- `config/abbreviations.yaml` — Abreviações PT-BR
- `config/transparencia_config.yaml` — Config de portais

**CI/CD:**
- `.github/` — GitHub Actions (agents config)
- Systemd timers como scheduler primário (13 timers)

**Docker:** Não utilizado. Deploy direto no Hetzner VPS (Ubuntu 24.04).

---

## Banco de Dados

**SGBD:** PostgreSQL 17 (Hetzner VPS)

**Tabelas (12 migrations):**

| Migration | Tabela | Descrição |
|-----------|--------|-----------|
| 001 | `pncp_raw_bids` | Licitações multi-source unificado (FTS PT-BR, 12 índices) |
| 002 | `pncp_supplier_contracts` | Contratos de fornecedores |
| 003 | `enriched_entities` | Cache BrasilAPI/IBGE |
| 004 | `ingestion_runs`, `ingestion_checkpoints` | Auditoria de crawls |
| 005 | `search_datalake_rpc` | RPC de busca full-text |
| 006 | `upsert_pncp_raw_bids` RPC | Upsert otimizado |
| 007 | `sc_public_entities` | 2.085 órgãos SC |
| 008 | `purge_rpc` | Limpeza de registros antigos |
| 009 | Índices + `entity_coverage` | Tracking de cobertura |
| 010 | `match_logging` | Log de entity matching |
| 011 | `v_unmatched_bids` | View de bids não matched |
| 012 | `coverage_snapshots` | Snapshots de cobertura |

**Seed:** `db/seed/001_sc_entities.py` + `seed_sc_entities.py` (1.006 LOC) — popula 2.085 órgãos SC a partir de planilha Excel.

---

## Integrações Externas

| Integração | Tipo | Crawler/Modulo | Autenticação |
|-----------|------|---------------|--------------|
| **PNCP API** | API REST | `pncp_crawler_adapter.py` | Pública |
| **DOM-SC** | Portal web | `dom_sc_crawler.py` | API Key |
| **PCP v2** | API REST | `pcp_crawler.py` | Pública |
| **ComprasGov v3** | Dados abertos | `compras_gov_crawler.py` | Pública |
| **SC Compras** | Portal | `sc_compras_crawler.py` | Pública |
| **TCE-SC (ESFINGE)** | Portal | `tce_sc_crawler.py` | Pública |
| **Portais Transparência** | Web scraping | `transparencia_crawler.py` | Pública |
| **OpenAI API** | API REST | `intel_analyze.py` | API Key |
| **BrasilAPI** | API REST | `enricher.py` | Pública |
| **IBGE** | API REST | `enricher.py` | Pública |
| **SICAF** | Portal (opcional) | `sanctions.py` | Playwright |

---

## Testes

| Framework | Arquivos | Cobertura |
|-----------|----------|-----------|
| pytest | 10 arquivos de teste | Estimada baixa (<30%) |

**Arquivos de teste identificados:** 10 (`test_*.py` ou `*_test.py`)

---

## Módulos Identificados

1. **crawl** — Coleta multi-source (8 crawlers + orquestrador)
2. **intel** — Pipeline de inteligência (collect → enrich → llm_gate → extract → analyze → validate → report)
3. **reports** — Relatórios (panorama, coverage, sazonalidade)
4. **lib** — Bibliotecas compartilhadas (normalização, simulação, estimativa, templates)
5. **config** — Configuração centralizada (settings, setores, abreviações)
6. **db** — Database (migrations, seed, setup)
7. **deploy** — Deployment (systemd timers, install script)
8. **docs** — Documentação (PRD, arquitetura, stories, QA gates)

---

## Métricas do Projeto

| Métrica | Valor |
|---------|-------|
| Total de arquivos Python | 58 |
| Total de LOC Python | 50.651 |
| Migrations SQL | 12 |
| Systemd timers | 13 |
| Setores configurados | 13 |
| Órgãos monitorados | 2.085 |
| Fontes de dados | 8 (+ 1 gap-fill Transparência) |
| Dependências Python | 11 |
| Commits no repositório | 16 |
| Cobertura alvo | 100% (raio 200km) |
| Epic concluído | EPIC-001 (7 stories) |
