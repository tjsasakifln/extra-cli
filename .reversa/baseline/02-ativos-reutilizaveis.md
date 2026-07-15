# Ativos Reutilizaveis do Projeto

> Gerado em: 2026-07-14
> Proposito: Inventario de componentes prontos, CLIs funcionais, modelos de dados, queries e pipelines que podem ser reutilizados, estendidos ou integrados.

---

## 1. Opportunity Intelligence (`scripts/opportunity_intel/`)

Pipeline vertical ponta a ponta mais maduro do projeto. Localiza, consolida, deduplica, ranqueia e exporta licitacoes abertas.

### 1.1 CLI — `python scripts/opportunity_intel/cli.py`

Comandos operacionais ponta a ponta:

| Comando | Funcao | Arquivo |
|---------|--------|---------|
| `radar --profile ...` | Executa radar auditavel QW-01 completo | `radar.py` (846 linhas) |
| `list --status open --limit 20` | Lista oportunidades com filtros | `cli.py:cmd_list` |
| `show 42` | Detalhes completos de uma oportunidade | `cli.py:cmd_show` |
| `explain 42` | Explica fatores de ranking de uma oportunidade | `cli.py:cmd_explain` |
| `coverage` | Dashboard de cobertura por entidade | `cli.py:cmd_coverage` |
| `source-health` | Health check por fonte (PNCP etc) | `cli.py:cmd_source_health` |
| `update --source pncp` | Executa crawl para uma fonte especifica | `cli.py:cmd_update` |
| `export --format csv -o ops.csv` | Exporta para JSON ou CSV | `cli.py:cmd_export` |
| `briefing --dias 7` | Briefing diario com filtro AEC + SC + 200km | `cli.py:cmd_briefing` |

**Conexao:** PostgreSQL via `LOCAL_DATALAKE_DSN` (default: `postgresql://postgres@127.0.0.1:5433/pncp_datalake`)

### 1.2 Modelos de Dados (`models.py`)

- `OpportunityRecord` — dataclass canonica de 41 campos (identidade, ente, processo, objeto, valor, datas, status, documentos, qualidade, ranking, proveniencia)
- `CrawlRequest` — parametros de execucao (source, date_from, date_to, mode, limit, max_pages, max_records, page_size)
- `FetchResult` — wrapper de resposta HTTP (status, raw_data, error, page, total_pages, completion_rule)

### 1.3 Schema e Validacao (`schema.py`)

- `validate_qw01_schema(conn)` — inspeciona `information_schema` e valida colunas obrigatorias das tabelas: `coverage_evidence`, `opportunity_runs`, `opportunity_intel`, `sc_public_entities`
- `schema_fingerprint(conn)` — hash SHA-256 deterministico de colunas + constraints + indexes
- `connect_postgres(dsn)` — conexao fail-closed (rejeita SQLite)
- `GitIdentity` — branch + SHA atuais

### 1.4 Ranking Explicavel (`ranking.py`)

Motor de ranking deterministico (0-100) com 3 tiers:

- **GO** (>=70), **REVIEW** (40-69), **NO_GO** (<40)
- 6 regras de hard block (status terminal, data passada, sem objeto, sem orgao, valor negativo, fora do raio)
- 9 fatores positivos (status_open, data_abertura_futura, orgao_conhecido, valor_realista, modalidade_competitiva, documentos_completos, dentro_raio, fonte_confiavel, dados_completos)
- 10 fatores negativos (status_unknown, sem_data_abertura, sem_valor, etc.)
- Funcao principal: `compute_ranking(...)` — 15 parametros, retorna dict com ranking/score/fatores/regras/confianca
- Classificacao de modalidades: 11 competitivas, 11 nao-competitivas

### 1.5 Scoring Hibrido (`scoring.py`)

Sistema de dois scores independentes:

- `RadarScores` — dataclass congelada com `data_confidence_score`, `client_fit_score`, `triage_recommendation` (PRIORITARIA/REVISAR/DESCARTAR)
- `score_opportunity(row, entity, profile, status_evidence)` — combina pesos do perfil do cliente com dados da oportunidade
- 7 campos de missing fields monitorados
- Terminais: closed, suspended, revoked, annulled, failed

### 1.6 Transformer (`transformer.py`)

Normalizacao de registros brutos para `OpportunityRecord`:

- `normalize_pncp(raw)` — mapeia API PNCP (numeroControlePNCP, orgaoCNPJ, objeto, modalidadeNome, etc.)
- `normalize_dom_sc(raw)` — mapeia API DOM-SC (atos, categorias 6/7/28)
- `normalize_generic(raw, source)` — heuristicas para fontes desconhecidas
- `normalize_record(raw, source)` — dispatch automático para normalizador especifico ou fallback
- Helpers: `_parse_dt`, `_parse_dom_date`, `_infer_esfera`, `_extract_municipio_from_entidade`, `_extract_edital_from_title`

### 1.7 Deduplicacao (`dedup.py`)

4 niveis conservadores (sem similaridade textual):

1. `numero_controle_pncp` (ID oficial PNCP)
2. `source:source_id` (mesma fonte + mesmo ID)
3. `orgao_cnpj|processo|edital` (chave composta)
4. `content_hash` (hash MD5 de campos chave)

Funcoes: `compute_content_hash(record)`, `compute_dedup_keys(record)`, `find_duplicate(record, existing)`, `merge_sources(primary, secondary)`

### 1.8 Radar Auditavel QW-01 (`radar.py` — 846 linhas)

Pipeline completo que executa:

1. Validacao de schema + fingerprint + git identity
2. Carregamento do perfil do cliente (YAML)
3. Carregamento do universo canonico (planilha seed)
4. Execucao ou reuso de coleta PNCP
5. Carregamento de evidence coverage
6. Calculo de monitoring coverage (success/success_zero/partial)
7. Load + scoring de candidatos com dedup
8. Field readiness por 9 metricas
9. Source health e applicability
10. Geracao de artefatos (CSV, XLSX, JSON, summary.md)
11. 8 arquivos de output por execucao

### 1.9 Cobertura (`manifest.py`)

- Gera 3 arquivos em `output/readiness/`:
  - `opportunity-coverage-manifest.json` (universe, opportunities, freshness, readiness)
  - `opportunity-coverage-gaps.csv` (entidades sem dados)
  - `opportunity-source-health.csv` (frescura por fonte)
- Universo canonico: `scripts.lib.universe.CANONICAL_UNIVERSE` = 1093 entidades

### 1.10 Perfil de Cliente (`profile.py`)

`ClientProfile` — dataclass congelada com 17 campos de configuracao:

- `desired_object_types`: tipos de objeto desejados com termos associados
- `positive_terms` / `negative_terms`: termos de scoring
- `allowed_modalities`: modalidades permitidas
- `priority_distance_km`, `minimum_value`, `maximum_value`, `minimum_days_to_deadline`
- `weights`: pesos para data_confidence e client_fit
- `triage_thresholds`: limiares de triagem
- `hard_blocks`: bloqueios configurados (exclude_terminal, require_future_deadline, etc.)
- `documents`: requisitos de documentos

Arquivo: `scripts/opportunity_intel/profile.py`
Exemplo: `config/client_profiles/extra.yaml`

---

## 2. Buyer Intelligence (`scripts/buyer_intel/`)

Ranking e perfil de orgaos compradores. 2 arquivos.

### 2.1 CLI — `python scripts/buyer_intel/cli.py`

| Comando | Funcao |
|---------|--------|
| `ranking --limit 20` | Ranking de orgaos compradores |
| `perfil <cnpj_8>` | Perfil detalhado de um orgao |
| `ranking --format csv` | Exporta ranking como CSV |

### 2.2 Modelos e Motor (`ranking.py`)

- `BuyerProfile` — dataclass com 27 campos (contratos, AEC, valores, fornecedores, HHI, vencimentos, etc.)
- `BuyerRankingEntry` — dataclass com 9 fatores de score (aderencia 0-25, volume 0-20, frequencia 0-15, ticket 0-10, proximidade 0-10, oportunidades 0-10, renovacao 0-5, concentracao 0-5)
- `compute_buyer_ranking(profiles)` — normaliza por maximo, calcula scores, classifica (PRIORITARIO >=60, ATIVO >=40, REVIEW >=20, BAIXA_PRIORIDADE <20)
- `AEC_KEYWORDS` — 40 keywords de engenharia/construcao
- `is_aec(objeto)` — classificador booleano por keywords

