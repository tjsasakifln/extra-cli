# Análise Técnica — Extra Consultoria

> Gerado pelo Archaeologist em 2026-07-13
> Reexecução completa — 17 módulos, 137K LOC Python
> doc_level: completo

---

## Módulo 1: crawl (51 .py, ~65K LOC)

**Propósito:** Crawlers web, pipeline de ingestão, orquestração e monitoramento de fontes de licitações B2G.

### Arquitetura

```
crawl/
├── monitor.py              # Orquestrador central (71K, 21 funções)
├── transparencia_crawler.py# Crawler de transparência genérico (57K)
├── contracts_crawler.py    # Crawler de contratos PNCP (29K)
├── ciga_ckan_crawler.py    # Crawler CIGA/CKAN (34K)
├── tce_sc_crawler.py       # Crawler TCE-SC (26K)
├── doe_sc_crawler.py       # Crawler DOE-SC (28K)
├── selenium_crawler.py     # Crawler Selenium genérico (28K)
├── enricher.py             # Enriquecimento (IBGE, geocode) (25K)
├── sync_client.py          # HTTP síncrono com retry (26K)
├── async_client.py         # HTTP assíncrono com retry (29K)
├── checkpoint.py           # Checkpoint de crawls incrementais (14K)
├── circuit_breaker.py      # Circuit breaker pattern (21K)
├── sanctions.py            # Verificação de sanções (23K)
├── clients/                # APIs tipadas
│   ├── base/               # Interface base (CrawlRequest, FetchResult)
│   └── pncp/               # PNCP API client (5 arquivos)
├── ingestion/              # Pipeline de ingestão (6 arquivos)
│   └── _base/crawler.py    # Base class com retry/circuit breaker
└── transparencia_templates/ # Templates por portal (7 arquivos)
```

### Algoritmos Principais

| Algoritmo | Arquivo | Descrição |
|-----------|---------|-----------|
| `crawl_source()` | `monitor.py` | Orquestração de crawl: carrega crawler → carrega entidades → faz match cascade → faz crawl → upsert no banco → projeta evidência |
| `_match_entities_cascade()` | `monitor.py` | Matching em cascata: CNPJ exato → nome+município → fuzzy, com população de evidência por entidade |
| `_project_entity_evidence()` | `monitor.py` | Projeta estado de evidência por (entity, source, data_type, run_id) no coverage_evidence ledger |
| Circuit Breaker | `circuit_breaker.py` | 3 estados: CLOSED → OPEN (após N falhas) → HALF_OPEN (após timeout). Config por fonte. |
| Retry com Backoff | `retry.py`, `sync_client.py` | Exponential backoff com jitter, max 3 tentativas, timeout configurável |
| Checkpoint | `checkpoint.py` | Paginação por data: salva último cursor, retoma de onde parou. Idempotente. |

### Crawlers por Fonte

| Crawler | Fonte | Método | LOC |
|---------|-------|--------|-----|
| `pncp_crawler_adapter.py` | PNCP API | REST | 19K |
| `pncp_arp_crawler.py` | PNCP ARP | REST | 17K |
| `pncp_pca_crawler.py` | PNCP PCA | REST | 16K |
| `contracts_crawler.py` | PNCP Contratos | REST | 29K |
| `compras_gov_crawler.py` | Compras.gov | REST | 22K |
| `tce_sc_crawler.py` | TCE-SC | Scraping | 26K |
| `doe_sc_crawler.py` | DOE-SC | Scraping | 28K |
| `doe_sc_selenium_crawler.py` | DOE-SC | Selenium | 19K |
| `dom_sc_crawler.py` | DOM-SC | Scraping | 21K |
| `ciga_ckan_crawler.py` | CIGA/CKAN | CKAN API | 34K |
| `sc_compras_crawler.py` | SC Compras | Scraping | 19K |
| `mides_bigquery_crawler.py` | MIDES/BigQuery | BigQuery API | 22K |
| `transparencia_crawler.py` | Portais Transparência | Scraping | 57K |
| `selenium_crawler.py` | Genérico | Selenium | 28K |

### Padrões de Erro

- 🟢 `CircuitBreakerOpenError` — circuito aberto, skip fonte
- 🟢 `RetryExhaustedError` — tentativas esgotadas
- 🟢 `CrawlAuthError` — credenciais inválidas
- 🟢 `CrawlParseError` — resposta não parseável
- 🟢 `CrawlTransformError` — parse OK, transform falhou
- 🟢 `CrawlPersistError` — transform OK, persist falhou

