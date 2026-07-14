# Tests — Design

> Gerado pelo Writer em 2026-07-13T21:30:00Z | doc_level: completo

## Arquitetura de Testes

```
tests/
├── conftest.py                          # Fixture autouse: mock psycopg2 (isolamento padrao)
├── conftest_db.py                       # Fixtures de banco real (db_conn session, clean_bids)
├── __init__.py                          # Package marker
├── fixturas/                            # Dados de fixture externos
│   ├── ciga_ckan_ac_data.py            # Dados sinteticos para AC validation
│   ├── pncp_v2_response.json           # Resposta PNCP v2 mockada
│   └── pncp_v3_response.json           # Resposta PNCP v3 mockada
├── scripts/                            # Testes de scripts auxiliares
│   └── test_monitoring.py              # Teste do modulo de monitoramento
├── smoke/                              # Smoke tests de conectividade
│   ├── test_smoke_sources.py           # Smoke todas as fontes
│   ├── test_smoke_contract_intel.py    # Smoke contract intel
│   └── test_qw01_pncp_smoke.py         # Smoke QW-01 PNCP
└── test_*.py                           # 58 testes unitarios/integracao
```

## Interface de Testes

### Marcadores (pytest.ini)

```ini
markers =
    slow: Tests that are slow (network, DB, filesystem)
    unit: Pure unit tests (no IO, no DB)
    integration: Tests that require external resources (API, DB)
    e2e: End-to-end tests against real external systems
    smoke: Quick connectivity/functionality checks per source
    database: Tests that require a real PostgreSQL database
    crawler: Tests for specific crawler modules
```

### Configuracao de Execucao (pytest.ini)

```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts =
    --cov=scripts
    --cov-report=term-missing
    --cov-report=html:docs/td-001/coverage-reports/
    -v
    -m "not slow"
```

### Fixtures Compartilhadas

| Fixture | Escopo | Autouse | Arquivo | Descricao |
|---------|--------|---------|---------|-----------|
| `_mock_psycopg2_connect` | function | Sim | `conftest.py:11-46` | Mocka psycopg2.connect para isolar testes de DB. Excecao: TestPostgreSQLFailClosed. |
| `test_dsn` | session | Nao | `conftest_db.py:28-31` | Retorna TEST_DSN (env ou default `postgresql://test:test@localhost:5433/extra_test`) |
| `db_conn` | session | Nao | `conftest_db.py:34-99` | Conexao PostgreSQL real com aplicacao de migrations. Skip se DB indisponivel. |
| `clean_bids` | function | Nao | `conftest_db.py:102-117` | Limpa dados de teste (`pncp_id LIKE 'test_%'`) apos cada teste. |

### Grupo: Protocol Conformance (test_crawler_protocol.py)

```
_init_from_registry() → CRAWLER_MODULES dict
    ↓
TestCrawlerInterface (pytest.mark.unit, parametrize sobre CRAWLER_MODULES)
├── test_has_crawl_function(source)         → assert hasattr + callable
├── test_has_transform_function(source)     → assert hasattr + callable
└── TestCrawlerSignatures
    ├── test_crawl_signatures(source)       → tipos entrada/saida
    └── test_transform_signatures(source)   → tipos entrada/saida
```

### Grupo: Crawlers (10 arquivos)

Cada crawler tem teste unitario (mocks) e/ou integracao (DB real):

| Arquivo | Crawler | Cobertura |
|---------|---------|-----------|
| `test_crawler_pncp.py` | PNCP | Paginacao, filtros, keywords |
| `test_ciga_ckan_crawler.py` | CIGA CKAN | Crawl, transform, AC validation |
| `test_compras_gov_crawler.py` | ComprasGov | 2 endpoints, auto-detecao |
| `test_contracts_crawler.py` | Contracts | Janelas 90 dias, upsert |
| `test_doe_sc_crawler.py` | DOE-SC | Token Bearer, cache 30min |
| `test_sc_compras_crawler.py` | SC Compras | HTML regex, labels |
| `test_pcp_crawler.py` | PCP v2 | Modalidade mapping fuzzy |
| `test_transparencia_crawler.py` | Transparencia | 4 templates |
| `test_tce_sc_live.py` | TCE-SC | SCMWeb (slow) |
| `test_mides_bigquery_crawler.py` | Mides BigQuery | Crawl e transform |
| `test_ciga_ckan_ac_validation.py` | CIGA CKAN AC | Validacao AC com fixtures |

### Grupo: Pipeline (8 arquivos)