### 2.3 Queries Complexas

A funcao `fetch_buyer_profiles()` no `cli.py` implementa uma query SQL de 50 linhas com:

- CTE `buyer_stats`: agregacao de `pncp_supplier_contracts`
- CTE `supplier_concentration`: calculo HHI (Herfindahl-Hirschman Index)
- CTE `top_fornecedores`: top 3 fornecedores por orgao
- CTE `open_opportunities`: editais abertos por orgao
- Percentis P25/P50/P75 via `PERCENTILE_CONT`
- Classificacao AEC via regex de 40 keywords

### 2.4 Fallback Inteligente

- Tenta PostgreSQL primeiro (`LOCAL_DATALAKE_DSN`)
- Fallback para SQLite (`data/contract_intel.db`) se DSN vazio

---

## 3. Extra Ledger (`scripts/extra_ledger/`)

Ledger proprietario da construtora. 1 arquivo (`cli.py`, 471 linhas).

### 3.1 Armazenamento

JSON file-based em `data/extra_ledger.json` — sem dependencia de banco.

### 3.2 Comandos

| Comando | Funcao |
|---------|--------|
| `dashboard` | Visao consolidada do ledger |
| `oportunidade add --orgao ...` | Registra oportunidade avaliada |
| `oportunidade list` | Lista oportunidades |
| `proposta add --orgao ...` | Registra proposta enviada |
| `proposta resultado --id 1 --resultado vencedora` | Atualiza resultado |
| `proposta list` | Lista propostas com win rate |
| `contrato add --orgao ...` | Registra contrato |
| `contrato list` | Lista contratos |
| `contrato evento --id 1 --tipo aditivo` | Adiciona evento a contrato |
| `capacidade add ...` | Registra atestado/capacidade |

### 3.3 Estrutura de Dados

```json
{
  "version": 1,
  "cliente": "Extra Construtora",
  "oportunidades": [{"id", "orgao", "edital", "objeto", "valor_estimado", "decisao", "confianca", "pncp_id"}],
  "propostas": [{"id", "orgao", "edital", "valor_proposta", "status", "resultado_data", "motivo_perda"}],
  "contratos": [{"id", "orgao", "numero_contrato", "valor", "status", "aditivos", "medicoes", "marcos"}],
  "capacidades": [{"id", "tipo", "descricao", "orgao_emissor", "validade", "categoria"}]
}
```

---

## 4. Crawlers de Contrato e Licitação (`scripts/crawl/`)

53 arquivos Python. 11 fontes registradas no registry central.

### 4.1 Registry Central (`registry.py`)

Fonte unica de verdade para todas as fontes. `SourceInfo` dataclass com:

- `name`, `aliases`, `module`, `purpose` (bids/contracts/coverage_only/hybrid)
- `authority_level` (federal/estadual/municipal/multi)
- `capabilities` (open_tenders, historical_contracts, competitors, prices, entity_matching, coverage_truth, source_health)
- `snapshot_semantics`, `freshness_sla_hours`, `credential_names`

Funcoes: `iter_sources()`, `lookup()`, `resolve_name()`, `iter_choices()`

### 4.2 Fontes Registradas

| Nome | Modulo | Proposito | Nivel | Capabilities |
|------|--------|-----------|-------|-------------|
| `pncp` | `pncp_crawler_adapter` | bids | federal | open_tenders, historical_contracts, entity_matching |
| `dom_sc` | `dom_sc_crawler` | bids | municipal | open_tenders |
| `pcp` | `pcp_crawler` | bids | multi | open_tenders |
| `compras_gov` | `compras_gov_crawler` | bids | federal | open_tenders |
| `sc_compras` | `sc_compras_crawler` | bids | estadual | open_tenders |
| `contracts` | `contracts_crawler` | contracts | federal | historical_contracts, competitors |
| `transparencia` | `transparencia_crawler` | bids | municipal | open_tenders |
| `tce_sc` | `tce_sc_crawler` | bids | estadual | open_tenders, historical_contracts |
| `doe_sc` | `doe_sc_crawler` | bids | estadual | open_tenders |
| `ciga_ckan` | `ciga_ckan_crawler` | coverage_only | municipal | coverage_truth |
| `mides_bigquery` | `mides_bigquery_crawler` | bids | estadual | open_tenders |

