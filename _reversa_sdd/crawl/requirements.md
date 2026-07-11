# Requirements — Módulo `crawl`

> 🟢 CONFIRMADO — extraído de `scripts/crawl/monitor.py`, `pncp_crawler_adapter.py`, `dom_sc_crawler.py`, `pcp_crawler.py`, `tce_sc_crawler.py`, `transformer.py`, `enricher.py`

## Funcionais (FR)

| ID | Requisito | Fonte | Confiança |
|----|-----------|-------|-----------|
| FR-C1 | Coletar licitações de 8 fontes: PNCP, DOM-SC, PCP v2, ComprasGov v3, SC Compras, Contratos PNCP, TCE-SC (SCMWeb), Portais Transparência | `monitor.py:44` | 🟢 |
| FR-C2 | Pipeline por source: Crawl → Transform → Upsert → Entity Match → Coverage Update | `monitor.py:454-532` | 🟢 |
| FR-C3 | Entity matching em 3 níveis: CNPJ exato → nome normalizado + IBGE → fuzzy (rapidfuzz/difflib) | `monitor.py:142-341` | 🟢 |
| FR-C4 | Dedup por content hash (SHA-256 de objeto+valor+situação canonicalizados) | `transformer.py:30-44` | 🟢 |
| FR-C5 | Modos de crawl: full (completo), incremental (delta), dry-run | `monitor.py:589-591` | 🟢 |
| FR-C6 | Suporte a --report-coverage (relatório sem crawl) | `monitor.py:593-596` | 🟢 |
| FR-C7 | Filtro por raio 200km (--within-200km-only) | `monitor.py:598-601` | 🟢 |
| FR-C8 | Enriquecimento cadastral via BrasilAPI (CNPJ) + IBGE (municípios) com TTL 30 dias | `enricher.py:24` | 🟢 |
| FR-C9 | Auditoria de cada execução em `ingestion_runs` (fetched, upserted, covered, status, erro) | `monitor.py:94-117` | 🟢 |
| FR-C10 | Crawl resumable via `ingestion_checkpoints` (cursor_data JSONB) | `db/migrations/004` | 🟢 |
| FR-C11 | PNCP com chunking 1-dia, delay 500ms entre páginas, filtro keywords engenharia | `pncp_crawler_adapter.py:33-55` | 🟢 |
| FR-C12 | DOM-SC: 3 categorias (contratos=6, convênios=7, empenhos=28), HTTP Basic Auth + API Key | `dom_sc_crawler.py:40-68` | 🟢 |
| FR-C13 | TCE-SC via SCMWeb JSON API, 365 dias full, 7 dias incremental | `tce_sc_crawler.py:58-61` | 🟢 |

## Não Funcionais (NFR)

| ID | Requisito | Evidência | Confiança |
|----|-----------|-----------|-----------|
| NFR-C1 | Timeout HTTP: 15-60s por requisição (varia por fonte) | `config/settings.py:55`, `dom_sc_crawler.py:52` | 🟢 |
| NFR-C2 | Rate limiting: delay 500ms-2s entre requisições | `pncp_crawler_adapter.py:38`, `tce_sc_crawler.py:52` | 🟢 |
| NFR-C3 | Max páginas PNCP: 50 (PAGE_SIZE=100 → 5000 registros max) | `config/settings.py:53` | 🟢 |
| NFR-C4 | Retry com max 1-3 tentativas (varia por fonte) | `pncp_crawler_adapter.py:37`, `tce_sc_crawler.py:55` | 🟢 |
| NFR-C5 | Purge de registros >400 dias (diário 04:00 UTC) | `config/settings.py:92` | 🟢 |
| NFR-C6 | Enriquecimento assíncrono com semáforo(10) — max 10 chamadas concorrentes | `enricher.py:28` | 🟢 |

## Critérios de Aceitação

**AC-C1: Crawl bem-sucedido de uma fonte**
- Dado que o sistema tem acesso à API da fonte
- Quando executo `monitor.py --source pncp --mode full`
- Então os registros são coletados, transformados, upsertados no banco e o entity matching é executado
- E um registro em `ingestion_runs` é criado com status `completed`

**AC-C2: Dedup impede duplicatas**
- Dado que uma licitação com mesmo conteúdo já existe no banco
- Quando o mesmo registro é re-ingerido
- Então o upsert atualiza o registro existente (não cria duplicata)
- E `records_upserted` reflete apenas inserções novas

**AC-C3: Entity matching identifica órgão**
- Dado que uma licitação tem `orgao_cnpj` que corresponde a um `cnpj_8` em `sc_public_entities`
- Quando o entity matching é executado
- Então `matched_entity_id` é preenchido, `match_method = 'cnpj'`, `match_score = 1.0`, `match_confidence = 'high'`

**AC-C4: Crawler não implementado é tratado**
- Dado que uma fonte não tem crawler implementado
- Quando executo `monitor.py --source <fonte>`
- Então `_load_crawler()` retorna None e a execução é registrada como `failed` com mensagem "Crawler not implemented"

## MoSCoW

| Prioridade | Requisitos |
|-----------|-----------|
| **Must** | FR-C1, FR-C2, FR-C3, FR-C4, FR-C9 |
| **Should** | FR-C5, FR-C6, FR-C7, FR-C8, FR-C10, FR-C11, FR-C12, FR-C13 |
| **Could** | — |
| **Won't** | Crawler SICAF (requer Playwright, não instalado) |