---

## Módulo 2: opportunity_intel (16 .py, ~15K LOC)

**Propósito:** Inteligência de licitações abertas, QW-01 Radar operacional, ranking competitivo, scoring.

### Arquitetura

```
opportunity_intel/
├── cli.py            # CLI 8 comandos (23K)
├── radar.py          # QW-01 Radar orquestração (33K)
├── crawler_base.py   # Base de crawlers opportunity (23K)
├── transformer.py    # Transformador source→canonical (18K)
├── status.py         # Cálculo de status canônico (16K)
├── pncp_audit.py     # Auditoria PNCP open monitoring (20K)
├── ranking.py        # Competitive intelligence (14K)
├── scoring.py        # Data confidence + client fit (9K)
├── models.py         # Dataclass models + constants (8K)
├── schema.py         # DDL + schema fingerprint (5K)
├── dedup.py          # Deduplicação content-hash (7K)
├── backfill.py       # Backfill histórico (14K)
├── manifest.py       # Manifestos de cobertura (12K)
├── profile.py        # Perfis de cliente (5K)
└── pncp_crawler.py   # PNCP crawler específico (5K)
```

### Algoritmos Principais

#### QW-01 Radar (`radar.py`)

```
Pipeline:
1. load_canonical_universe() → 1093 entidades spreadsheet
2. validate_qw01_schema() → fingerprint do schema
3. run_pncp_open_monitoring() → PNCP open proposals endpoint
4. Para cada registro:
   a. resolve no universo canônico (CNPJ8 match)
   b. calcula status canônico (source_map + temporal + heuristic)
   c. score_opportunity() → data_confidence + client_fit
   d. classifica: PRIORITARIA | REVISAR | DESCARTAR
5. Gera: CSV + JSON + coverage manifest
6. Exit code: 0 (≥95% monitoring coverage) | 2 (<95%)
```

#### Status Canônico (`status.py`)

Pipeline de decisão com 3 níveis:
1. **Source-specific maps** (PNCP: 16 valores, DOM-SC: 11 valores)
2. **Temporal evidence**: data_encerramento no futuro → `open`, no passado → `closed`
3. **Heuristic fallback**: modalidades "abertas" (dispensa, inexigibilidade) com janela de 90 dias → `open`, >365 dias → `closed`

#### Ranking (`ranking.py`)

Sistema determinístico com 3 categorias:
- **HARD_BLOCKS** (6 regras): status terminal, sem objeto, sem órgão, fora do raio
- **POSITIVE_FACTORS** (9 regras): status open, data futura, órgão conhecido, modalidade competitiva
- **NEGATIVE_FACTORS** (9 regras): status unknown, sem data, sem valor, fonte baixa confiança

Score 0-100 → GO (≥70) | REVIEW (40-69) | NO_GO (<40)

#### Scoring (`scoring.py`)

2 scores independentes para triagem humana:
- `data_confidence_score` (0-100): fonte oficial, status comprovado, URL disponível, entity match, freshness, integridade
- `client_fit_score` (0-100): match com termos positive/negative do perfil, categoria de objeto, raio
- Triage: PRIORITARIA | REVISAR | DESCARTAR

### Entidades

- 🟢 `OpportunityRecord` — 35 campos, representação canônica de licitação
- 🟢 `RadarExecution` — metadados de execução imutável (run_id, readiness, git_sha, schema_fingerprint)
- 🟢 `RadarScores` — data_confidence + client_fit + triage + fatores

---

## Módulo 3: contract_intel (3 .py, ~60K LOC)

**Propósito:** Contract Intelligence — consulta de contratos históricos, ranking de fornecedores, contratos expirando, readiness manifest.

### Arquitetura

```
contract_intel/
├── cli.py              # CLI contratos (47K)
└── target_universe.py  # Universo-alvo determinístico 200 km (12K)
```

### Algoritmos Principais

#### Target Universe (`target_universe.py`)

```
1. Carrega seed spreadsheet (Extra - alvos de licitação. R-0.xlsx)
2. Para cada linha: extrai CNPJ8, município, natureza jurídica, coordenadas
3. Calcula Haversine distance de Florianópolis (-27.5954, -48.5480)
4. Flag raio_200km: SIM ✓ se distância ≤ 200.0 km
5. Detecta CNPJ8 duplicados (reporta, não deduplica silenciosamente)
6. Entidades sem coordenadas: EXCLUDED + flagged
```