### 4.3 Orquestrador Principal (`monitor.py` — 1517 linhas)

Pipeline completo por fonte:

1. **Crawler discovery**: `_load_crawler(source)` via importlib dinâmico
2. **Credential validation**: `validate_source_credentials(source)`
3. **Phase 1 Crawl**: `crawler.crawl(CrawlRequest)` com fallback para string mode
4. **Phase 2 Transform**: `crawler.transform(records)` com normalizacao
5. **Phase 3 Upsert**: via funcao upsert configurada (`upsert_pncp_raw_bids` default)
6. **Phase 4 Entity Matching**: `match_entities_cascade()` do modulo unificado
7. **Phase 5 Engineering Classification** (PNCP only): `pncp_engineering.classify_engineering()`
8. **Projection de Entity Evidence**: `_project_entity_evidence()` para `coverage_evidence`
9. **Coverage Report**: `report_coverage(conn)` com dashboard completo

Comandos:
```bash
python scripts/crawl/monitor.py --source pncp --mode full
python scripts/crawl/monitor.py --source all --mode incremental
python scripts/crawl/monitor.py --report-coverage
```

### 4.4 Crawlers Específicos

| Arquivo | Fonte | Tecnica |
|---------|-------|---------|
| `pncp_crawler_adapter.py` | PNCP | API REST (pncp.gov.br) |
| `pncp_contract.py` | PNCP | Parsing de contratos (DEFAULT_MODALIDADES = [1-19]) |
| `pncp_engineering.py` | PNCP | Classificador de engenharia (score 0-100) |
| `pncp_geo.py` | PNCP | Resolvedor geografico com cache |
| `dom_sc_crawler.py` | DOM-SC | API REST |
| `doe_sc_crawler.py` | DOE-SC | Selenium com fallback |
| `doe_sc_selenium_crawler.py` | DOE-SC | Selenium puro |
| `pcp_crawler.py` | PCP | API REST |
| `compras_gov_crawler.py` | ComprasGov | API REST v3 |
| `sc_compras_crawler.py` | SC Compras | API REST |
| `contracts_crawler.py` | PNCP Contratos | API especializada |
| `transparencia_crawler.py` | Transparencia | Scraping multi-site |
| `tce_sc_crawler.py` | TCE-SC | API REST |
| `ciga_ckan_crawler.py` | CIGA | CKAN API |
| `mides_bigquery_crawler.py` | MIDES | BigQuery |
| `bids_crawler.py` | Generic | Crawler base generico |

### 4.5 Infraestrutura de Crawl

| Arquivo | Funcao |
|---------|--------|
| `config.py` | Configuracoes centralizadas |
| `rate_limiter.py` | Rate limiting por dominio |
| `retry.py` | Retry com backoff |
| `circuit_breaker.py` | Circuit breaker pattern |
| `checkpoint.py` | Checkpoint state management |
| `async_client.py` | Cliente HTTP async |
| `sync_client.py` | Cliente HTTP sync |
| `adapter.py` | Adaptador de crawler |
| `middleware.py` | Middleware pipeline |
| `loader.py` | Loader dinamico de crawlers |
| `transformer.py` | Transformacao generica de dados |
| `enricher.py` | Enriquecimento com dados externos (IBGE, geocode, CNPJ) |
| `metrics.py` | Métricas de execucao |
| `security.py` | Seguranca e sanitizacao |
| `exceptions.py` | Excecoes especializadas |
| `supabase_client.py` | Cliente Supabase (fallback) |
| `playwright_fallback.py` | Playwright para fallback de crawlers Selenium |
| `selenium_crawler.py` | Crawler Selenium generico |
| `selenium_crawler_adapter.py` | Adaptador Selenium |
| `selenium_smoke_test.py` | Smoke test para Selenium |
| `redis_pool.py` | Pool de conexoes Redis |
| `credential_validator.py` | Validador de credenciais |
| `sanctions.py` | Sancoes e bloqueios |

---

## 5. Relatorios (`scripts/reports/`)

4 arquivos Python.

### 5.1 Panorama (`panorama.py`)

Relatorio de panorama de mercado:

- `section_volume()` — volume por modalidade
- `section_municipios()` — top municipios por licitacao
- `section_orgaos()` — top orgaos contratantes
- `section_sazonalidade()` — distribuicao mensal
- `section_source_distribution()` — distribuicao por fonte
- `section_coverage_gaps()` — entidades sem cobertura (via `target_universe_entities`)
- Output: terminal + Excel + PDF

Uso: `python scripts/reports/panorama.py --setor engenharia --uf SC --dias 90 --output-excel`

### 5.2 Coverage Weekly (`coverage_weekly.py`)

Relatorio semanal de cobertura no estilo Big Four (McKinsey, BCG, Deloitte):

- Executive PDF (1-2 paginas, ReportLab)
- Detailed Excel (4 sheets, openpyxl)
- Snapshot diario de cobertura automatico

Uso: `python -m scripts.reports.coverage_weekly`

### 5.3 Coverage Gaps (`coverage_gaps.py`)

Exportacao de gaps de cobertura:

- `fetch_all_gaps()` — entidades descobertas via `v_coverage_gaps`
- `fetch_gaps_by_municipio()` — agregacao por municipio
- `export_excel()` — Excel com abas por municipio e natureza juridica
- Output: `output/reports/coverage/gaps-{date}.xlsx`

---

## 6. DataLake CLI (`scripts/local_datalake.py`)

684 linhas. Interface de consulta ao PostgreSQL DataLake.

### 6.1 Comandos

| Comando | Funcao | Tabela |
|---------|--------|--------|
| `search --uf SC --dias 30` | Busca editais com FTS | `search_datalake() RPC` |
| `supplier --cnpj X` | Consulta contratos de fornecedor | `pncp_supplier_contracts` |
| `pricing --keywords "obra,reforma"` | Estatisticas de precos | `pncp_supplier_contracts` |
| `competitors --keywords "engenharia"` | Top concorrentes | `pncp_supplier_contracts` |
| `detail --pncp-id X` | Detalhes de um edital | `pncp_raw_bids` |
| `stats` | Estatisticas de todas as tabelas | Todas |
| `coverage` | Dashboard de cobertura | `entity_coverage`, `coverage_snapshots` |
| `coverage --snapshot` | Gera snapshot diario | `generate_coverage_snapshot()` |
| `coverage --export` | Exporta gaps para Excel | `v_coverage_gaps` |

### 6.2 Capacidades do Search

- `search_datalake()` RPC com 12 parametros nomeados
- Filtros: UF, datas, modalidades, valor min/max, texto livre (`websearch_to_tsquery`)
- Modos: `publicacao` e `abertas`
- Output: terminal formatado ou JSON
- Full-text search via PostgreSQL tsquery

### 6.3 Capacidades do Pricing

- Calculo de estatisticas: P10, P25, median, P75, P90, mean, stddev, CV
- Filtro por keywords (AND), UF, periodo
- Amostra limitada a 1000 contratos

### 6.4 Tabelas Monitoradas pelo `stats`

14 tabelas core:
`pncp_raw_bids`, `pncp_supplier_contracts`, `enriched_entities`, `ingestion_checkpoints`, `ingestion_runs`, `search_results_cache`, `search_results_store`, `profiles`, `alerts`, `pipeline_items`, `leads`, `classification_feedback`, `organizations`, `digital_products`

---

## 7. Biblioteca Compartilhada (`scripts/lib/`)

16 arquivos de suporte.

| Arquivo | Funcao |
|---------|--------|
| `universe.py` | Universo canonico (1093 entidades, `CanonicalEntity`, `CanonicalUniverse`, `load_canonical_universe()`) |
| `universe_query.py` | Queries do universo canonico |
| `entity_hierarchy.py` | Hierarquia de entidades |
| `geocode.py` | Geocodificacao e calculo de distancias |
| `name_normalizer.py` | Normalizacao de nomes/razoes sociais |
| `cli_validation.py` | Validacao de argumentos CLI |
| `constants.py` | Constantes do projeto |
| `retry.py` | Retry com backoff |
| `intel_logging.py` | Logging estruturado |
| `value_semantics.py` | Semantica de valores monetarios |
| `terminal.py` | Utilitarios de terminal |
| `cost_estimator.py` | Estimativa de custos |
| `bid_simulator.py` | Simulacao de licitacoes |
| `doc_templates.py` | Templates de documentos |
| `victory_profile.py` | Perfil de vitoria |
| `win_loss_tracker.py` | Tracking de vitorias/perdas |

