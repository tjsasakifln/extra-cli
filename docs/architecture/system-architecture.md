# System Architecture — Extra Consultoria

> **Documento gerado em:** 2026-07-11
> **Propósito:** Brownfield Discovery — Fase 1: Documentacao do Sistema
> **Autor:** Aria (Visionary Architect)

---

## 1. Executive Summary

A Extra Consultoria e uma plataforma CLI de inteligencia em licitacoes publicas, single-client (Extra Construtora), operada pelo consultor Tiago Sasaki. O sistema e uma maquina de crawling multi-source que monitora 2.085 orgaos publicos de Santa Catarina em 5+ fontes de dados abertos, combinando ingestao continua (systemd timers) com pipelines de inteligencia sob demanda (CLI).

A arquitetura segue um modelo de **DataLake PostgreSQL centralizado** rodando em Hetzner VPS, com crawlers Python async que coletam, transformam e fazem upsert de dados de licitacoes publicas. Um pipeline secundario de inteligencia (Intel-Busca) aplica quality gates em cadeia para filtrar e classificar editais relevantes para a construtora, gerando relatorios em Excel e PDF.

O sistema possui aproximadamente 64.000 linhas de codigo Python + SQL, divididas em 3 subsistemas principais: (1) Crawl Multi-Source com 8 crawlers especializados, (2) Pipeline Intel-Busca com 7 steps e 5 quality gates, e (3) Banco de Dados relacional com 12 migrations e schema otimizado para busca full-text em portugues.

---

## 2. Technology Stack

| Camada | Tecnologia | Versao | Justificativa |
|--------|-----------|--------|---------------|
| Linguagem | Python | 3.12 (.python-version) | Ecossistema rico para crawling e LLM |
| Database | PostgreSQL | 17 | Single-user, sem REST overhead; pg_trgm para fuzzy search |
| HTTP Client | httpx | >=0.28.1 | Async nativo para crawl concorrente |
| LLM | OpenAI GPT-4.1-nano | - | Custo baixo, qualidade suficiente para classificacao |
| PDF | ReportLab | >=4.5.1 | Codigo existente validado (Big Four aesthetic) |
| Excel | openpyxl | >=3.1.5 | Geracao de planilhas de analise |
| CLI Interface | rich | >=13.0.0 | Output colorido e tabelas no terminal |
| HTML Parsing | lxml + beautifulsoup4 | >=5.0.0 + >=4.12.0 | Crawling de portais de diarios oficiais |
| Fuzzy Matching | rapidfuzz | >=3.0.0 | Entity matching 3-level cascade |
| Database Driver | psycopg2-binary | >=2.9.9 | Conexao nativa PostgreSQL |
| Config | python-dotenv + PyYAML | >=1.0.0 + >=6.0 | 12-factor app, secrets fora do codigo |
| Scheduler | systemd timers | Nativo Linux | Sem dependencia externa (Redis/ARQ) |
| Embeddings | text-embedding-3-small | - | Opcional, via OpenAI STORY-438 |
| Deployment | Hetzner VPS | Ubuntu 24.04 | Cloud host |

---

## 3. Project Structure

