# QA Adversarial — Coverage Audit — 2026-07-15

## 1. Casos Adversariais

Tabela completa de casos testados contra o codigo fonte, banco de dados e pipeline.

| # | Caso | Tratado? | Mecanismo | Risco |
|---|------|----------|-----------|-------|
| a | Edital republicado com mesmo numero mas data diferente | PARCIAL | Dedup key (Level 3) usa `orgao_cnpj+numero_processo+numero_edital` sem data. Content hash do adapter inclui `dataPublicacaoPncp`, mas o transformer.py tem hash separado que NAO inclui datas. O upsert via `content_hash` detectaria mudanca, mas sem versonamento — perde o registro anterior. | MEDIO — republicacao com correcao de datas seria detectada como "mesmo registro atualizado", mas o historico de versoes se perde. |
| b | Mudanca de data de abertura | NAO | `scripts/crawl/transformer.py` `compute_content_hash()` usa apenas `objetoCompra + valorTotalEstimado + situacaoCompra`. Datas NAO estao no hash. O adapter (`pncp_crawler_adapter.py`) tem hash SEPARADO que inclui data. **Duas implementacoes conflitantes de hash.** | ALTO — se o upsert usa o hash do transformer, mudanca de data abertura NAO dispara atualizacao. Duas implementacoes de hash sem coordenacao. |
| c | Orgao com CNPJ de fundo vs CNPJ prefeitura | PARCIAL | Entity matching por CNPJ8. Se fundo e prefeitura compartilham CNPJ8, funciona. Se tem CNPJ8 diferentes, o matching nao os une. A cobertura monitora entidades da planilha, entao bids de orgaos com CNPJ nao-listados podem ficar sem matched_entity. | MEDIO — o monitor pode perder bids de entidades vinculadas (fundacoes, autarquias) que tem CNPJ proprio fora do universo-alvo. |
| d | Numero edital formatacao diferente (001/2024 vs 1/2024 vs 00001/2024) | NAO | Dedup Level 3 faz comparacao de string exata. `"001/2024" != "1/2024"`. Sem normalizacao de numeros sequenciais. | ALTO — mesma licitacao com formatacao diferente vira registros duplicados. |
| e | Licitacao em lote (varios itens, mesmo edital) | SIM | PNCP API retorna uma publicacao por compra, nao por item. Itens sao endpoint separado (`fetch_compra_items`). Dedup por `numeroControlePNCP` (unico por compra). | BAIXO — a modelagem e 1 registro = 1 compra publicada. Itens nao geram duplicatas. |
| f | Contrato derivado de ata de registro de preco | NAO | `pncp_supplier_contracts` nao tem coluna de referencia para ARP (Ata de Registro de Preco). Nao ha linking entre contract e sua ata de origem. O campo `modalidade_nome` pode indicar, mas sem normalizacao. | MEDIO — contratos derivados de ARP perdem o vinculo com a compra original. Para analise de relicitacao, a cadeia contrato->ata->edital se perde. |
| g | PDF sem camada de texto (scanned) | NAO | Nao ha OCR ou extracao de texto de PDFs. O sistema baixa metadados de documentos via `fetch_compra_documents()` mas nao ha pipeline de extracao de conteudo de anexos. | MEDIO — anexos com imagem escaneada sao opacos para qualquer analise automatizada. |
| h | Edital publicado apenas no diario oficial (nao PNCP) | BLOQUEADO | Crawlers `doe_sc`, `dom_sc` estao em `SOURCE_BLOCKERS` — nao executam no ambiente atual. Editais exclusivos de diario oficial sao perdidos. | **ALTO** — furos de cobertura determinados por bloqueio de infraestrutura. |
| i | Publicacao removida do portal | NAO | Nao ha deteccao de remocao. O sistema faz upsert (INSERT/UPDATE) mas nao marca `is_active = false` para registros que sumiram da API. | MEDIO — sticky data: registros removidos permanecem como ativos para sempre. |
| j | HTTP 200 com pagina de erro ("Nenhum resultado") | PARCIAL | Se API retorna JSON valido sem chave `"data"` e sem `"empty": true`, o campo `empty_confirmed` pode ser True. O loop de crawl interpreta como janela sem dados e avanca. Mas se o retorno tem `"data": []` e `"empty": false`, o crawler marca `empty_confirmed=False` e pode parar com erro confuso. | MEDIO — edge case de API retornando formato inesperado pode gerar falso positivo de "dados ok" ou loop infinito ate `PNCP_MAX_PAGES`. |
| k | Crawler retornando 0 resultados sem erro | PARCIAL | O codigo diferencia `empty_confirmed=true` (0 resultados esperados) de `empty_confirmed=false` (possivel erro). Se `empty_confirmed=True`, o crawl segue adiante normalmente. | BAIXO — comportamento correto para janelas sem dados. Porem, se a API comeca a retornar `empty: true` por erro interno, o falso negativo e silencioso. |
| l | Paginacao retornando 1 de 10 mas parando na 5 | NAO | O loop usa `paginasRestantes` retornado pela API. **Nao ha validacao** como `if pagina_atual < total_paginas: assert paginas_restantes == total_paginas - pagina_atual`. Se a API retorna `paginasRestantes: 0` prematuramente, o crawl para sem erro. | **ALTO** — perda silenciosa de dados. Sem verificacao cruzada entre `totalPaginas` e `paginasRestantes` + `numeroPagina`. |
| m | Timezone: publicacao na virada do dia (23:59 vs 00:01) | PARCIAL | `transformer.py` usa `datetime.now(UTC)` como fallback para `dataPublicacaoPncp`. Mas PNCP datas sao BRT (UTC-3). Uma publicacao 23:59 BRT vira 02:59 UTC do dia seguinte. Crawl queries usam `dataInicial`/`dataFinal` em formato `YYYYMMDD` sem fuso — pode perder registros na fronteira. | MEDIO — janelas de 7 dias consecutivas mitigam, mas registros publicados a meia-noite podem ser perdidos ou dobrados em janelas adjacentes. |
| n | Mesmo edital no PNCP e portal municipal | PARCIAL | Dedup cross-source em `opportunity_intel/dedup.py` tem 4 niveis. Nivel 3 (`orgao_cnpj+processo+edital`) pegaria se ambos usam os mesmos numeros. Mas SEM normalizacao de formatacao (vide caso D). Portais municipais raramente usam `numeroControlePNCP`. | MEDIO — depende da consistencia dos dados de cada portal. Formatos divergentes geram duplicatas. |
| o | Anexo com mesmo nome de arquivo de editais diferentes | NA INSPECIONAR | `fetch_compra_documents()` retorna metadados. A interface de download local nao foi analisada. Se salva por nome de arquivo, haveria colisao. Se salva por `pncp_id+filename`, ok. | BAIXO — hipotetico ate inspecao do storage. |
| p | Anexo alterado (PDF substituido) mantendo mesma URL | NAO | Nao ha re-download baseado em etag, last-modified, ou hash do PDF. O sistema nao detecta substituicao de anexo. | MEDIO — se o orgao substitui o edital PDF, o sistema mantem o anterior sem saber. |