### 7.1 Universo Canonico (`universe.py`)

- `CANONICAL_UNIVERSE` = 1093 entidades (constante auditada)
- `CanonicalEntity` — dataclass com entity_id, razao_social, municipio, distancia_km, dentro_raio, etc.
- `CanonicalUniverse` — colecao com `conservative_monitoring_population` (entidades incluídas + unresolved)
- `load_canonical_universe(seed_path, conn)` — carrega da planilha seed + banco
- Metodos: `resolve_opportunity(cnpj, nome, municipio)`, `to_snapshot()`

---

## 8. Entity Matching (`scripts/matching/`)

3 arquivos.

| Arquivo | Funcao |
|---------|--------|
| `entity_matcher.py` | Matcher em cascata: CNPJ -> nome normalizado -> fuzzy |
| `measure_baseline.py` | Medicao de baseline de matching |

Funcao principal: `match_entities_cascade(conn, source, entities, pncp_ids)` — usada no monitor.py Phase 4.

---

## 9. Banco de Dados PostgreSQL

### 9.1 Instancias

| Porta | Nome Docker | Base |
|-------|-------------|------|
| 5432 | `recuperador-postgres` (postgres:16-alpine) | `pncp_datalake` |
| 5433 | Host nativo | `pncp_datalake` (recuperador) |
| 54399 | Host nativo | `postgres` (config.settings) |

### 9.2 Schemas e Tabelas (identificadas por código)

Das queries nos modulos:

**Tabelas Core:**
- `pncp_raw_bids` — editais brutos (usada por search, panorama, oportunidades)
- `pncp_supplier_contracts` — contratos de fornecedores (usada por buyer intel, supplier, pricing, competitors)
- `opportunity_intel` — oportunidades processadas e ranqueadas (35+ colunas)
- `sc_public_entities` — entes publicos de SC (usada por matching, cobertura)
- `entity_coverage` — cobertura por entidade
- `coverage_evidence` — evidencias de auditoria
- `coverage_snapshots` — snapshots historicos de cobertura
- `ingestion_runs` — historico de execucao de crawlers
- `ingestion_checkpoints` — checkpoints de crawl
- `opportunity_runs` — runs do QW-01
- `engineering_opportunities` — oportunidades classificadas como engenharia

**Views:**
- `v_opportunity_coverage_summary` — sumario de cobertura de oportunidades
- `v_coverage_gaps` — gaps de cobertura (usada por coverage_gaps.py)
- `v_coverage_gaps_by_municipio` — gaps agregados por municipio
- `v_coverage_trend` — tendencia de cobertura (4 ultimas semanas)

**Funcoes RPC:**
- `search_datalake(p_ufs, p_date_start, p_date_end, p_tsquery, p_websearch_text, p_modalidades, p_valor_min, p_valor_max, p_esferas, p_modo, p_limit, p_embedding)` — busca full-text com 12 parametros
- `upsert_qw01_pncp_opportunities(jsonb)` — upsert de oportunidades QW-01
- `upsert_pncp_raw_bids(jsonb)` — upsert de editais brutos
- `generate_coverage_snapshot()` — gera snapshot diario

### 9.3 Tabelas Adicionais (identificadas em queries)

- `target_universe_entities` — entidades do universo alvo
- `target_universe_runs` — runs do universo alvo
- `pncp_enrichment_cache` — cache de enriquecimento PNCP
- `pncp_raw_contracts` — contratos brutos
- `enriched_entities` — entidades enriquecidas
- `search_results_cache`, `search_results_store` — cache de busca
- `profiles`, `alerts`, `pipeline_items`, `leads`, `classification_feedback`
- `organizations`, `digital_products`

---

## 10. Outputs e Artefatos em `data/` e `output/`

### 10.1 `data/` — Caches e Dados Persistentes