```
/mnt/d/extra consultoria/
├── config/                          # Configuracoes centralizadas
│   ├── settings.py                  # Env vars loading (todas as configuracoes)
│   ├── sectors_config.yaml          # 14 setores de negocio (engenharia, saude, etc.)
│   ├── sectors_data.yaml            # Dados complementares por setor
│   ├── abbreviations.yaml           # Abreviacoes para normalizacao
│   └── transparencia_config.yaml    # Config portal da transparencia
│
├── scripts/                         # TODO codigo fonte Python
│   ├── crawl/                       # Subsistema de Crawl Multi-Source
│   │   ├── monitor.py               # ORQUESTRADOR PRINCIPAL (entry point)
│   │   ├── pncp_crawler_adapter.py  # PNCP API adapter (async)
│   │   ├── dom_sc_crawler.py        # DOM-SC Portal crawler
│   │   ├── pcp_crawler.py           # PCP v2 API crawler
│   │   ├── compras_gov_crawler.py   # ComprasGov v3 API crawler
│   │   ├── sc_compras_crawler.py    # SC Compras crawler
│   │   ├── tce_sc_crawler.py        # TCE-SC crawler
│   │   ├── transparencia_crawler.py # Portal Transparencia crawler
│   │   ├── contracts_crawler.py     # Contratos crawler
│   │   ├── pncp_arp_crawler.py      # Atas de Registro de Precos
│   │   ├── pncp_pca_crawler.py      # Planos de Contratacoes Anuais
│   │   ├── bids_crawler.py          # BidsCrawler class (BaseCrawler subclasse)
│   │   ├── enricher.py              # Enriquecimento fornecedores (BrasilAPI + IBGE)
│   │   ├── transformer.py           # Transform raw API -> unified schema
│   │   ├── loader.py                # Upsert via RPC + embeddings
│   │   ├── config.py                # Crawl-specific config
│   │   ├── _parallel_mixin.py       # Mixin paralelo para async
│   │   ├── async_client.py          # HTTP async client
│   │   ├── sync_client.py           # HTTP sync client fallback
│   │   ├── adapter.py               # PNCPLegacyAdapter
│   │   ├── checkpoint.py            # Crawl resumable checkpoints
│   │   ├── circuit_breaker.py       # Circuit breaker pattern
│   │   ├── retry.py                 # Retry com backoff
│   │   └── sanctions.py             # Sanctions checking
│   │
│   ├── intel_collect.py             # Intel Step 1: coleta de dados
│   ├── intel_enrich.py              # Intel Step 2: enriquecimento
│   ├── intel_llm_gate.py           # Intel Step 3: gate LLM para ruido
│   ├── intel_extract_docs.py        # Intel Step 4: extracao de documentos
│   ├── intel_analyze.py             # Intel Step 5: analise (manual)
│   ├── intel_excel.py               # Intel Step 6: geracao Excel
│   ├── intel_report.py              # Intel Step 7: geracao PDF
│   ├── intel_pipeline.py            # ORQUESTRADOR Intel-Busca (7 steps + 5 gates)
│   ├── intel_validate.py            # Validacao de dados
│   ├── intel_sector_loader.py       # Carregador de config setorial
│   ├── intel_feedback.py            # Feedback loop (win/loss tracking)
│   │
│   ├── lib/                         # Bibliotecas compartilhadas
│   │   ├── name_normalizer.py       # Normalizacao de nomes (entity matching)
│   │   ├── intel_logging.py         # Logging estruturado
│   │   ├── constants.py             # Constantes do intel pipeline
│   │   ├── cli_validation.py        # Validacao de argumentos CLI
│   │   ├── retry.py                 # Funcoes de retry genericas
│   │   ├── cost_estimator.py        # Estimativa de custos
│   │   ├── bid_simulator.py         # Simulacao de vitoria
│   │   ├── doc_templates.py         # Templates de documentos PDF
│   │   ├── victory_profile.py       # Perfil de vitoria
│   │   └── win_loss_tracker.py      # Tracking de win/loss
│   │
│   ├── reports/                     # Relatorios
│   │   ├── panorama.py              # Panorama de mercado (Excel + terminal)
│   │   ├── coverage_gaps.py         # Gap analysis de cobertura
│   │   └── coverage_weekly.py       # Relatorio semanal de cobertura
│   │
│   ├── local_datalake.py            # CLI do DataLake (search, supplier, stats)
│   ├── datalake_helper.py           # Helpers do datalake
│   ├── generate_consultoria_pdf.py  # Geracao PDF de consultoria
│   ├── generate_proposta_pdf.py     # Geracao PDF de proposta
│   ├── generate_report_b2g.py       # Relatorio B2G
│   ├── collect_report_data.py       # Coleta dados para relatorio
│   └── _pt_accents.py               # Utilitario de acentos portugues
│
├── db/                              # Database
│   ├── migrations/                  # 12 migrations SQL numeradas
│   │   ├── 001_pncp_raw_bids.sql    # Core bids table + full-text search
│   │   ├── 002_pncp_supplier_contracts.sql
│   │   ├── 003_enriched_entities.sql
│   │   ├── 004_ingestion_tables.sql # ingestion_runs, checkpoints
│   │   ├── 005_search_datalake_rpc.sql
│   │   ├── 006_upsert_rpcs.sql      # upsert_pncp_raw_bids RPC
│   │   ├── 007_sc_public_entities.sql
│   │   ├── 008_purge_rpc.sql
│   │   ├── 009_indexes_and_coverage.sql # entity_coverage + triggers
│   │   ├── 010_match_logging.sql
│   │   ├── 011_unmatched_bids_view.sql
│   │   └── 012_coverage_snapshots.sql
│   ├── seed/                        # Seed data
│   │   ├── 001_sc_entities.py       # 2.085 orgaos SC da planilha
│   │   └── seed_sc_entities.py
│   └── setup_db.sh                  # Script de setup do banco
│
├── deploy/                          # Deploy
│   ├── install.sh                   # Script de instalacao
│   └── systemd/                     # systemd units
│       ├── pncp-crawl-full.service/.timer
│       ├── pncp-crawl-inc.service/.timer
│       ├── dom-sc-crawl.service/.timer
│       ├── pcp-crawl.service/.timer
│       ├── compras-gov-crawl.service/.timer
│       ├── tce-sc-crawl.service/.timer
│       ├── transparencia-crawl.service/.timer
│       ├── pncp-enrich.service/.timer
│       ├── pncp-purge.service/.timer
│       ├── pncp-contracts.service/.timer
│       ├── coverage-report.service/.timer
│       ├── coverage-report-weekly.service/.timer
│       ├── pncp-report-weekly.service/.timer
│       └── onfailure@.service        # Failure notification template
│
├── data/                            # Dados locais
│   ├── intel/                       # JSON intermediario do pipeline intel
│   └── reports/                     # Dados de relatorios
│
├── output/                          # Artefatos gerados
│   ├── pdfs/
│   ├── excels/
│   └── logs/
│
├── docs/                            # Documentacao
│   ├── architecture/architecture.md # Diagrama C4 existente
│   └── stories/                     # Development stories
│
├── .env                             # Env vars (gitignored)
├── .env.example                     # Template de env vars
├── requirements.txt                 # Dependencias Python
├── CLAUDE.md                        # Instrucoes do projeto
└── README.md                        # Documentacao principal
```