Regra de inclusão: `Haversine(lat, lon, -27.5954, -48.5480) ≤ 200.0 km, Earth radius 6371 km`

#### Contract Intel CLI (`cli.py`)

Comandos:
- `historical` — contratos históricos (3 anos) via `v_contract_historical`
- `suppliers` — ranking de fornecedores via `v_supplier_winners` (qtd, valor, ticket médio, HHI)
- `expiring` — contratos expirando em 90-180 dias via `v_expiring_contracts`
- `manifesto` — readiness per-capability com denominadores conservadores
- `export` — CSV/JSON

Semântica de valor: `valor_global` de PNCP NÃO é "preço praticado" — é o valor global do contrato assinado (semântica CONTRATADO, não PAGO).

---

## Módulo 4: lib (15 .py, ~12K LOC)

**Propósito:** Biblioteca compartilhada — universo canônico, geocodificação, normalização, semântica de valores.

### Componentes

| Arquivo | LOC | Função |
|---------|-----|--------|
| `universe.py` | 14K | `CanonicalUniverse` — 1093 entidades do spreadsheet, resolução por CNPJ8 |
| `doc_templates.py` | 14K | Templates de documentos (propostas, relatórios) |
| `entity_hierarchy.py` | 13K | Hierarquia de entes (município → estado → federação) |
| `geocode.py` | 12K | Haversine distance, cache IBGE, coordenadas municipais |
| `name_normalizer.py` | 10K | Normalização de nomes (acentos, abreviações, pontuação) |
| `value_semantics.py` | 9K | 5 estágios de valor: ESTIMADO, HOMOLOGADO, CONTRATADO, PAGO, GLOBAL |
| `victory_profile.py` | 12K | Perfil de vitória do cliente (modalidades, faixas de valor, regiões) |
| `bid_simulator.py` | 12K | Simulador de licitações (probabilidade de vitória, cenários) |
| `cost_estimator.py` | 10K | Estimador de custos de participação |
| `win_loss_tracker.py` | 5K | Tracking de win/loss por licitação |
| `cli_validation.py` | 5K | Validação de argumentos CLI |
| `intel_logging.py` | 1K | Configuração de logging para pipeline de inteligência |
| `retry.py` | 3K | Retry genérico |
| `constants.py` | 1K | Constantes compartilhadas |

### Algoritmos Chave

#### CanonicalUniverse (`universe.py`)

```python
CanonicalUniverse(
    seed_path="Extra - alvos de licitação. R-0.xlsx",
    seed_sha256=<hash>,
    radius_km=200.0,
    entities=[CanonicalEntity, ...],  # 1093
)

# Propriedades:
.included             # dentro do raio (within_radius=True)
.excluded             # fora do raio
.unresolved           # sem coordenadas
.conservative_monitoring_population  # included + unresolved (nunca subestima)
.resolution_coverage  # % de entidades com decisão de raio
```

#### Value Semantics (`value_semantics.py`)

```python
class ValorSemantica(Enum):
    ESTIMADO = "valor_estimado"    # Edital — PNCP bids
    HOMOLOGADO = "valor_homologado"# Award — ComprasGov
    CONTRATADO = "valor_contratado"# Contrato assinado — PNCP contracts
    PAGO = "valor_pago"           # Disbursement — TCE/SC empenhos
    GLOBAL = "valor_global"       # Undifferentiated — PNCP default (NÃO é "preço praticado")

SOURCE_VALUE_TYPES = {
    "pncp": {"bids": ESTIMADO, "contracts": CONTRATADO},
    "compras_gov": {"bids": HOMOLOGADO},
    "tce_sc": {"contracts": PAGO},
}
```

#### Name Normalizer (`name_normalizer.py`)

Pipeline: NFKD normalize → uppercase → strip acentos → expande abreviações (20 padrões) → remove pontuação → remove CNPJ → trim

Abreviações: SEC→SECRETARIA, MUN→MUNICIPIO, PM→PREFEITURA MUNICIPAL, FMS→FUNDO MUNICIPAL DE SAUDE, etc.

---

## Módulo 5: matching (3 .py, ~28K LOC)