| Arquivo | Pipeline | Tipo |
|---------|----------|------|
| `test_intel_pipeline.py` | Intel pipeline | Unit + Integration |
| `test_backfill_count_covered.py` | Backfill count covered | Integration |
| `test_pncp_pipeline_db.py` | PNCP pipeline DB | Integration |
| `test_opportunity_models.py` | Opportunity models | Unit |
| `test_opportunity_dedup.py` | Opportunity dedup | Unit |
| `test_opportunity_ranking.py` | Opportunity ranking | Unit |
| `test_opportunity_status.py` | Opportunity status | Unit |
| `test_opportunity_transformer.py` | Opportunity transformer | Unit |
| `test_opportunity_integration.py` | Opportunity integration | Integration |
| `test_contract_intel_cli.py` | Contract intel CLI | Unit |
| `test_contract_intel_crawl.py` | Contract intel crawl | Unit |
| `test_contract_intel_target.py` | Contract intel target | Unit |
| `test_contract_intel_truth_v1.py` | Contract intel truth v1 | Integration |
| `test_coverage_calculator.py` | Coverage calculator | Unit |
| `test_coverage_truth.py` | Coverage truth | Integration |
| `test_coverage_only_evidence.py` | Coverage only evidence | Unit |
| `test_evidence_projection_db.py` | Evidence projection DB | Integration |

### Grupo: Readiness (3 arquivos)

| Arquivo | Modulo | Tipo |
|---------|--------|------|
| `test_consulting_readiness.py` | consulting_readiness.py | Integration |
| `test_freshness_gate.py` | freshness_gate.py | Integration |
| `test_backfill_pipeline.py` | backfill_pipeline.py | Integration |

### Grupo: Lib/Utilitarios (8 arquivos)

| Arquivo | Modulo | Tipo |
|---------|--------|------|
| `test_geocode.py` | lib/geocode.py | Unit |
| `test_cache_ibge.py` | crawl/enricher.py (_ibge_cache) | Unit |
| `test_entity_hierarchy.py` | lib/entity_hierarchy.py | Unit |
| `test_manifest.py` | opportunity_intel/manifest.py | Unit + Integration |
| `test_universe.py` | lib/universe.py | Unit |
| `test_common.py` | crawl/common.py | Unit |
| `test_transformer.py` | crawl/transformer.py | Unit |
| `test_report_dedup.py` | reports/report_dedup.py | Unit |

## Fluxo Principal

```
pytest (comando CLI)
  ↓
pytest.ini carrega: testpaths, markers, addopts (cov, verbose, exclude slow)
  ↓
conftest.py:_mock_psycopg2_connect (autouse) — mocka psycopg2 para todos os testes
  ↓
Para cada test_*.py encontrado:
  ├── Se teste tem marcador integration/database + REQUIRE_TEST_DB=1
  │     → conftest_db.db_conn (session scope) — PostgreSQL real com migrations
  │     → clean_bids (function scope) — limpa dados de teste
  │
  ├── Se teste tem marcador e2e
  │     → Conexao real com sistema externo
  │
  ├── Se teste tem marcador unit
  │     → Mocks completos, sem IO
  │
  └── Se teste tem marcador smoke
        → Verificacao rapida de conectividade

Apos execucao:
  ├── --cov=scripts → relatorio de cobertura terminal + HTML
  └── Resultado: PASS/FAIL com verbose output
```

## Dependencias

### Framework de Teste

| Dependencia | Uso | Versao (inferida) |
|------------|-----|-------------------|
| pytest | Framework de teste | 7.x+ |
| pytest-cov | Cobertura de codigo | 4.x+ |
| pytest-html | Relatorio HTML (via cov-report) | 3.x+ |
| unittest.mock | Mocks (stdlib) | Python 3.12 |
| psycopg2-binary | Conexao PostgreSQL em testes de integracao | 2.9.x |

### Infraestrutura de Teste

| Recurso | Configuracao | Uso |
|---------|-------------|-----|
| PostgreSQL test | `docker-compose.yml` → `postgresql://test:test@localhost:5433/extra_test` | Testes de integracao |
| Docker Compose | `docker compose up -d test-db` | Iniciar banco de testes |
| Variaveis de ambiente | `TEST_DSN`, `REQUIRE_TEST_DB`, `PNCP_TOKEN`, etc. | Controle de ambiente |

### Dependencias entre Testes

Nao ha dependencia explicita entre arquivos de teste. Cada arquivo e executado isoladamente. A unica dependencia e infraestrutural:

- `conftest_db.py` depende de `psycopg2` e de `docker-compose` rodando
- `test_e2e_external.py` depende de sistemas externos reais (PNCP API, etc.)
- `tests/smoke/*` depende de conectividade de rede com as fontes

## Decisoes de Design