---

## 4. Entry Points & Data Flows

### 4.1 Entry Points

| Entry Point | Localizacao | Modo | Gatilho |
|------------|-------------|------|---------|
| **monitor.py** | `scripts/crawl/monitor.py` | CLI | systemd timer / manual |
| **intel_pipeline.py** | `scripts/intel_pipeline.py` | CLI | Manual sob demanda |
| **local_datalake.py** | `scripts/local_datalake.py` | CLI | Manual |
| **panorama.py** | `scripts/reports/panorama.py` | CLI | systemd timer / manual |
| **generate_report_b2g.py** | `scripts/generate_report_b2g.py` | CLI | Manual |

### 4.2 Fluxo Principal: Crawl Multi-Source

```
systemd timer (ex: pncp-crawl-full.timer)
    │
    ▼
monitor.py --source pncp --mode full
    │
    ├── 1. Load entities (2.085 orgaos SC via _load_entities)
    ├── 2. Dynamic import crawler (_load_crawler)
    │       └── importlib.import_module("scripts.crawl.pncp_crawler_adapter")
    │
    ├── 3. Phase 1: CRAWL
    │       └── crawler.crawl(mode) → raw_records[]
    │
    ├── 4. Phase 2: TRANSFORM
    │       └── crawler.transform(raw_records) → normalized records[]
    │
    ├── 5. Phase 3: UPSERT (via RPC)
    │       └── upsert_pncp_raw_bids(records) → {inserted, updated, unchanged}
    │
    ├── 6. Phase 4: ENTITY MATCHING (3-level cascade)
    │       ├── Level 1: CNPJ exact match (8-digit base) → confidence: high
    │       ├── Level 2: Normalized name + municipio → confidence: high
    │       └── Level 3: Fuzzy matching (rapidfuzz/difflib) → confidence: high|medium|low
    │
    └── 7. Coverage update (via AFTER INSERT trigger)
            └── entity_coverage trigger → atualiza is_covered
```

### 4.3 Fluxo Intel-Busca Pipeline

```
intel_pipeline.py --cnpj 01721078000168 --ufs SC,PR,RS
    │
    ├── Step 1: intel_collect.py → dados brutos do datalake + PNCP live
    │   └── GATE 1: COBERTURA (coverage check, UFs coverage, total > 0)
    │
    ├── Step 2: intel_enrich.py → enriquecimento cadastral (BrasilAPI, SICAF)
    │   └── GATE 2: CADASTRAL (sanctions, enrichment coverage)
    │
    ├── Step 2.5: Bid Score Computation (v2 weights)
    │   └── Score composite: fit_estrategico*0.20 + viabilidade*0.15 + ...
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
        └── GATE 5: RECOMENDACAO (check zero NAO PARTICIPAR, capacity)
```

### 4.4 Fluxo de Dados Entre Camadas