**Propósito:** Entity matching cascade de 3 níveis para associar bids a entidades públicas.

### Algoritmo Cascade

```
Nível 1 — CNPJ Exact Match (8 dígitos)
  ├─ Match exato no CNPJ8
  └─ Confidence: HIGH (🟢)

Nível 2 — Normalized Name + Município
  ├─ Normaliza nome (remove acentos, expande abreviações)
  ├─ Match exato de nome normalizado + município
  └─ Confidence: HIGH (🟢)

Nível 2b — Alias Matching
  ├─ Siglas e padrões conhecidos (ex: "PM de X" ↔ "Prefeitura Municipal de X")
  └─ Confidence: HIGH (🟢)

Nível 3 — Fuzzy Matching
  ├─ rapidfuzz (fallback: difflib)
  ├─ Threshold padrão: 0.85
  ├─ Threshold cidades pequenas (<5000 hab): 0.75
  └─ Confidence: HIGH (>0.90) | MEDIUM (0.85-0.90) | LOW (0.75-0.85)
```

### Parâmetros Configuráveis

| Parâmetro | Default | Env Var |
|-----------|---------|---------|
| Fuzzy threshold | 0.85 | `ENTITY_MATCH_FUZZY_THRESHOLD` |
| Fuzzy threshold small city | 0.75 | `ENTITY_MATCH_FUZZY_THRESHOLD_SMALL_CITY` |
| Small city population | 5000 | `SMALL_CITY_POPULATION_THRESHOLD` |
| Log unknown abbreviations | true | `ENTITY_MATCH_LOG_UNKNOWN_ABBREVIATIONS` |

---

## Módulo 6: coverage (4 .py, ~44K LOC)

**Propósito:** Cálculo, validação e projeção de cobertura de entidades.

### Componentes

| Arquivo | LOC | Função |
|---------|-----|--------|
| `validate_coverage.py` | 34K | Validador de cobertura com categorização de causa raiz |
| `calculator.py` | 5K | Calculadora de % cobertura por entidade/fonte |
| `measure_pncp_expansion.py` | 4K | Mede expansão incremental de cobertura PNCP |
| `run_matching.py` | 2K | Executa matching em lote |

### Mapa de Causa Raiz

24 naturezas jurídicas mapeadas para 8 categorias de causa raiz:

| Categoria | Descrição | % Estimado |
|-----------|-----------|------------|
| `sem_dados_publicos` | Entidade sem portal ou dados públicos acessíveis | ~50% |
| `sem_obrigacao_legal_14133` | Fora do escopo da Lei 14.133 (estatais, judiciário) | ~15% |
| `dom_sc_sem_api_key` | Portal DOM-SC requer chave de API | ~5% |
| `icp_brasil_necessario` | Requer certificado digital ICP-Brasil | ~3% |
| `portal_offline` | Portal temporariamente indisponível | ~2% |
| `entidade_inativa` | Entidade extinta ou inativa | ~1% |
| `nao_investigado` | Ainda não investigado | ~24% |

---

## Módulo 7: reports (4 .py, ~64K LOC)

**Propósito:** Relatórios PDF/Excel executivos.

| Arquivo | LOC | Função |
|---------|-----|--------|
| `coverage_weekly.py` | 44K | Relatório semanal de cobertura (PDF + Excel) |
| `panorama.py` | 12K | Panorama setorial |
| `coverage_gaps.py` | 7K | Análise de gaps de cobertura |

---

## Módulo 8: fix (7 .py, ~165K LOC)

**Propósito:** Scripts de reparo, backfill e ativação de fontes dormentes.

| Arquivo | LOC | Função |
|---------|-----|--------|
| `scrape_residual_portals.py` | 51K | Scrape de portais residuais não cobertos |
| `activate_dormant_sources.py` | 34K | Ativação de fontes marcadas como dormentes |
| `sc_dados_abertos_backfill.py` | 21K | Backfill SC Dados Abertos |
| `resolve_unresolved_entities.py` | 16K | Resolução de entidades não resolvidas |
| `rebuild_evidence_ledger.py` | 15K | Reconstrução do evidence ledger |
| `geocode_missing_entities.py` | 13K | Geocodificação de entidades sem coordenadas |

---

## Módulo 9: pipeline (2 .py, ~34K LOC)

**Propósito:** Backfill multi-fonte.