### Resumo por severidade

| Severidade | Contagem |
|-----------|----------|
| ALTO | 4 (b, d, h, l) |
| MEDIO | 9 (a, c, f, g, i, j, m, n, p) |
| BAIXO | 2 (e, o) |
| NAO TRATADO | 13 (tratamento parcial ou ausente somando ALTO+MEDIO) |

---

## 2. Cobertura de Testes

### Inventario completo

```
Total: 1381 testes coletados, 1371 selecionados, 10 desativados (conftest_db).
```

### Contagem por arquivo

| Arquivo | Testes | Classificacao |
|---------|--------|---------------|
| integration/test_all_sql_references.py | 4 | Integration |
| integration/test_migration_fresh_install.py | 10 | Integration |
| scripts/test_monitoring.py | 39 | Integration |
| smoke/test_qw01_pncp_smoke.py | 1 | Smoke |
| smoke/test_smoke_contract_intel.py | 8 | Smoke |
| smoke/test_smoke_sources.py | 5 | Smoke |
| test_backfill_count_covered.py | 5 | Integration |
| test_backfill_pipeline.py | 25 | Integration |
| test_cache_ibge.py | 10 | Unit |
| test_checkpoint.py | 15 | Unit |
| test_ciga_ckan_ac_validation.py | 18 | Integration |
| test_ciga_ckan_crawler.py | 61 | Integration |
| test_common.py | 53 | Unit |
| test_competitive_intel_validation.py | 2 | Integration |
| test_compras_gov_crawler.py | 6 | Integration |
| test_consulting_readiness.py | 33 | Integration |
| test_contract_intel_cli.py | 7 | Integration |
| test_contract_intel_crawl.py | 25 | Integration |
| test_contract_intel_target.py | 19 | Unit |
| test_contract_intel_truth_v1.py | 18 | Integration |
| test_contracts_crawler.py | 20 | Integration |
| test_coverage_blockers.py | 11 | Unit |
| test_coverage_calculator.py | 11 | Unit |
| test_coverage_manifest.py | 10 | Unit |
| test_coverage_only_evidence.py | 5 | Integration |
| test_coverage_states.py | 45 | Unit |
| test_coverage_truth.py | 40 | Integration/Unit |
| test_crawler_pncp.py | 7 | Unit |
| test_crawler_protocol.py | 7 | Integration |
| test_datalake_helper.py | 27 | Unit |
| test_date_propagation.py | 6 | Unit |
| test_doe_sc_crawler.py | 28 | Integration |
| test_e2e_external.py | 1 | Smoke/E2E |
| test_entity_hierarchy.py | 15 | Unit |
| test_entity_matcher.py | 22 | Unit |
| test_evidence_projection_db.py | 12 | Integration |
| test_fetch_result.py | 7 | Unit |
| test_freshness_gate.py | 8 | Unit |
| test_geocode.py | 30 | Unit |
| test_integration_crawl.py | 17 | Integration |
| test_intel_pipeline.py | 42 | Integration |
| test_manifest.py | 13 | Unit |
| test_mides_bigquery_crawler.py | 24 | Integration |
| test_opportunity_dedup.py | 13 | Unit |
| test_opportunity_integration.py | 14 | Integration |
| test_opportunity_models.py | 14 | Unit |
| test_opportunity_ranking.py | 12 | Unit |
| test_opportunity_status.py | 22 | Unit |
| test_opportunity_transformer.py | 13 | Unit |
| test_orchestrator.py | 20 | Integration |
| test_pcp_crawler.py | 28 | Integration |
| test_pncp_contract.py | 8 | Unit |
| test_pncp_pipeline_db.py | 2 | Integration |
| test_qw01_postgres.py | 5 | Integration |
| test_qw01_radar.py | 12 | Integration |
| test_report_dedup.py | 21 | Unit |
| test_resolve_unresolved_entities.py | 1 | Integration |
| test_sc_compras_crawler.py | 88 | Integration |
| test_sc_dados_abertos_backfill.py | 28 | Integration |
| test_scrape_residual_portals.py | 29 | Integration |
| test_selenium_crawler_adapter.py | 24 | Integration |
| test_snapshot_reconciliation.py | 8 | Integration |
| test_tce_sc_live.py | 5 | Smoke |
| test_transformer.py | 31 | Unit |
| test_transparencia_crawler.py | 98 | Integration |
| test_unified_entity_matching.py | 9 | Unit |
| test_universe.py | 11 | Unit |
| test_upsert_contracts.py | 7 | Integration |
| conftest_db.py | 1 (fixture) | Integration |