| Arquivo | Tamanho | Conteudo |
|---------|---------|----------|
| `intel_pncp_checkpoint.json` | 659K | Checkpoint do pipeline de inteligencia |
| `contract_intel.db` | 232K | SQLite com dados de contratos (fallback) |
| `ciga_ckan_crawl_full.log` | 214K | Log de crawl CIGA CKAN |
| `extra_ledger.json` | Ledger da construtora (oportunidades/propostas/contratos) |
| `platform_detection_results_pass2.json` | 181K | Resultados de deteccao de plataformas |
| `ibge_cache.json` | 8.1K | Cache IBGE |
| `cnpj_cache.json` | Cache CNPJ |
| `geocode_cache.json` | Cache de geocodificacao |
| `docs_cache.json` | 3.3K | Cache de documentos |
| `benchmark_cache.json` | Cache de benchmark |
| `intel/` | Intel reports (JSON + PDF + XLSX por CNPJ) |
| `selenium_debug/` | Screenshots de debug (Selenium) |

### 10.2 `output/` — Artefatos Gerados

| Diretorio | Conteudo |
|-----------|----------|
| `output/readiness/` | Manifestos de cobertura (coverage_manifest.json, gaps.csv, source-health.csv) |
| `output/qw-01/` | Execucoes do radar QW-01 (radar_editais.csv/.xlsx, run_manifest.json, summary.md, universe_snapshot.json, coverage_manifest.json, coverage_gaps.csv, source_health.json, source-applicability.csv) |
| `output/reports/coverage/` | Relatorios de gaps (XLSX, CSV) |
| `output/quality/` | Relatorios de qualidade (bandit, ruff, pytest, lint) |
| `output/profile-calibration/` | Calibracao de perfil de cliente |
| `output/coverage/` | Coverage gate reports |
| `output/bootstrap/` | Logs de bootstrap |

---

## 11. Arquivos de Configuracao

| Arquivo | Conteudo |
|---------|----------|
| `config/client_profiles/extra.yaml` | Perfil da Extra Construtora (object types, termos, pesos, thresholds) |
| `config/settings.py` | Configuracoes centralizadas (`DEFAULT_DSN`, `LOCAL_DATALAKE_DSN`) |
| `config/abbreviations.yaml` | Abreviacoes de nomes de entidades |
| `config/municipio_population.yaml` | Populacao por municipio |
| `config/sectors_config.yaml` | Configuracao de setores |
| `config/sectors_data.yaml` | Dados de setores |
| `config/source_applicability.yaml` | Aplicabilidade de fontes |
| `config/transparencia_config.yaml` | Configuracao do crawler Transparencia |

---

## 12. CLIs que Ja Funcionam Ponta a Ponta

Todos os comandos abaixo estao implementados e prontos para uso (requerem PostgreSQL acessivel):

### Opportunity Intelligence
```bash
python scripts/opportunity_intel/cli.py radar --profile config/client_profiles/extra.yaml
python scripts/opportunity_intel/cli.py list --status open --uf SC --limit 20
python scripts/opportunity_intel/cli.py show 42
python scripts/opportunity_intel/cli.py explain 42
python scripts/opportunity_intel/cli.py coverage
python scripts/opportunity_intel/cli.py source-health
python scripts/opportunity_intel/cli.py update --source pncp
python scripts/opportunity_intel/cli.py export --format csv -o ops.csv
python scripts/opportunity_intel/cli.py briefing --dias 7
python scripts/opportunity_intel/manifest.py
```

### Buyer Intelligence
```bash
python scripts/buyer_intel/cli.py ranking --limit 20
python scripts/buyer_intel/cli.py perfil 12345678
python scripts/buyer_intel/cli.py ranking --format csv
```

### Extra Ledger (zero dependencias)
```bash
python scripts/extra_ledger/cli.py dashboard
python scripts/extra_ledger/cli.py oportunidade add --orgao "PMF" --objeto "Reforma" --valor 500000 --decisao participar
python scripts/extra_ledger/cli.py proposta add --orgao "PMF" --objeto "Reforma" --valor 485000
python scripts/extra_ledger/cli.py contrato add --orgao "PMF" --objeto "Reforma" --valor 485000
python scripts/extra_ledger/cli.py capacidade add --tipo atestado --descricao "CREA 2026"
```

### Crawl e Monitoramento
```bash
python scripts/crawl/monitor.py --source pncp --mode full
python scripts/crawl/monitor.py --source all --mode incremental
python scripts/crawl/monitor.py --report-coverage
```

### DataLake CLI
```bash
python scripts/local_datalake.py search --uf SC --dias 30
python scripts/local_datalake.py supplier --cnpj 12345678000199
python scripts/local_datalake.py pricing --keywords "obra,reforma" --uf SC
python scripts/local_datalake.py competitors --keywords "engenharia"
python scripts/local_datalake.py detail --pncp-id X
python scripts/local_datalake.py stats
python scripts/local_datalake.py coverage
```