- `backfill_multi_source.py` (34K): pipeline de backfill que percorre múltiplas fontes com checkpoint

---

## Módulo 10: diagnose (1 .py, ~25K LOC)

**Propósito:** Diagnóstico de crawlers.

- `dom_sc_diagnostic.py` (25K): diagnóstico detalhado do crawler DOM-SC

---

## Módulo 11: transparencia (1 .py, ~14K LOC)

**Propósito:** Detecção automática de portais de transparência municipais.

- `run_detect_all.py` (14K): detector automático de plataformas de portais

---

## Módulo 12: config

**Propósito:** Configuração centralizada do sistema.

| Arquivo | Tamanho | Função |
|---------|---------|--------|
| `settings.py` | 7K | Settings centralizados (paths, DB, APIs) |
| `constants.py` | 5K | Constantes de domínio |
| `sectors_config.yaml` | 61K | Config de 13 setores B2G |
| `sectors_data.yaml` | 177K | Dados setoriais (atividades, keywords) |
| `transparencia_config.yaml` | 19K | Config de portais de transparência |
| `municipio_population.yaml` | 2K | População IBGE por município |
| `abbreviations.yaml` | 1K | Abreviações de nomes de entes |
| `logging_config.py` | 8K | Configuração de logging estruturado JSON |

---

## Módulo 13: db (33 + 8 migrations SQL)

**Propósito:** Schema do banco de dados PostgreSQL + PostGIS.

### Tabelas Principais

| Tabela | Migration | Propósito |
|--------|-----------|-----------|
| `pncp_raw_bids` | 001 | Licitações brutas PNCP |
| `pncp_supplier_contracts` | 002 | Contratos de fornecedores |
| `enriched_entities` | 003 | Entidades enriquecidas |
| `ingestion_checkpoints` | 004 | Checkpoints de ingestão |
| `sc_public_entities` | 007 | Entes públicos SC (raio 200km) |
| `entity_coverage` | 009 | Cobertura por entidade |
| `coverage_snapshots` | 012 | Snapshots históricos de cobertura |
| `coverage_evidence` | 024 | Evidence ledger auditável |
| `opportunity_intel` | 027 | Licitações abertas |
| `opportunity_checkpoints` | 027 | Checkpoints de paginação |
| `opportunity_runs` | 027 | Execuções de crawl |
| `opportunity_coverage` | 027 | Cobertura por entidade/fonte |

### Views Analíticas

| View | Migration | Propósito |
|------|-----------|-----------|
| `v_contract_historical` | 026 | Contratos históricos (3 anos, 200km) |
| `v_supplier_winners` | 026 | Ranking de fornecedores (qtd, valor, HHI) |
| `v_expiring_contracts` | 026 | Contratos expirando 90-180 dias |
| `v_contract_intel_percentis` | 025 | P25/P50/P75 por categoria |

### Functions/RPCs

- `search_datalake` — busca full-text com GIN index
- `upsert_pncp_raw_bids` — upsert idempotente
- `upsert_pncp_supplier_contracts` — upsert idempotente
- `purge_old_records` — purga registros expirados
- `refresh_entity_coverage` — recalcula cobertura

### Índices

- GIN: `objeto_contrato`, `objeto_compra` (full-text search)
- HNSW: embedding vectors (entity matching)
- B-tree: CNPJ, datas, status, UF, município, modalidade, ranking

---

## Módulo 14: deploy (20 systemd timer pairs)

**Propósito:** Orquestração de crawlers na VPS via systemd.

### Timers

| Timer | Frequência | Função |
|-------|-----------|--------|
| `pncp-crawl-inc.timer` | Horária | Crawl incremental PNCP |
| `pncp-crawl-full.timer` | Semanal | Crawl full PNCP |
| `pncp-contracts.timer` | Diária | Contratos PNCP |
| `pncp-enrich.timer` | Diária | Enriquecimento |
| `pncp-purge.timer` | Semanal | Purga registros antigos |
| `pncp-report-weekly.timer` | Semanal | Relatório semanal |
| `compras-gov-crawl.timer` | Diária | Compras.gov |
| `tce-sc-crawl.timer` | Diária | TCE-SC |
| `dom-sc-crawl.timer` | Diária | DOM-SC |
| `pcp-crawl.timer` | Diária | PCP |
| `sc-compras-crawl.timer` | Diária | SC Compras |
| `transparencia-crawl.timer` | Diária | Portais transparência |
| `ciga-ckan-crawl.timer` | Semanal | CIGA/CKAN |
| `doe-sc-crawl.timer` | Diária | DOE-SC |
| `selenium-crawl.timer` | Diária | Crawlers Selenium |
| `coverage-report.timer` | Semanal | Relatório cobertura |
| `coverage-report-weekly.timer` | Semanal | Relatório semanal detalhado |
| `extra-db-backup.timer` | Diária | Backup banco |
| `extra-health-check.timer` | Horária | Health check |
| `extra-collect-metrics.timer` | Horária | Coleta métricas |
| `extra-check-alerts.timer` | 30min | Verificação alertas |

