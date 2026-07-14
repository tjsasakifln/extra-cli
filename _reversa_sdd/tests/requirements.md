# Tests — Testes Automatizados

> Gerado pelo Writer em 2026-07-13T21:30:00Z | doc_level: completo | Base: 249340d

## Visão Geral

Suíte de 64 arquivos de teste usando pytest 7.x+ com suporte a 7 marcadores (unit, integration, e2e, smoke, slow, database, crawler). Abrange desde testes unitarios rapidos ate validacao ponta-a-ponta contra sistemas reais, com fixtures compartilhadas em 2 conftest.py, dados de fixture externos e cobertura via pytest-cov.

## Responsabilidades

- Validar contrato de interface de todos os 10 crawlers sync (protocol conformance tests)
- Garantir pipeline de transformacao: content_hash SHA-256, normalizacao de datas/valores
- Testar pipeline de matching de entidades (CNPJ exato, nome+municipio, fuzzy)
- Validar pipeline de oportunidade (dedup, ranking, modelo de dados, status)
- Testar pipeline de intel (consolidacao, enriquecimento, validacao)
- Validar pipeline de contratos (crawl, target, truth ledger)
- Testar pipeline de cobertura (calculator, truth, evidence projection)
- Validar pipeline de readiness (consulting_readiness, freshness_gate, backfill)
- Testar orquestracao de crawl (orchestrator, monitor, checkpoint)
- Testar utilitarios de lib (geocode, cache IBGE, manifest, entity hierarchy, transformer)

## Regras de Negocio

- R1: Testes unitarios nao fazem IO de rede nem banco de dados — mock obrigatorio via conftest.py: `_mock_psycopg2_connect` (autouse) 🟢
- R2: Testes de integracao exigem PostgreSQL real via docker-compose + `REQUIRE_TEST_DB=1` 🟢
- R3: Testes e2e sao opt-in por marcador `e2e` — exigem sistemas externos reais 🟢
- R4: Testes smoke verificam conectividade e funcionalidade basica por fonte 🟢
- R5: Marcador `slow` excluido do default addopts (`-m "not slow"`) 🟢
- R6: Protocol conformance testa que todo crawler implementa `crawl(mode)->list[dict]` e `transform(records)->list[dict]` 🟢
- R7: Cache IBGE usa TTL de 7 dias, testado via isolation de time mockado 🟢
- R8: Fixture `_mock_psycopg2_connect` e autouse e protege todos os testes — opt-in para integration/database via marcador + env var 🟢
- R9: `TestPostgreSQLFailClosed` e excecao a regra de mock — testa falha de conexao real 🟢
- R10: Bandit exclude `tests/` — testes excluidos de scan de seguranca intencionalmente 🟢
- R11: mypy com `ignore_errors = true` em `tests.*` — testes nao sao verificados estaticamente 🟢

## Requisitos Funcionais