| Decisao | Opcao Escolhida | Alternativa Rejeitada | Justificativa |
|---------|----------------|----------------------|---------------|
| Isolamento de banco | Fixture autouse mocka psycopg2 para todos os testes | Fixture apenas nos testes que precisam | Evita esquecimento — todo teste e isolado por padrao, opt-in para DB real via marcador + env var |
| Escopo de db_conn | Session-scoped | Function-scoped | Migrations sao aplicadas uma vez por sesse o, nao por teste — 10x mais rapido |
| Registro de crawlers | `_init_from_registry()` -> `scripts/crawl/registry.py` | Lista hardcoded em test_crawler_protocol.py | Sincronizado automaticamente com o registry central — sem duplicacao de manutencao |
| Smoke tests | Arquivos separados em `smoke/` subdir | Marcador `smoke` inline nos testes de crawler | Separa claramente validacao rapida de conectividade de testes funcionais completos |
| Cobertura | `--cov=scripts` (modulo scripts inteiro) | `--cov` sem filtro ou `--cov=tests` | Foco em cobertura de codigo de producao, nao de teste |
| Exclusao de slow | `-m "not slow"` no addopts | Nenhum filtro default | CI deve rodar rapido (~2s unit); testes lentos sao opt-in |
| Dados de fixture | JSON files + python module em `fixtures/` | Inline nos testes | Reutilizavel entre testes, facil de atualizar quando schema muda |
| mypy em tests | `ignore_errors = true` | `disallow_untyped_defs` ativo | Decisao pragmatica — testes tem muitos mocks e duck typing que nao compensam tipagem estrita |

## Riscos e Lacunas

### 🔴 LACUNAS IDENTIFICADAS

| ID | Lacuna | Impacto | Risco | Remediacao |
|----|--------|---------|-------|------------|
| L-TS01 | `scripts/lib/universe.py` sem teste de cobertura mensurado | Plano-mestre §18 exige >=80% de cobertura para universe.py | ALTO | Implementar gate de cobertura com pytest-cov e CI com limite minimo |
| L-TS02 | `scripts/opportunity_intel/` sem gate de cobertura | Plano-mestre §18 exige >=80% para todo opportunity_intel | ALTO | Adicionar limite minimo de cobertura no CI para esse modulo |
| L-TS03 | Reconciliation pipeline sem teste ou gate de cobertura | Plano-mestre §18 exige >=80% para reconciliacao | ALTO | Criar test suite basica e gate de cobertura |
| L-TS04 | Coverage module sem gate de cobertura implementado | Plano-mestre §18 exige >=80% para coverage, contract pipeline, supplier metrics, price pipeline, report builder | ALTO | Implementar limite minimo de cobertura no CI |
| L-TS05 | Contract pipeline sem cobertura mensurada | Plano-mestre §18 exige >=80% | ALTO | Adicionar test coverage gate no CI |
| L-TS06 | Supplier metrics sem testes dedicados | Plano-mestre §18 exige >=80% | ALTO | Criar test suite baseline |
| L-TS07 | Price pipeline sem gate de cobertura | Plano-mestre §18 exige >=80% | ALTO | Implementar gate e testes |
| L-TS08 | Report builder sem cobertura mensurada | Plano-mestre §18 exige >=80% | MEDIO | Adicionar gate de cobertura |
| L-TS09 | `tests.*` com `ignore_errors = true` no mypy | Perda de deteccao de erros de tipo em testes | BAIXO | Gradualmente habilitar mypy em testes novos com `disallow_untyped_defs` |
| L-TS10 | Bandit exclui `tests/` — sem scan de seguranca em codigo de teste | Codigo de teste com secrets ou vulnerabilidades passa despercebido | BAIXO | Documentado como intencional (plano-mestre §18) |
| L-TS11 | Testes de integracao dependem de docker-compose | Falha silenciosa com `pytest.skip` se DB nao disponivel — pode mascarar regression | MEDIO | CI deve ter `REQUIRE_TEST_DB=1` para detectar falhas de setup |
| L-TS12 | Nao ha teste de golden report (plano-mestre §18, seçao Testes) | Relatorios de cobertura e intel sem validacao de saida | MEDIO | Implementar golden test com fixtures de dados congelados |

### 🟡 INFERENCIAS

| ID | Inferencia | Fonte | Confianca |
|----|-----------|-------|-----------|
| I-TS01 | Testes de integration usam `docker compose up -d test-db` para PostgreSQL | `conftest_db.py:8` (docstring referencia docker-compose) | 🟡 |
| I-TS02 | CI executa `pytest -m unit` rapido e `pytest -m integration` lento em stages separados | `pytest.ini:addopts` + pratica comum | 🟡 |
| I-TS03 | Testes smoke sao usados no startup dos timers systemd | `CLAUDE.md` lista `systemctl list-timers` | 🟡 |

### 🟢 CONFIRMADO

| Item | Fonte |
|------|-------|
| 64 arquivos de teste | `_reversa_sdd/inventory.md:130` |
| 7 marcadores pytest | `pytest.ini:10-17` |
| 2 conftest.py com fixtures compartilhadas | `conftest.py`, `conftest_db.py` |
| Protocol conformance testa todos os crawlers | `test_crawler_protocol.py:1-8` |
| Mock autouse psycopg2 para isolamento | `conftest.py:11-46` |
| pytest-cov configurado com relatorio HTML | `pytest.ini:5-7` |
| Gate de 80% nao implementado para modulos criticos | `plano-mestre §18` — ausencia de configuracao |
| Bandit exclui tests/ | `pyproject.toml:bandit.exclude_dirs` |
| mypy ignore_errors em tests.* | `pyproject.toml:mypy.overrides[1]` |
| Infraestrutura de teste via docker-compose | `conftest_db.py:DEFAULT_TEST_DSN` |