### OnFailure

`onfailure@.service` — template para notificação em falha de qualquer serviço.

---

## Módulo 15: root_scripts (~40 entry points CLI)

**Propósito:** Scripts de entry point de alto nível que orquestram funcionalidades de negócio.

### Scripts Core

| Script | LOC | Função |
|--------|-----|--------|
| `intel_pipeline.py` | 50K | Pipeline inteligência (7 stages + 5 gates) |
| `intel_collect.py` | 138K | Coleta de inteligência multi-fonte |
| `intel_analyze.py` | 71K | Análise de dados de inteligência |
| `intel_report.py` | 99K | Geração de relatório executivo |
| `intel_enrich.py` | 25K | Enriquecimento de dados |
| `intel_validate.py` | 41K | Validação de qualidade |
| `intel_llm_gate.py` | 14K | Gate LLM GPT-4.1 Nano |
| `intel_excel.py` | 41K | Export Excel |
| `intel_sector_loader.py` | 19K | Carga de setores |

### Gates

| Script | LOC | Função |
|--------|-----|--------|
| `consulting_readiness.py` | 88K | Consulting Readiness Gate (≥95%) |
| `coverage_truth.py` | 39K | Coverage Truth assessment |
| `freshness_gate.py` | 10K | Freshness Gate SLA (SLA configurável) |

### PDFs (Big Four)

| Script | LOC | Função |
|--------|-----|--------|
| `generate_consultoria_pdf.py` | 66K | PDF Consultoria Estratégica |
| `generate_proposta_pdf.py` | 44K | PDF Proposta Comercial |
| `generate_report_b2g.py` | 287K | Relatório B2G completo |
| `collect_report_data.py` | 440K | Coleta de dados para relatórios |

### Outros

| Script | LOC | Função |
|--------|-----|--------|
| `local_datalake.py` | 26K | CLI DataLake (search, supplier, stats) |
| `demo_b2g_setorial.py` | 48K | Demo B2G Setorial |
| `health-dashboard.py` | 16K | Dashboard de saúde |
| `notify.py` | 10K | Notificações |
| `check-alerts.py` | 20K | Verificação de alertas |
| `collect-metrics.py` | 14K | Coleta de métricas |

---

## Módulo 16: tests (64 arquivos)

**Propósito:** Testes automatizados.

### Cobertura por Módulo

| Área | Testes | Tipo |
|------|--------|------|
| Crawlers | `test_ciga_ckan_crawler.py`, `test_tce_sc_live.py`, `test_compras_gov_crawler.py`, `test_pcp_crawler.py`, `test_doe_sc_crawler.py`, `test_sc_compras_crawler.py`, `test_transparencia_crawler.py`, `test_contracts_crawler.py`, `test_crawler_pncp.py`, `test_crawler_protocol.py` | Unit + Integration |
| Opportunity | `test_opportunity_models.py`, `test_opportunity_dedup.py`, `test_opportunity_ranking.py`, `test_opportunity_transformer.py`, `test_opportunity_integration.py`, `test_opportunity_status.py` | Unit + Integration |
| QW-01 | `test_qw01_radar.py`, `test_qw01_postgres.py` | Integration |
| Contract Intel | `test_contract_intel_cli.py`, `test_contract_intel_crawl.py`, `test_contract_intel_target.py`, `test_contract_intel_truth_v1.py` | Unit + Integration |
| Coverage | `test_coverage_truth.py`, `test_coverage_calculator.py`, `test_coverage_only_evidence.py`, `test_evidence_projection_db.py` | Unit + Integration |
| Readiness | `test_consulting_readiness.py`, `test_freshness_gate.py`, `test_backfill_pipeline.py` | Integration |
| Matching | `test_entity_matcher.py`, `test_name_normalizer` | Unit |
| Lib | `test_geocode.py`, `test_cache_ibge.py`, `test_entity_hierarchy.py`, `test_manifest.py`, `test_universe.py`, `test_common.py`, `test_transformer.py`, `test_report_dedup.py` | Unit |
| Pipeline | `test_intel_pipeline.py`, `test_backfill_count_covered.py`, `test_pncp_pipeline_db.py` | Integration |
| Smoke | `smoke/` | E2E |