| ID | Requisito | Prioridade | Fonte |
|----|-----------|-----------|-------|
| RF-TS01 | Protocol conformance: verificar `crawl()` e `transform()` em todos os crawlers | Must | `test_crawler_protocol.py:60-75` |
| RF-TS02 | Protocol signatures: verificar tipos de entrada/saida de crawl() e transform() | Must | `test_crawler_protocol.py:78-150` |
| RF-TS03 | Testar paginacao PNCP day-by-day com filtro UF/modalidade | Must | `test_crawler_pncp.py` |
| RF-TS04 | Testar crawler DOM-SC com Basic Auth, 3 categorias | Must | `test_doe_sc_crawler.py` |
| RF-TS05 | Testar crawler DOE-SC com Bearer token, cache 30min | Must | `test_doe_sc_crawler.py` |
| RF-TS06 | Testar crawler PCP v2 com fuzzy modalidade mapping | Should | `test_pcp_crawler.py` |
| RF-TS07 | Testar crawler ComprasGov (legado + Lei 14.133) | Must | `test_compras_gov_crawler.py` |
| RF-TS08 | Testar crawler contratos PNCP com janelas 90 dias | Must | `test_contracts_crawler.py` |
| RF-TS09 | Testar crawler TCE-SC via SCMWeb | Should | `test_tce_sc_live.py` |
| RF-TS10 | Testar scraping transparencia: 4 templates (Betha, Ipam, E-gov, Generico) | Should | `test_transparencia_crawler.py` |
| RF-TS11 | Testar transformacao: content_hash SHA-256, normalizacao datas/valores | Must | `test_transformer.py` |
| RF-TS12 | Testar cache IBGE com TTL de 7 dias | Must | `test_cache_ibge.py` |
| RF-TS13 | Testar matching cascade: CNPJ → nome+municipio → fuzzy | Must | `test_entity_matcher.py` |
| RF-TS14 | Testar modelo de dados de oportunidade (models, dedup, ranking, status, transformer) | Must | `test_opportunity_models.py`, `test_opportunity_dedup.py`, `test_opportunity_ranking.py`, `test_opportunity_status.py`, `test_opportunity_transformer.py` |
| RF-TS15 | Testar pipeline de intel (consolidacao, enrichment, validacao) | Must | `test_intel_pipeline.py`, `test_backfill_count_covered.py`, `test_pncp_pipeline_db.py` |
| RF-TS16 | Testar pipeline de contrato intel (crawl, target, truth v1, CLI) | Must | `test_contract_intel_cli.py`, `test_contract_intel_crawl.py`, `test_contract_intel_target.py`, `test_contract_intel_truth_v1.py` |
| RF-TS17 | Testar pipeline de cobertura (calculator, truth, evidence, evidence projection DB) | Must | `test_coverage_calculator.py`, `test_coverage_truth.py`, `test_coverage_only_evidence.py`, `test_evidence_projection_db.py` |
| RF-TS18 | Testar readiness (consulting_readiness, freshness_gate, backfill_pipeline) | Must | `test_consulting_readiness.py`, `test_freshness_gate.py`, `test_backfill_pipeline.py` |
| RF-TS19 | Testar orquestradores (orchestrator, monitor) | Should | `test_orchestrator.py` |
| RF-TS20 | Testar sistema de checkpoint para retomada de crawls | Should | `test_checkpoint.py` |
| RF-TS21 | Testar manifest de cobertura | Must | `test_manifest.py` |
| RF-TS22 | Testar rotina de backfill multi-source | Should | `test_backfill_pipeline.py` |
| RF-TS23 | Testar upsert de contratos | Should | `test_upsert_contracts.py` |
| RF-TS24 | Testar pipeline de precos (price pipeline) | Should | `test_pncp_pipeline_db.py` |
| RF-TS25 | Smoke tests por fonte: conectividade e funcionalidade basica | Must | `tests/smoke/test_smoke_sources.py`, `tests/smoke/test_smoke_contract_intel.py`, `tests/smoke/test_qw01_pncp_smoke.py` |
| RF-TS26 | Testar QW-01 radar operacional | Must | `test_qw01_radar.py`, `test_qw01_postgres.py` |
| RF-TS27 | Testar backfill SC Dados Abertos | Should | `test_sc_dados_abertos_backfill.py` |
| RF-TS28 | Testar adaptador Selenium para crawlers | Should | `test_selenium_crawler_adapter.py` |
| RF-TS29 | Testar CIGA CKAN crawler e AC validation | Must | `test_ciga_ckan_crawler.py`, `test_ciga_ckan_ac_validation.py` |
| RF-TS30 | Testar Mides BigQuery crawler | Must | `test_mides_bigquery_crawler.py` |
| RF-TS31 | Testar date propagation no pipeline | Should | `test_date_propagation.py` |
| RF-TS32 | Testar resolucao de entidades nao resolvidas | Should | `test_resolve_unresolved_entities.py` |
| RF-TS33 | Testar monitoramento (scripts/test_monitoring.py) | Should | `tests/scripts/test_monitoring.py` |
| RF-TS34 | Testar datalake helper (search, supplier, stats) | Should | `test_datalake_helper.py` |

## Requisitos Nao Funcionais