### Classificacao dos testes

| Tipo | Quantidade estimada | % |
|------|---------------------|---|
| Unit (pure function mock) | ~380 | 28% |
| Integration (DB real ou mock) | ~950 | 69% |
| Smoke / E2E | ~20 | 1% |
| Fixture/conftest | ~11 | 1% |

### Modulos do caminho critico SEM testes

| Modulo | Path | Risco |
|--------|------|-------|
| **Ingestion transformer** | `scripts/crawl/ingestion/transformer.py` | **STUB** — retorna `records` sem transformar. 0 testes. |
| **Evidence ledger** | `scripts/crawl/loader.py` | Nao ha tests unitarios para o pipeline de upsert/evidence. |
| **Security module** | `scripts/crawl/security.py` | Sem testes. |
| **Redis pool** | `scripts/crawl/redis_pool.py` | Sem testes. |
| **Rate limiter** | `scripts/crawl/rate_limiter.py` | Sem testes. |
| **Geo enrichment** | `scripts/crawl/enricher.py` | Parcial (test_cache_ibge.py testa o cache, nao o enricher em si). |
| **PNCP ARP crawler** | `scripts/crawl/pncp_arp_crawler.py` | Sem testes. |
| **PNCP PCA crawler** | `scripts/crawl/pncp_pca_crawler.py` | Sem testes. |
| **PNCP contract (core constants)** | `scripts/crawl/pncp_contract.py` | Ha `test_pncp_contract.py` (8 tests) — parcial. |
| **PncpOpportunityCrawler** | `scripts/opportunity_intel/pncp_crawler.py` | Sem testes diretos. |
| **Backfill multi-source** | `scripts/pipeline/backfill_multi_source.py` | Sem testes. |
| **State machine coverage** | `scripts/coverage/states.py` | 51% de cobertura de codigo (104 linhas, 51 executadas). |
| **Datalake helper** | `scripts/datalake_helper.py` | Fora do coverage gate. |
| **PNCP engineering** | `scripts/crawl/pncp_engineering.py` | Sem testes. |
| **Checkpoint** | `scripts/crawl/checkpoint.py` | Tem test_checkpoint.py (15 tests) — ok. |
| **Registry** | `scripts/crawl/registry.py` | Sem testes. |