### Reports
```bash
python scripts/reports/panorama.py --uf SC --dias 90
python -m scripts.reports.coverage_weekly
python scripts/reports/coverage_gaps.py
```

---

## 13. Componentes que Funcionam Ponta a Ponta sem Intervencao Manual

1. **Radar QW-01** (`radar.py`): pipeline completo que vai da validacao de schema ate a geracao de 8 artefatos de output. Ja executou com sucesso em 2026-07-13.

2. **Monitor Multi-Source** (`monitor.py`): orquestra crawl, transform, upsert, entity matching, engineering classification e entity evidence para qualquer fonte registrada.

3. **Opportunity Intel CLI**: 9 comandos operacionais que leem do `opportunity_intel` e exibem/exportam dados sem parametros complexos.

4. **Extra Ledger CLI**: sistema completo de ledger sem banco de dados, funcional com Python puro.

5. **DataLake CLI**: 7 comandos de consulta ao PostgreSQL com full-text search, estatisticas de precos, e dashboard de cobertura.

6. **Manifest Generator** (`manifest.py`): gera 3 arquivos de coverage manifest com validacoes matematicas (impede % negativos, >100%, denominador zero).

7. **Registry Central** (`registry.py`): unifica todas as 11 fontes de dados com metadata completa.

---

## 14. Oportunidades de Integracao

1. **Extra Ledger -> Opportunity Intel**: oportunidades registradas manualmente no ledger podem ser enriquecidas com dados do `opportunity_intel` via `pncp_id`.

2. **Buyer Intel -> Opportunity Intel**: perfis de orgaos compradores podem alimentar o scoring de oportunidades (buyer_profile como fator de `client_fit_score`).

3. **Contracts Crawler -> Buyer Intel**: o crawler de contratos (`pncp_supplier_contracts`) e a fonte primaria do Buyer Intel.

4. **Coverage Manifest -> Dashboard**: o `manifest.py` produz dados que alimentam o dashboard do `local_datalake.py coverage`.

5. **Engineering Classification -> Opportunity Intel**: o classificador de engenharia (`pncp_engineering.py`) pode ser integrado ao transformer do Opportunity Intel como fator de ranking.

6. **12-param search_datalake RPC**: pode ser exposta como API ou integrada a ferramentas externas (BI, dashboards).

---

## 15. Metricas de Volume (aproximadas)

Baseado nas queries de codigo e logs de execucao:

| Tabela | Estimativa | Fonte |
|--------|-----------|-------|
| `pncp_raw_bids` | ~50K+ registros | search RPC, panorama queries |
| `pncp_supplier_contracts` | ~10K+ registros | buyer intel, pricing queries |
| `opportunity_intel` | ~5K+ registros | radar QW-01 (radar_editais.csv = 947K) |
| `sc_public_entities` | ~2.085 entidades | monitor.py (2085 orgaos SC) |
| `target_universe_entities` | ~1.093 entidades | CANONICAL_UNIVERSE |
| `entity_coverage` | ~2K+ linhas | coverage queries |
| `coverage_snapshots` | Multiplos snapshots | weekly report |
| `coverage_evidence` | ~10K+ linhas | entity evidence projection |
| `engineering_opportunities` | ~5K+ registros | monitor.py PNCP phase |

---

## 16. Dependencias Tecnicas

### Python (identificadas nos imports)
- `psycopg2` — PostgreSQL (obrigatorio para operacao)
- `rich` — terminal formatting (local_datalake.py)
- `yaml` (PyYAML) — config/profile files
- `openpyxl` — Excel output (opcional, graceful fallback)
- `reportlab` — PDF generation (coverage_weekly.py)
- `selenium` — browser automation (doe_sc, transparencia)
- `playwright` — fallback browser
- `redis` — cache (redis_pool.py)
- `google-cloud-bigquery` — mides_bigquery_crawler

### Infraestrutura
- PostgreSQL 15/16 (Docker ou host)
- Redis (opcional, para rate limiting avançado)
- Selenium/Chrome (para crawlers municipais)
- Playwright (fallback para Selenium)