```
[Fontes Externas]
  PNCP API ──┐
  DOM-SC  ───┤
  PCP API ───┤
  ComprasGov ┤───► [Crawlers] ──► [Transformer] ──► [Loader/RPC] ──► [PostgreSQL]
  SC Compras─┤                          ▲                              │
  TCE-SC  ───┤                          │                              │
  Transparen─┘                    [content_hash]                [pncp_raw_bids]
                                     dedup                        │
                                                                  ▼
                                                         [Entity Matcher]
                                                         3-level cascade
                                                                  │
                                                                  ▼
                                                         [entity_coverage]
                                                         trigger update
                                                                  │
                                                                  ▼
[Intel Pipeline] ──► [DataLake Query] ──► [Enrich] ──► [LLM Gate] ──► [Analysis] ──► [PDF/Excel]
```

---

## 5. Dependencies

### 5.1 External APIs & Services

| API/Servico | URL Base | Autenticacao | Rate Limit | Uso |
|------------|----------|-------------|------------|-----|
| PNCP Consulta | `https://pncp.gov.br/api/consulta/v1` | Nao requer (publico) | Nao documentado (batch delay 1-2s) | Crawl principal de licitacoes |
| PNCP Arquivos | `https://pncp.gov.br/api/pncp/v1` | Nao requer (publico) | - | Download de documentos |
| DOM-SC | `https://www.diariomunicipal.sc.gov.br` | API Key (`DOM_SC_API_KEY`) | Nao documentado | Diario Oficial municipios SC |
| PCP v2 | `https://compras.api.portaldecompraspublicas.com.br/v2` | Nao requer | - | Portal de Compras Publicas |
| ComprasGov v3 | `https://dadosabertos.compras.gov.br` | Nao requer | - | Compras federais |
| BrasilAPI | `https://brasilapi.com.br/api` | Nao requer | Nao documentado (CDN 23 regioes) | Enriquecimento CNPJ |
| IBGE Localidades | `https://servicodados.ibge.gov.br/api/v1/localidades` | Nao requer | Nao documentado | Geo-enriquecimento municipios |
| IBGE SIDRA | `https://servicodados.ibge.gov.br/api/v3/agregados` | Nao requer | - | Populacao municipios |
| OpenAI | `https://api.openai.com/v1` | API Key (`OPENAI_API_KEY`) | Paga | Classificacao LLM + embeddings |
| PostgreSQL | Hetzner VPS | `LOCAL_DATALAKE_DSN` | N/A | Database principal |

### 5.2 Internal Module Dependencies

```
monitor.py
  ├── scripts.crawl.pncp_crawler_adapter
  ├── scripts.crawl.dom_sc_crawler
  ├── scripts.crawl.pcp_crawler
  ├── scripts.crawl.compras_gov_crawler
  ├── scripts.crawl.sc_compras_crawler
  ├── scripts.crawl.contracts_crawler
  ├── scripts.crawl.transparencia_crawler
  ├── scripts.crawl.tce_sc_crawler
  ├── scripts.lib.name_normalizer
  └── psycopg2

bids_crawler.py
  ├── scripts.crawl.transformer (transform_batch)
  ├── scripts.crawl.loader (bulk_upsert, purge_old_bids)
  ├── scripts.crawl.checkpoint
  └── scripts.crawl.config

intel_pipeline.py
  ├── intel_collect.py (subprocess)
  ├── intel_enrich.py (subprocess)
  ├── intel_llm_gate.py (subprocess)
  ├── intel_extract_docs.py (subprocess)
  ├── intel_excel.py (subprocess)
  ├── intel_report.py (subprocess)
  └── scripts.lib.cli_validation

enricher.py
  ├── httpx (BrasilAPI, IBGE)
  └── supabase_client (get_supabase)
```

### 5.3 Python Packages (requirements.txt)

| Package | Versao Minima | Uso |
|---------|--------------|-----|
| httpx | >=0.28.1 | HTTP async client para crawlers e APIs |
| openai | >=1.55.0 | LLM (classificacao) + embeddings |
| psycopg2-binary | >=2.9.9 | Driver PostgreSQL |
| python-dotenv | >=1.0.0 | Leitura de .env |
| pyyaml | >=6.0 | Leitura de YAML config |
| reportlab | >=4.5.1 | Geracao de PDFs |
| openpyxl | >=3.1.5 | Geracao de Excel |
| rich | >=13.0.0 | CLI output colorido |
| lxml | >=5.0.0 | Parsing HTML/XML |
| beautifulsoup4 | >=4.12.0 | Parsing HTML |
| rapidfuzz | >=3.0.0 | Fuzzy string matching (entity matching) |

