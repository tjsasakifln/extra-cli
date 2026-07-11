# Tasks — Módulo `crawl`

> 🟢 CONFIRMADO — baseado em `monitor.py`, crawlers, `transformer.py`

## Tarefas de Reimplementação

### T1: Interface de Crawler
- **Arquivo legado:** `scripts/crawl/monitor.py:547-569`
- **Confiança:** 🟢
- **Descrição:** Implementar `_load_crawler(source)` com `importlib.import_module`. Mapear source names → módulos Python. Retornar None com log se crawler não encontrado.
- **Critério de pronto:** 8 fontes mapeadas, import dinâmico funcional, fallback para crawler não implementado.

### T2: Conexão PostgreSQL e Load de Entidades
- **Arquivo legado:** `scripts/crawl/monitor.py:58-74`
- **Confiança:** 🟢
- **Descrição:** `_get_conn()` via `psycopg2.connect(DSN)`. `_load_entities()` com query parametrizada, filtro opcional `raio_200km`. Retornar lista de dicts.
- **Critério de pronto:** Conexão funcional, 2.085 entidades carregadas, filtro raio_200km operante.

### T3: Pipeline crawl_source()
- **Arquivo legado:** `scripts/crawl/monitor.py:454-532`
- **Confiança:** 🟢
- **Descrição:** Orquestrar Crawl → Transform → Upsert → Entity Match → Coverage Update. Tratar exceções com try/except, log de erro, `_finish_ingestion_run(status='failed')`.
- **Critério de pronto:** Pipeline completo executado sem erros para fonte PNCP, run registrado em `ingestion_runs`.

### T4: Entity Matching Cascade
- **Arquivo legado:** `scripts/crawl/monitor.py:142-341`
- **Confiança:** 🟢
- **Descrição:** Implementar 3 níveis: CNPJ → nome normalizado + IBGE → fuzzy. Construir índices (dict). Para cada bid, tentar níveis em ordem. Atualizar matched_entity_id, match_method, match_score, match_confidence.
- **Critério de pronto:** Matching funcional nos 3 níveis. Stats (cnpj, name_normalized, fuzzy, unmatched) computados corretamente. Batch commit funcional.

### T5: Content Hash Dedup
- **Arquivo legado:** `scripts/crawl/transformer.py:30-44`
- **Confiança:** 🟢
- **Descrição:** `compute_content_hash(item)` → SHA-256 de `objeto|valor|situacao` canonicalizado (lowercase, strip).
- **Critério de pronto:** Hash determinístico. Mesmo conteúdo → mesmo hash. Conteúdo diferente → hash diferente.

### T6: Coverage Report
- **Arquivo legado:** `scripts/crawl/monitor.py:348-414`
- **Confiança:** 🟢
- **Descrição:** Query SQL cruzando `sc_public_entities` × `entity_coverage`. Agrupar por `raio_200km`. Breakdown por source. Listar uncovered entities within 200km.
- **Critério de pronto:** Query retorna total, covered, uncovered, pct. Breakdown por source funcional. Uncovered list populada.

### T7: Ingestion Run Tracking
- **Arquivo legado:** `scripts/crawl/monitor.py:94-117`
- **Confiança:** 🟢
- **Descrição:** `_start_ingestion_run()` → INSERT com status='running'. `_finish_ingestion_run()` → UPDATE com fetched/upserted/covered/status/error.
- **Critério de pronto:** Cada execução de crawler gera 1 registro em `ingestion_runs` com dados completos.

### T8: PNCP Crawler Adapter
- **Arquivo legado:** `scripts/crawl/pncp_crawler_adapter.py`
- **Confiança:** 🟢
- **Descrição:** Implementar `crawl(mode)` com chunking 1-dia, paginação (50/página, max 50 páginas), delay 500ms, filtro keywords engenharia, modalidades 2,3,4,7. `transform(records)` normalizando para schema unificado.
- **Critério de pronto:** Crawl PNCP funcional. Chunking respeita range de datas. Delay anti-429 funcional. Transform produz schema correto.

### T9: DOM-SC Crawler
- **Arquivo legado:** `scripts/crawl/dom_sc_crawler.py`
- **Confiança:** 🟢
- **Descrição:** Autenticação HTTP Basic Auth (CPF:CNPJ) + header X-API-Key. 3 categorias: 6 (contratos), 7 (convênios), 28 (empenhos). Janela: 90 dias full, 3 dias incremental.
- **Critério de pronto:** Crawl funcional para 3 categorias. Autenticação funcional. Dados normalizados para schema.

### T10: TCE-SC Crawler
- **Arquivo legado:** `scripts/crawl/tce_sc_crawler.py`
- **Confiança:** 🟢
- **Descrição:** SCMWeb JSON API com parâmetro `p285` (TCE-SC). Mapeamento de modalidades (SCMWeb → padrão). 365 dias full, 7 dias incremental. Feature flag `TCE_SC_ENABLED`.
- **Critério de pronto:** Crawl TCE-SC funcional. Mapeamento de modalidades correto. Feature flag respeitada.