### Modulos gated vs. nao-gated

O `.coveragerc` define coverage gate apenas para:

- `scripts/opportunity_intel` (parcial)
- `scripts/coverage`
- `scripts/contract_intel`
- `scripts/pipeline`
- `scripts/lib/universe.py`
- `scripts/lib/supplier_metrics.py`
- `scripts/lib/price_pipeline.py`
- `scripts/reports`

**NAO gated** (sem verificacao de coverage):

- `scripts/crawl/` — todo o pipeline de ingestaO (crawlers, upsert, monitor)
- `scripts/matching/` — entity matching
- `scripts/lib/` — exceto os 3 arquivos acima
- `scripts/fix/` — scripts de reparo
- `scripts/opportunity_intel/pncp_crawler.py` — dentro do pacote gated mas sem cobertura
- Todos os scripts standalone (`.py` na raiz de `scripts/`)

---

## 3. Qualidade de Testes

### Amostra analisada: 5 arquivos

| Arquivo | Fixtures | Edge cases | Mocks vs Real | Observacao |
|---------|----------|------------|---------------|------------|
| `test_opportunity_dedup.py` | Inline dicts | Testa hash collision, merge, campos nulos | 100% mock (pure functions) | Boa cobertura de casos. Testa que nao faz fuzzy match. Nao testa `numero_edital` com formatacao variante (caso D). |
| `test_freshness_gate.py` | `MagicMock` | SLA stale, never, fresh, conn failure | Mock de `psycopg2.connect`, `_run_snapshot`, `_data_snapshot` | Testa todos os estados de freshness. Env override. Nao testa tabela sem coluna `ingested_at`. |
| `test_crawler_pncp.py` | `MOCK_RAW_RECORD` + classes Response mockadas | JSON invalido, synthetic ID, crawl limit | Mock de `urllib.request.urlopen` e `_fetch_publication_page` | Bom. Testa HTTP 200 com 0 registros, crawl com limit, target invalido. Nao testa timezone, paginasRestantes errado, HTTP 200 com erro. |
| `test_report_dedup.py` | Inline dicts | Stopwords, pure numbers, special chars, empty input | 100% mock (pure functions) | Excelente cobertura de edge cases. Testa Jaccard com conjunto vazio, subset, tokens especiais (R$). |
| `test_entity_matcher.py` | `SAMPLE_ENTITIES` fixture + MagicMock conn | Level 1/2/3, fuzzy abaixo threshold, difflib fallback, cascade priority | Mock de conexao DB. `_make_mock_conn` helper. | Cobre todos os 3 niveis de cascade, prefix match, confidence levels. Nao testa alias matching com municipios diferentes, nem cidades pequenas com threshold adaptativo. |

### Problemas identificados

1. **Predominancia de mocks pesados**: ~69% dos testes sao "integration" mas muitos usam `MagicMock` para DB. Testes de integracao com DB real sao raros (apenas `conftest_db.py` que e desativado por default — 10 testes desativados).

2. **Happy path dominante**: A maioria dos testes cobre o fluxo normal. Casos de erro de API, formatacao inesperada de dados, e corrupcao de dados sao subtestados.