---

## 6. Configuration & Environment

### 6.1 Environment Variables

Toda configuracao vive em variaveis de ambiente carregadas via `python-dotenv` em `config/settings.py`. Nenhum valor hardcoded no codigo.

| Variavel | Default | Descricao |
|----------|---------|-----------|
| `LOCAL_DATALAKE_DSN` | `postgresql://postgres:smartlic_local@127.0.0.1:54399/postgres` | DSN do PostgreSQL |
| `DATALAKE_BACKEND` | `local` | Backend do datalake |
| `DATALAKE_QUERY_ENABLED` | `true` | Query habilitada |
| `OPENAI_API_KEY` | `` | Key OpenAI |
| `OPENAI_MODEL` | `gpt-4.1-nano` | Modelo LLM |
| `OPENAI_TIMEOUT_S` | `10` | Timeout chamada OpenAI |
| `OPENAI_MAX_CONCURRENT` | `5` | Max chamadas concorrentes |
| `PNCP_BASE` | `https://pncp.gov.br/api/consulta/v1` | PNCP API base |
| `PNCP_MAX_PAGES` | `50` | Max paginas por fetch |
| `PNCP_PAGE_SIZE` | `100` | Tamanho pagina |
| `PNCP_MAX_RETRIES` | `1` | Max retries |
| `DOM_SC_API_KEY` | `` | DOM-SC API key |
| `DOM_SC_BASE` | `https://www.diariomunicipal.sc.gov.br` | DOM-SC base URL |
| `PCP_BASE` | `https://compras.api.portaldecompraspublicas.com.br/v2` | PCP API base |
| `COMPRAS_GOV_BASE` | `https://dadosabertos.compras.gov.br` | ComprasGov base |
| `INGESTION_UFS` | `SC` | UFs para ingestao |
| `INGESTION_MODALIDADES` | `4,5,6,7` | Modalidades (4=Concorrencia, 5=Pregao Eletronico, 6=Pregao Presencial, 7=Contratacao Direta) |
| `INGESTION_DATE_RANGE_DAYS` | `3` | Dias para full crawl |
| `INGESTION_INCREMENTAL_DAYS` | `3` | Dias para incremental |
| `INGESTION_PURGE_GRACE_DAYS` | `400` | Retencao em dias |
| `COVERAGE_TARGET_PCT` | `100.0` | Meta de cobertura |
| `COVERAGE_WINDOW_DAYS` | `90` | Janela de cobertura |
| `INTEL_LOG_LEVEL` | `INFO` | Nivel de logging |

### 6.2 Config Files YAML

| Arquivo | Conteudo |
|---------|----------|
| `config/sectors_config.yaml` | 14 setores com CNAE, heuristicas, padroes, regras de negocio (2.116 linhas) |
| `config/sectors_data.yaml` | Dados complementares por setor |
| `config/abbreviations.yaml` | Abreviacoes para normalizacao textual |
| `config/transparencia_config.yaml` | Config do Portal da Transparencia |

### 6.3 Secrets Management

- `.env` gitignored contem credenciais reais
- `.env.example` commitado como template
- Nenhuma credencial hardcoded no codigo-fonte
- `DOM_SC_API_KEY`, `OPENAI_API_KEY` e `LOCAL_DATALAKE_DSN` sao as principais secrets

---

## 7. Code Patterns & Conventions

### 7.1 Padroes Identificados

| Categoria | Padrao | Onde |
|-----------|--------|------|
| **Async Crawl** | `async/await` com `asyncio.Semaphore` para controle de concorrencia | `scripts/crawl/` (bids_crawler.py, _parallel_mixin.py) |
| **Sync Pipeline** | `subprocess.run()` para execucao sequencial de scripts | `intel_pipeline.py` |
| **Module-level Functions** | Funcoes modulares sem classes (funcional puro) | `monitor.py`, `transformer.py`, `loader.py` |
| **Classes ABC** | `BaseCrawler` como classe base abstrata | `bids_crawler.py` |
| **Mixin Pattern** | `_PNCPParallelMixin` via MRO | `_parallel_mixin.py` |
| **Circuit Breaker** | Degradacao gradual de chamadas HTTP | `circuit_breaker.py` |
| **Retry with Backoff** | Exponential backoff para APIs externas | `retry.py`, `enricher.py` |
| **Content Hash Dedup** | SHA-256 hash de campos chave para change detection | `transformer.py` |
| **3-Level Entity Match** | Cascade: CNPJ -> normalized name -> fuzzy | `monitor.py` |
| **Quality Gates** | Pipeline pattern com g validates intermediarios | `intel_pipeline.py` |
| **Subprocess Delegation** | Scripts chamam outros scripts via subprocess | `intel_pipeline.py` |
| **Singleton HTTP** | Context manager `async with AsyncPNCPClient()` | `bids_crawler.py` |
| **Graceful Degradation** | Circuit breaker + fallback para difflib | `_parallel_mixin.py`, `monitor.py` |
| **Dynamic Import** | `importlib.import_module()` para carregar crawlers | `monitor.py` (load_crawler) |