---

## Módulo 17: docs (590 arquivos)

**Propósito:** Documentação completa do projeto.

### Estrutura

```
docs/
├── architecture/       # Arquitetura do sistema
├── stories/            # Stories de desenvolvimento
│   └── epics/          # 7 epics ativos
│       ├── epic-001-100-cobertura/
│       ├── epic-coverage-100pct/
│       ├── epic-feat-001-crawlers-coverage/
│       ├── epic-master-b2g/
│       ├── epic-td-001-resolution/
│       ├── epic-td-002-code-quality/
│       └── epic-td-003-reversa-remediation/
├── prd/                # PRDs
├── decisions/          # ADRs
├── coverage-truth/     # Coverage truth documentation
├── ops/                # Runbooks operacionais
├── qa/                 # QA gates, CodeRabbit reports
├── assessments/        # Avaliações técnicas
├── research/           # Pesquisas (ex: TCE-SC Esfinge)
├── guides/             # Guias
├── reports/            # Relatórios
├── reviews/            # Revisões
├── workplans/          # Planos de trabalho
└── frontend/           # Documentação frontend (nova)
```

---

## Resumo Cross-Modular

### Pipelines de Dados

```
[Spreadsheet Seed] → CanonicalUniverse (lib/universe.py)
                    → sc_public_entities (db)
                    ↓
[Fontes Externas] → Crawlers (crawl/*)
                  → Ingestão (crawl/ingestion/)
                  → Enriquecimento (crawl/enricher.py)
                  ↓
[DB PostgreSQL] → coverage_evidence (024)
                → entity_coverage (009)
                → opportunity_intel (027)
                → pncp_supplier_contracts (002)
                ↓
[Análise] → consulting_readiness.py
          → coverage_truth.py
          → freshness_gate.py
          → radar.py (QW-01)
          → contract_intel/cli.py
          ↓
[Output] → PDFs (Big Four)
         → Excel
         → CSV/JSON
```

### Regras de Negócio Transversais

1. **Fail-closed**: nunca marcar como "aberto" por default. Status desconhecido → `unknown`.
2. **CNPJ8 match**: matching sempre usa 8 dígitos raiz do CNPJ.
3. **Determinístico primeiro**: ranking/scoring é determinístico. LLM é enriquecimento opcional, nunca requisito.
4. **Nunca "preço praticado"**: `valor_global` do PNCP é valor contratual, não reflete pagamentos efetivos.
5. **Denominador conservador**: população de monitoramento = incluídos + não resolvidos (nunca subestima).
6. **Evidência auditável**: toda cobertura tem registro no `coverage_evidence` ledger.
7. **Raio 200km**: Haversine distance de Florianópolis (-27.5954, -48.5480), Earth radius 6371 km.
8. **Deságio**: diferença entre valor estimado e homologado, NUNCA entre global e outro estágio.
9. **Competitive Intelligence**: market share, HHI, supplier ranking — apenas com dados contratuais confirmados.

### Complexidade por Módulo

| Módulo | Complexidade | Arquivos | LOC |
|--------|-------------|----------|-----|
| crawl | **VERY_HIGH** | 51 | 65K |
| root_scripts | **VERY_HIGH** | ~40 | 500K+ |
| opportunity_intel | HIGH | 16 | 15K |
| contract_intel | HIGH | 3 | 60K |
| fix | HIGH | 7 | 165K |
| reports | MEDIUM | 4 | 64K |
| coverage | MEDIUM | 4 | 44K |
| lib | MEDIUM | 15 | 12K |
| matching | LOW | 3 | 28K |
| pipeline | LOW | 2 | 34K |
| diagnose | LOW | 1 | 25K |
| transparencia | LOW | 1 | 14K |
| config | LOW | 7 | 12K |