3. **Regression tests ausentes**: Nao ha testes que referenciem bugs anteriores (ex: STORY-2.12 AC4 fallback existe no codigo mas nao tem test de regressao especifico).

4. **Zero testes para o ingestion transformer**: O `scripts/crawl/ingestion/transformer.py` e um STUB e nao tem testes. Se for substituido por implementacao real, nao ha safety net.

5. **Fixtures de banco**: Nao ha fixtures de banco populado com dados realistas de PNCP. Os testes de integracao dependem de banco existente ou mocks.

---

## 4. Cobertura de Codigo

### Gate configurado

Threshold: **80%** para apenas **8 modulos/arquivos** listados no `[coverage_gate]` do `.coveragerc`.

### Modulos gated

| Modulo | Situacao |
|--------|----------|
| `scripts/opportunity_intel` | Coberto parcialmente (alguns arquivos sem testes, ex: `pncp_crawler.py`) |
| `scripts/coverage` | Moderado — `states.py` tem 51% |
| `scripts/contract_intel` | Coberto |
| `scripts/pipeline` | Backfill tem tests |
| `scripts/lib/universe.py` | Coberto |
| `scripts/lib/supplier_metrics.py` | Coberto |
| `scripts/lib/price_pipeline.py` | Coberto |
| `scripts/reports` | Coberto |

### Codebase total nao-gated

Estimativa: ~200+ arquivos Python em `scripts/`. Coverage geral e **~5-10%** quando medido contra toda a base. Os 80% do gate aplicam-se a uma fração minoritária do codigo.

### Modulos com coverage baixa conhecida

| Arquivo | Linhas | Covered | % | Observacao |
|---------|--------|---------|---|------------|
| `scripts/coverage/states.py` | 104 | 51 | 51% | Abaixo do threshold de 80%. O gate falharia se este modulo estivesse corretamente medido. |

---

## 5. Gates Fail-Closed Propostos

Gates que DEVEM falhar (exit code != 0) em cenario de violacao:

### G1 — Recall abaixo do threshold
- **Trigger**: Cobertura entity-level < N% (ex: 95%) no `coverage_manifest.json`
- **Implementacao**: `consulting_readiness.py` ja implementa exit code 2 quando coverage < threshold
- **Estado**: JA EXISTE. Mas o threshold e configurado via CLI (default 95%). Se rodado com `--threshold 0.50`, passa artificialmente.

### G2 — Fonte critica stale (> 48h sem atualizacao)
- **Trigger**: `freshness_gate.py` detecta fonte com `freshness_status != "fresh"`
- **Implementacao**: `freshness_gate.py` ja implementa exit code 2
- **Estado**: JA EXISTE. Mas so monitora 2 fontes (pncp, contracts). Se outras fontes (compras_gov, tce_sc) ficarem stale, o gate nao pega.

### G3 — Crawler retornando 0 registros quando media historica > 0
- **Trigger**: Fontes com historico de N registros/dia retornarem 0
- **Implementacao**: NAO EXISTE. Nao ha comparacao com media historica.
- **Proposta**: Gate que consulta `ingestion_runs` e `pncp_raw_bids` para comparar contagem atual com media dos ultimos 7 dias. Se desvio > 3 sigma, falha.

### G4 — HTTP 200 mas body com padrao de erro
- **Trigger**: Resposta HTTP 200 com JSON contendo `"error"`, `"erro"`, ou `"mensagem"` e sem `"data"`
- **Implementacao**: PARCIAL. `_http_get_json` verifica JSON valido mas nao procura por campos de erro. Se API retorna `{"error": "token invalido"}`, o codigo interpreta como `records=[]`, `empty_confirmed=False` — erro nao silencioso mas mensagem enganosa ("pagina sem dados" vs "erro de autenticacao").
- **Proposta**: Gate que verifica se respostas HTTP 200 tem formato esperado (chave `data` como array). Se nao, loga WARNING e falha se padrao persiste.

### G5 — Paginacao incompleta detectada
- **Trigger**: `totalPaginas` retornado pela API e diferente de `numeroPagina + paginasRestantes`
- **Implementacao**: NAO EXISTE. O loop confia cegamente em `paginasRestantes`.
- **Proposta**: Apos completar um crawl, verificar: `if total_paginas is not None and paginas_restantes is not None: assert numero_pagina + paginas_restantes == total_paginas`. Se falhar, marcar como `pagination_incomplete: True` no FetchResult.