### 7.2 Convencoes de Nomenclatura

| Elemento | Convencao | Exemplo |
|----------|-----------|---------|
| Arquivos Python | `snake_case` | `intel_pipeline.py` |
| Funcoes | `snake_case` | `crawl_source()`, `_match_entity()` |
| Classes | `PascalCase` | `BidsCrawler`, `PNCPLegacyAdapter` |
| Variaveis | `snake_case` | `raw_records`, `matched_entity` |
| Constantes | `UPPER_SNAKE` | `INGESTION_DATE_RANGE_DAYS` |
| Constantes privadas | `_UPPER` | `_BRASILAPI_BASE` |
| Funcoes privadas | `_prefix` | `_get_conn()`, `_load_entities()` |
| Metodos async | `async def` prefix | `async def fetch_page()` |
| Configuracoes | `TEXT_LIKE` (env var style) | `PNCP_MAX_PAGES` |

### 7.3 Tratamento de Erros

- **Pattern**: `try/except` localizado com `logger.warning/error` e continuacao
- **Fallback**: `rapidfuzz` -> `difflib` (graceful degradation)
- **Circuit Breaker**: `_circuit_breaker` monitora falhas e reduz concorrencia
- **Retry**: Exponential backoff com multiplas tentativas para APIs externas
- **Partial Success**: Falha de upsert RPC continua com proximo batch
- **Nao propaga excecoes**: Erros em steps do pipeline sao logged e continuam

### 7.4 Anti-Padroes Observados

| Anti-Padrao | Localizacao | Impacto |
|-------------|-------------|---------|
| `DEFAULT_DSN` duplicada | `monitor.py` linha 48 vs `settings.py` | Configuracao inconsistente |
| `psycopg2` queries diretas sem ORM | `monitor.py` | Acoplamento DB, sem type safety |
| Subprocess `sys.executable` | `intel_pipeline.py` | Acoplamento ao interpretador atual |
| Constantes espalhadas | Diversos `_ENRICH_STALENESS_DAYS`, `_BRASILAPI_BASE` | Duplicacao de config |
| `global _IBGE_MUNICIPIOS_CACHE` | `enricher.py` linha 483/484 | Estado global mutavel |
| `capture_output=False` | `intel_pipeline.py` linha 173 | Output ao vivo, sem controle |
| `from supabase_client import...` inline | `enricher.py` linha 102 | Import dinamico oculto |
| `from ingestion.*` imports quebrados | `bids_crawler.py` linha 32-70 | Importa de `ingestion/` mas diretorio nao existe |
| ANSI codes manuais | `intel_pipeline.py` linhas 65-72 | Rich ja disponivel no projeto |
| Funcao com 341 linhas | `_match_entities_cascade` em `monitor.py` | Violacao SRP |
| `import json` inline | `monitor.py` linha 493 | Import no meio da funcao |

---

## 8. Technical Debt Inventory (System Level)