| Tipo | Requisito | Evidencia | Confianca |
|------|----------|----------|-----------|
| Performance | Testes unitarios executam em < 2s sem IO | `conftest.py:_mock_psycopg2_connect` (autouse) + marcador `-m "not slow"` | 🟢 |
| Isolamento | Mock de banco padrao via fixture autouse; DB real so com marcador + env var | `conftest.py:12-46` | 🟢 |
| Portabilidade | Testes rodam sem dependencia externa na configuracao default | `conftest.py:25-29` (guarda REQUIRE_TEST_DB) | 🟢 |
| Cobertura | pytest-cov configurado com `--cov=scripts --cov-report=term-missing --cov-report=html` | `pytest.ini:5-7` | 🟢 |
| Qualidade | Ruff + mypy + bandit + compileall no gate de codigo | `pyproject.toml`, `plano-mestre §18` | 🟢 |
| Compatibilidade | Python 3.12+ alvo | `pyproject.toml:target-version = "py312"` | 🟢 |
| Cobertura | Gate de 80% para modulos criticos (universe.py, opportunity_intel, reconciliacao, coverage, contract pipeline, supplier metrics, price pipeline, report builder) | `plano-mestre §18` — NAO IMPLEMENTADO | 🔴 |
| Seguranca | Bandit exclui tests/ — testes fora do escopo de scan de seguranca | `pyproject.toml:bandit.exclude_dirs` | 🟢 |
| Type Safety | mypy com `ignore_errors = true` em tests.* — testes nao verificados estaticamente | `pyproject.toml:mypy.overrides[1]` | 🟢 |

## Criterios de Aceitacao

```gherkin
Cenario: Teste unitario sem banco real
Dado que o teste NAO tem marcador integration nem database
E REQUIRE_TEST_DB nao esta definido como "1"
Quando o teste executa
Entao psycopg2.connect e mockado via fixture autouse
E o teste nao faz conexao real com PostgreSQL

Cenario: Teste de integracao com banco real
Dado que o teste tem marcador integration ou database
E REQUIRE_TEST_DB=1
Quando o teste executa
Entao conftest_db.db_conn fornece conexao PostgreSQL real
E migrations sao aplicadas automaticamente na primeira conexao
E dados de teste com prefixo 'test_' sao limpos apos cada teste via clean_bids

Cenario: Protocol conformance de crawler
Dado um modulo de crawler registrado em CRAWLER_MODULES
Quando test_has_crawl_function executa
Entao o modulo expoe funcao crawl() callable
E test_has_transform_function verifica transform() callable
E test_crawl_signatures verifica tipos de retorno

Cenario: Smoke test por fonte
Dado que a fonte externa esta acessivel
Quando o smoke test executa
Entao verifica conectividade basica (HTTP 200 ou similar)
E verifica que o formato de resposta e esperado
E nao faz assertions de conteudo completo

Cenario: Cache IBGE com TTL
Dado que o cache esta vazio
Quando _fetch_ibge_municipio_lookup() e chamado
Entao os dados sao armazenados em _IBGE_MUNICIPIOS_CACHE
E o timestamp _IBGE_MUNICIPIOS_CACHE_TS e atualizado
E apos 7 dias o cache expira e nova consulta e feita
```

## Prioridade MoSCoW

| Prioridade | Requisitos | Justificativa |
|-----------|-----------|---------------|
| **Must** | RF-TS01, RF-TS02, RF-TS03, RF-TS04, RF-TS05, RF-TS07, RF-TS08, RF-TS11, RF-TS12, RF-TS13, RF-TS14, RF-TS15, RF-TS16, RF-TS17, RF-TS18, RF-TS21, RF-TS25, RF-TS26, RF-TS29, RF-TS30 | Testes de contrato de interface, crawlers principais, pipelines core, e2e/smoke |
| **Should** | RF-TS06, RF-TS09, RF-TS10, RF-TS19, RF-TS20, RF-TS22, RF-TS23, RF-TS24, RF-TS27, RF-TS28, RF-TS31, RF-TS32, RF-TS33, RF-TS34 | Crawlers secundarios, testes de utilidades, pipelines auxiliares |
| **Could** | — | N/A |
| **Wont** | — | N/A |

## Rastreabilidade de Codigo