### G6 — Schema do portal de origem mudou (parser quebra)
- **Trigger**: Parser lanca excecao em campos obrigatorios (`numeroControlePNCP`, `objetoCompra`) para > 50% dos registros
- **Implementacao**: PARCIAL. `transform_batch()` ja loga warnings para itens que falham. Mas nao ha gate.
- **Proposta**: Se `transform_batch()` tem taxa de erro > 20%, parar o pipeline com exit code != 0.

### G7 — Disco com menos de 10% livre
- **Trigger**: `shutil.disk_usage('/')` retorna `free/total < 0.10`
- **Implementacao**: NAO EXISTE
- **Proposta**: Pre-crawl health check via `scripts/health_check.py`

### G8 — DB inacessivel
- **Trigger**: Conexao PostgreSQL falha
- **Implementacao**: JA EXISTE. `_get_conn()` em todos os modulos levanta excecao. Freshness gate, readiness gate, e coverage gate falham com exit code 1 ou 2.
- **Estado**: OK. Mas sem retry ou circuit breaker nos gates (apenas nos crawlers).

---

## 6. Violacoes de Honestidade Encontradas

### V1 — "Cobertura 95%" sem denominador claro

- **Onde**: README/CLAUDE.md menciona cobertura de monitoramento
- **Problema**: O unico gate de coverage (`coverage_gate.py`) mede apenas 8 modulos a 80%. O `consulting_readiness.py` mede coverage de entidades (entidades monitoradas / entidades no raio). A metrica de "95% coverage" se refere a ENTIDADES, nao a CODIGO. A documentacao nao distingue as duas metricas.
- **Evidencia**: `.coveragerc` lista apenas 8 modulos. O threshold e 80%, nao 95%.

### V2 — "2085 orgaos" vs. universo real de 1093

- **Onde**: `scripts/crawl/monitor.py` linha 5: "monitoramento de 100% dos 2.085 orgaos publicos de SC"
- **Problema**: A constante `CANONICAL_UNIVERSE = 1093` em `scripts/lib/universe.py` define o universo real como ~1093 entidades. O numero 2085 nao e usado em nenhuma metrica real de coverage. A declaracao "2.085 orgaos" e inflada.
- **Evidencia**: `universe.py` linha 24: `CANONICAL_UNIVERSE = 1093`. O seed file "Extra - alvos de licitacao. R-0.xlsx" contem ~1093 entidades.

### V3 — Fontes declaradas como "disponiveis" mas bloqueadas

- **Onde**: `monitor.py` lista `dom_sc`, `pcp`, `sc_compras`, `transparencia` como sources disponiveis
- **Problema**: Todas essas fontes estao em `SOURCE_BLOCKERS` em `consulting_readiness.py` e `coverage_truth.py`. Nao executam no ambiente atual. A CLI `python scripts/crawl/monitor.py --source all` tentaria roda-las e falharia.
- **Evidencia**: `SOURCE_BLOCKERS` em ambos os arquivos lista `doe_sc`, `dom_sc`, `pcp`, `sc_compras`, `transparencia`, `mides_bigquery` como bloqueados.

### V4 — "Sistema pronto para VPS" sem smoke test completo

- **Onde**: Documentacao operacional
- **Problema**: O unico smoke test que roda de fato (`test_qw01_pncp_smoke.py`) tem 1 teste. O `test_smoke_sources.py` (5 tests) depende de fontes bloqueadas. Varias fontes criticas nao podem ser validadas no ambiente atual.
- **Evidencia**: `tests/smoke/test_qw01_pncp_smoke.py` — 1 teste apenas. SOURCE_BLOCKERS com 6 fontes bloqueadas.

### V5 — Duas implementacoes concorrentes de hash

- **Onde**: `scripts/crawl/pncp_crawler_adapter.py` vs `scripts/crawl/transformer.py`
- **Problema**: O adapter gera `content_hash` incluindo `dataPublicacaoPncp`. O transformer gera hash com apenas `objetoCompra + valorTotalEstimado + situacaoCompra`. Se upsert usa um hash e change-detection usa outro, ha inconsistencia.
- **Evidencia**: `pncp_crawler_adapter.py` linhas 428-438 incluem `data_publicacao` no hash. `transformer.py` linhas 31-43 nao incluem datas.