| ID | Debito | Severidade | Localizacao | Impacto |
|----|--------|------------|-------------|---------|
| TD-001 | Imports quebrados para `ingestion/` package que nao existe | CRITICAL | `bids_crawler.py` (importacao de ingestion._base, ingestion.config, etc.) | Crawl BidsCrawler nao executa sem criar diretorio faltante |
| TD-002 | DSN default duplicado (monitor.py vs settings.py) | MEDIUM | `monitor.py:48`, `settings.py:33` | Risco de configuracao divergente |
| TD-003 | Ausencia de type hints em _match_entities_cascade (341 linhas) | HIGH | `monitor.py:142-341` | Dificuldade de manutencao |
| TD-004 | Estado global mutavel (cache IBGE module-level) | MEDIUM | `enricher.py:483-484` | Race condition potencial |
| TD-005 | Subprocess sem controle de output | LOW | `intel_pipeline.py:168-176` | Perda de logs estruturados |
| TD-006 | ANSI color codes manuais com Rich disponivel | LOW | `intel_pipeline.py:65-72` | Codigo redundante |
| TD-007 | `import json` inline no meio da funcao | LOW | `monitor.py:493` | Violacao PEP 8 |
| TD-008 | Constantes de config espalhadas no codigo vs settings.py | MEDIUM | `enricher.py` (_BRASILAPI_BASE, _ENRICH_STALENESS_DAYS, etc.) | Duplicacao de config |
| TD-009 | Ausencia de testes unitarios automatizados | CRITICAL | TODO o projeto | Nao ha garantia contra regression |
| TD-010 | `supabase_client` importado inline em vez de no topo | MEDIUM | `enricher.py:102,209,322,580` | Violacao PEP 8, performance |
| TD-011 | Monitor.py com ~687 linhas, acopla orquestracao + entity matching + coverage | HIGH | `monitor.py` | Violacao SRP, dificil testar |
| TD-012 | Fallback silencioso para difflib sem alerta | LOW | `monitor.py:216-221` | Pode degradar performance sem notificacao |
| TD-013 | Sem schema validation nos YAML de config | MEDIUM | `config/sectors_config.yaml` | Erro de config silencioso |
| TD-014 | Sem renovacao automatica de API keys | MEDIUM | `settings.py` | Falha quando expira |
| TD-015 | Sem healthcheck unificado do sistema | MEDIUM | N/A | Nao ha endpoint de saude |
| TD-016 | Duas implementacoes de crawler (monitor.py-legacy vs bids_crawler.py-new) | HIGH | `monitor.py` + `bids_crawler.py` | Duas implementacoes para PNCP crawl: `monitor.py` usa sync adapter, `bids_crawler.py` usa async BidsCrawler |

---

## 9. Integration Points

### 9.1 PNCP API (Federal)
- **URL**: `https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao`
- **Metodo**: GET com paginacao (pagina, tamanho)
- **Auth**: Nao requer (API publica)
- **Consumido por**: `pncp_crawler_adapter.py` (monitor.py), `bids_crawler.py` (via AsyncPNCPClient)
- **Rate limiting**: Batch delay configravel (1-2s entre batches)
- **Truncation detection**: GTM-FIX-004 monitora paginacao esgotada

### 9.2 DOM-SC (Diario Oficial dos Municipios de SC)
- **URL**: `https://www.diariomunicipal.sc.gov.br`
- **Metodo**: HTTP com API Key
- **Auth**: `DOM_SC_API_KEY` (header/cookie)
- **Consumido por**: `dom_sc_crawler.py`
- **Cobertura**: ~280 municipios SC (contratos de todos os 295 municipios via EXT-009)

### 9.3 PCP v2 (Portal de Compras Publicas)
- **URL**: `https://compras.api.portaldecompraspublicas.com.br/v2`
- **Metodo**: API REST
- **Auth**: Nao requer (publica)
- **Consumido por**: `pcp_crawler.py`
- **Cobertura**: ~100+ municipios SC

### 9.4 ComprasGov v3 (Compras Federais)
- **URL**: `https://dadosabertos.compras.gov.br`
- **Metodo**: API REST
- **Auth**: Nao requer (dados abertos)
- **Consumido por**: `compras_gov_crawler.py`
- **Cobertura**: Orgaos federais em SC

### 9.5 BrasilAPI (Enriquecimento CNPJ)
- **URL**: `https://brasilapi.com.br/api/cnpj/v1/{cnpj}`
- **Metodo**: GET
- **Auth**: Nao requer
- **Consumido por**: `enricher.py`
- **Rate limit**: Nao documentado; semaforo asyncio(10) concorrente

### 9.6 IBGE API (Enriquecimento Geo)
- **URL**: `https://servicodados.ibge.gov.br/api/v1/localidades/municipios`
- **Metodo**: GET
- **Auth**: Nao requer
- **Consumido por**: `enricher.py` (municipios + codigos IBGE)
- **Cache**: Module-level cache com 7 dias de TTL

### 9.7 OpenAI API (Classificacao + Embeddings)
- **URL**: `https://api.openai.com/v1`
- **Metodo**: REST (chat completions + embeddings)
- **Auth**: `OPENAI_API_KEY`
- **Consumido por**: `intel_llm_gate.py`, `loader.py` (STORY-438)
- **Modelos**: GPT-4.1-nano (classificacao), text-embedding-3-small (embeddings)