| ID | Arquivo(s) de Teste | Modulos Cobertos |
|----|--------------------|------------------|
| RF-TS01 | `test_crawler_protocol.py` | `scripts/crawl/registry.py`, todos os 10 crawlers |
| RF-TS02 | `test_crawler_protocol.py` | Todos os 10 crawlers (assinaturas) |
| RF-TS03 | `test_crawler_pncp.py` | `scripts/crawl/pncp_crawler_adapter.py` |
| RF-TS04 | `test_doe_sc_crawler.py` | `scripts/crawl/dom_sc_crawler.py` |
| RF-TS05 | `test_doe_sc_crawler.py` | `scripts/crawl/doe_sc_crawler.py` |
| RF-TS06 | `test_pcp_crawler.py` | `scripts/crawl/pcp_crawler.py` |
| RF-TS07 | `test_compras_gov_crawler.py` | `scripts/crawl/compras_gov_crawler.py` |
| RF-TS08 | `test_contracts_crawler.py` | `scripts/crawl/contracts_crawler.py` |
| RF-TS09 | `test_tce_sc_live.py` | `scripts/crawl/tce_sc_crawler.py` |
| RF-TS10 | `test_transparencia_crawler.py` | `scripts/crawl/transparencia_crawler.py` |
| RF-TS11 | `test_transformer.py`, `test_common.py` | `scripts/crawl/transformer.py`, `scripts/crawl/common.py` |
| RF-TS12 | `test_cache_ibge.py` | `scripts/crawl/enricher.py` |
| RF-TS13 | `test_entity_matcher.py` | `scripts/crawl/entity_matcher.py` |
| RF-TS14 | `test_opportunity_models.py`, `test_opportunity_dedup.py`, `test_opportunity_ranking.py`, `test_opportunity_status.py`, `test_opportunity_transformer.py` | `scripts/opportunity_intel/` |
| RF-TS15 | `test_intel_pipeline.py`, `test_backfill_count_covered.py`, `test_pncp_pipeline_db.py` | `scripts/intel_pipeline.py`, `scripts/pipeline/` |
| RF-TS16 | `test_contract_intel_cli.py`, `test_contract_intel_crawl.py`, `test_contract_intel_target.py`, `test_contract_intel_truth_v1.py` | `scripts/contract_intel/` |
| RF-TS17 | `test_coverage_calculator.py`, `test_coverage_truth.py`, `test_coverage_only_evidence.py`, `test_evidence_projection_db.py` | `scripts/coverage/`, `scripts/coverage_truth.py` |
| RF-TS18 | `test_consulting_readiness.py`, `test_freshness_gate.py`, `test_backfill_pipeline.py` | `scripts/consulting_readiness.py`, `scripts/freshness_gate.py` |
| RF-TS19 | `test_orchestrator.py` | `scripts/crawl/orchestrator.py`, `scripts/crawl/monitor.py` |
| RF-TS20 | `test_checkpoint.py` | `scripts/crawl/checkpoint.py` |
| RF-TS21 | `test_manifest.py` | `scripts/opportunity_intel/manifest.py` |
| RF-TS22 | `test_backfill_pipeline.py` | `scripts/pipeline/backfill_multi_source.py` |
| RF-TS23 | `test_upsert_contracts.py` | `scripts/pipeline/upsert_contracts.py` |
| RF-TS24 | `test_pncp_pipeline_db.py` | `scripts/pipeline/pncp_pipeline_db.py` |
| RF-TS25 | `tests/smoke/*` | Todos os crawlers, QW-01, contract intel |
| RF-TS26 | `test_qw01_radar.py`, `test_qw01_postgres.py` | `scripts/opportunity_intel/qw01_radar.py` |
| RF-TS27 | `test_sc_dados_abertos_backfill.py` | `scripts/crawl/sc_dados_abertos_backfill.py` |
| RF-TS28 | `test_selenium_crawler_adapter.py` | `scripts/crawl/selenium_crawler_adapter.py` |
| RF-TS29 | `test_ciga_ckan_crawler.py`, `test_ciga_ckan_ac_validation.py` | `scripts/crawl/ciga_ckan_crawler.py` |
| RF-TS30 | `test_mides_bigquery_crawler.py` | `scripts/crawl/mides_bigquery_crawler.py` |
| RF-TS31 | `test_date_propagation.py` | `scripts/pipeline/date_propagation.py` |
| RF-TS32 | `test_resolve_unresolved_entities.py` | `scripts/fix/resolve_unresolved_entities.py` |
| RF-TS33 | `tests/scripts/test_monitoring.py` | `scripts/monitoring.py` |
| RF-TS34 | `test_datalake_helper.py` | `scripts/local_datalake.py` |