### V6 — `scripts/crawl/ingestion/transformer.py` e um STUB

- **Onde**: `scripts/crawl/ingestion/transformer.py`
- **Problema**: A funcao `transform_batch()` e declarada como implementacao completa mas e um STUB que retorna os records sem transformacao. Quem importa `from ingestion.transformer import transform_batch` recebe um no-op.
- **Evidencia**: Conteudo do arquivo: `async def transform_batch(records, source="pncp"): return records`. Docstring diz "STUB: Transform raw API records into database format."

### V7 — `scripts/crawl/orchestrator.py` marcado como DEPRECATED mas ainda referenciado

- **Onde**: `scripts/crawl/orchestrator.py`
- **Problema**: O modulo e oficialmente deprecated (linha 24: `DeprecationWarning`) mas ainda pode ser importado por scripts legados. O `monitor.py` e o substituto oficial. Nao ha data de remocao ou migracao forcada.
- **Evidencia**: Docstring do arquivo: "DEPRECATED: Use scripts.crawl.monitor instead."

---

## 7. Recomendacoes para QA Gate

### Imediatas (devem ser implementadas antes da proxima publicacao)

1. **Adicionar validacao de paginacao** no `pncp_crawler_adapter.py`: verificar `totalPaginas == numeroPagina + paginasRestantes`. Se inconsistente, marcar FetchResult com erro.
2. **Unificar as duas implementacoes de content_hash**: adapter transformer devem usar a mesma funcao de hash. Incluir datas no hash para detectar alteracoes de cronograma.
3. **Normalizar numeros de edital** no dedup: remover zeros a esquerda e separadores antes da comparacao (`"001/2024"` -> normalizado para match com `"1/2024"`).
4. **Implementar deteccao de remocao**: apos cada crawl, identificar registros que existem no DB mas nao foram retornados pela API nas N ultimas execucoes. Marcar como `is_active = false`.
5. **Adicionar test para o caso (b)**: garantir que mudanca de data de abertura dispara atualizacao. Testar que `content_hash` inclui datas (ou que o upsert nao depende exclusivamente de hash).

### Curto Prazo

6. **Adicionar os crawlers ao coverage gate**: `scripts/crawl/*` deve estar no `[coverage_gate]` do `.coveragerc`.
7. **Implementar o ingestion transformer real**: substituir o STUB por implementacao que transforma records conforme schema.
8. **Criar smoke tests independentes de fontes bloqueadas**: tests que verificam a pipeline sem depender de `dom_sc`, `doe_sc`, etc.
9. **Testar formatacao variante de numeros de edital**: adicionar tests em `test_opportunity_dedup.py` para `"001/2024"` vs `"1/2024"` vs `"00001/2024"`.
10. **Gate de media historica (G3)**: implementar comparacao contra media de 7 dias para detectar crawlers que retornam 0 registros anomalamente.

### Medio Prazo

11. **Substituir `SOURCE_BLOCKERS` por verificacao real**: ao inves de declarar fontes como bloqueadas estaticamente, implementar health check que testa conectividade e credenciais.
12. **Implementar OCR ou extracao de texto de PDFs**: para anexos escaneados, adicionar pipeline de OCR (Tesseract ou similar) para extrair texto de editais em PDF.
13. **Adicionar coluna de "ultima verificacao" para deteccao de remocao**: cada registro deve saber quando foi visto pela ultima vez na API, para detectar silenciosamente registros removidos.
14. **Reconciliacao de totalPaginas vs registros recebidos**: apos o crawl, verificar se `totalRegistros` declarado pela API corresponde ao total de registros recebidos.

### Proposta de Thresholds para Gates

| Gate | Threshold | Acao se violado |
|------|-----------|-----------------|
| Recall entidades raio 200km | >= 95% | Block push |
| Freshness pncp | <= 24h | Block push, alerta |
| Freshness contracts | <= 7d | Block push, alerta |
| Pagination consistency 0 violations | != 0 | Block crawl, alerta |
| Transform error rate | > 20% | Block crawl |
| DB disponivel | Conexao OK | Block tudo |
| Coverage gate (codigo) | >= 80% | Block push |
| Disco livre | >= 10% | Block crawl |
| Media historica (crawler) | Desvio > 3 sigma | Block crawl, alerta |