---

## 10. Security Observations

| Observacao | Severidade | Detalhe |
|-----------|------------|---------|
| **Chaves OpenAI e DOM-SC em .env** | OK | Segue 12-factor, .env gitignored |
| **Database DSN com senha** | OK | Em .env, nao commitado |
| **Nenhuma autenticacao no datalake** | ATENCAO | PostgreSQL exposto em Hetzner sem firewall de aplicacao — apenas network-level |
| **SQL queries concatenadas** | MEDIO | `monitor.py` usa f-strings para SQL (linha 67-68) — risco teorico de SQL injection |
| **Nenhum rate limiting no crawler** | INFORMATIVO | Delay via config, mas sem respeitar headers RateLimit-* das APIs |
| **Nenhuma criptografia em repouso** | INFORMATIVO | Dados publicos de licitacao, baixo risco |
| **Sem logging estruturado** | BAIXO | logging basico sem correlation IDs |
| **API Keys em env vars do sistema** | OK | Nao hardcoded, mas sem rotacao automatica |

---

## 11. Database Schema (Core Tables)

### `pncp_raw_bids`
Tabela central que unifica todas as fontes. Schema definido na migration 001.
- **PK**: `pncp_id` (TEXT)
- **Indexes**: GIN para full-text search (portugues), indexes por uf, modalidade, valor, orgao_cnpj, matched_entity_id
- **Features**: content_hash para dedup, tsv para full-text search, soft-delete via is_active
- **Trigger**: Auto-update updated_at via `set_updated_at()`

### `pncp_supplier_contracts`
Contratos de fornecedores (migration 002).

### `enriched_entities`
Cache de enriquecimento (BrasilAPI, IBGE) com TTL de 30 dias (migration 003).
- **PK**: (entity_type, entity_id)
- **entity_type**: 'fornecedor' | 'municipio'

### `sc_public_entities`
Catalogo de 2.085 orgaos publicos de SC (migration 007).
- Seed a partir de planilha Excel via `db/seed/001_sc_entities.py`
- Campo `raio_200km` para filtro geografico

### `entity_coverage`
Tracking de cobertura por entidade por fonte (migration 009).
- Atualizado automaticamente via AFTER INSERT/UPDATE triggers
- Janela de 90 dias para `is_covered`

### `ingestion_runs` / `ingestion_checkpoints`
Auditoria de execucao e checkpoints para crawl resumable (migration 004).

---

## 12. Recommendations (Architect)

### Curto Prazo (Sprint 0)

1. **TD-001 Critical**: Corrigir imports quebrados para `ingestion/` no `bids_crawler.py` -- o arquivo referencia pacotes que nao existem no diretorio `scripts/crawl/` (importa de `ingestion._base.crawler`, `ingestion.config`, `ingestion.transformer`, etc.). Criar o package ou remover o arquivo orphan.

2. **TD-009 Critical**: Implementar test suite basica com pytest -- o projeto tem 64k linhas e zero testes automatizados. Priorizar testes para o transformer (funcao pura, deterministico) e entity matching.

3. **TD-016 High**: Consolidar as duas implementacoes de crawler PNCP (`monitor.py` sincrono via adapter vs `bids_crawler.py` assincrono) em uma unica via.

### Medio Prazo (Sprint 1-2)

4. **TD-011**: Refatorar `monitor.py` (~687 linhas) separando entity matching em modulo proprio.

5. **TD-008**: Migrar constantes espalhadas (`_BRASILAPI_BASE`, `_ENRICH_STALENESS_DAYS`, etc.) para `config/settings.py`.

6. **TD-003**: Adicionar type hints em todas as funcoes publicas, especialmente `_match_entities_cascade`.

7. **SQL injection**: Substituir f-strings em queries SQL por parametros `%s` ou usar SQLAlchemy/psycopg2.sql.

### Longo Prazo

8. **Pipeline CI/CD**: Adicionar GitHub Actions para lint (ruff), type check (mypy) e testes.

9. **Healthcheck**: Criar script unificado de saude do sistema (conexao DB, APIs externas, cobertura).

10. **Schema Validation**: Adicionar Pydantic ou dataclasses para validacao de config YAML.

---

**Documento gerado por Aria. Total: ~64k linhas de codigo analisadas em 8 crawlers + 7-step pipeline + 12 migrations SQL + 22 services systemd.**
