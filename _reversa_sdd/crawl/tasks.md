# Crawl — Tasks

> Gerado pelo Writer em 2026-07-11T22:30:00Z | doc_level: completo

## Tarefas de Reimplementação

| # | Tarefa | Fonte | Critério de Pronto | Confiança |
|---|--------|-------|-------------------|-----------|
| T-C01 | Implementar interface Crawler: `crawl(mode)→list[dict]`, `transform(records)→list[dict]` | `pncp_crawler_adapter.py:1-294` | 10 crawlers implementam mesma interface | 🟢 |
| T-C02 | Implementar PNCP crawler: GET com urllib, paginação day-by-day, filtro UF/modalidade, 17 keywords engenharia | `pncp_crawler_adapter.py:crawl()` | Retorna records com pncp_id+content_hash para SC | 🟢 |
| T-C03 | Implementar DOM-SC crawler: Basic Auth + X-API-Key, 3 categorias | `dom_sc_crawler.py:1-360` | 3 categorias agregadas, esfera_id='M' | 🟢 |
| T-C04 | Implementar DOE-SC crawler: Bearer token com login, cache 30min, filtro categorias | `doe_sc_crawler.py:1-728` | Token renovado em 401 | 🟢 |
| T-C05 | Implementar PCP v2 crawler: 14 entradas modalidade mapping, inferência esfera | `pcp_crawler.py:1-438` | Modalidade mapeada com fuzzy fallback | 🟢 |
| T-C06 | Implementar ComprasGov crawler: 2 endpoints, auto-detecção em transform() | `compras_gov_crawler.py:1-612` | Dados legado + Lei 14.133 unificados | 🟢 |
| T-C07 | Implementar Contracts crawler: janelas 90 dias, inferência UF por CNPJ | `contracts_crawler.py:1-371` | Schema pncp_supplier_contracts | 🟢 |
| T-C08 | Implementar TCE-SC crawler: SCMWeb, licitações+contratos, 2 fases | `tce_sc_crawler.py:1-767` | Paginação heurística (<20 itens = fim) | 🟢 |
| T-C09 | Implementar SC Compras crawler: HTML regex, detail pages | `sc_compras_crawler.py:1-605` | Extração de 29 labels via _LABEL_MAP | 🟢 |
| T-C10 | Implementar Transparência crawler: 4 templates, detect_platform | `transparencia_crawler.py:1-1221` | Betha→Ipam→E-gov→Genérico fallback | 🟢 |
| T-C11 | Implementar transforms: content_hash SHA-256, normalização datas/valores | `common.py:1-213` | Todos os campos mapeados, hash determinístico | 🟢 |
| T-C12 | Implementar upsert RPC: ON CONFLICT content_hash DO NOTHING | `db/migrations/006_upsert_rpcs.sql` | Idempotente, sem duplicatas | 🟢 |
| T-C13 | Integrar entity_matcher.cascade no pipeline pós-upsert | `entity_matcher.py:1-297` | matched_entity_id preenchido após upsert | 🟢 |
| T-C14 | Implementar coverage triggers: AFTER INSERT/UPDATE → entity_coverage | `db/migrations/009_indexes_and_coverage.sql` | is_covered, total_bids, last_seen_at OK | 🟢 |
| T-C15 | Implementar checkpoint: save + is_crawl_completed_today | `checkpoint.py:1-448` | Retomada sem re-processamento | 🟢 |
| T-C16 | Implementar circuit breaker: 5 singletons, Redis-backed | `circuit_breaker.py:1-523` | Degraded mode após 3 falhas consecutivas | 🟢 |
| T-C17 | Implementar retry com exponential backoff 2^N | `retry.py:1-285` | Timeout chain validado em startup | 🟢 |
| T-C18 | Implementar sanctions checker: CEIS+CNEP async, cache 24h | `sanctions.py:1-640` | is_sanctioned flag, rate limit 90/min | 🟢 |
| T-C19 | Implementar enricher: 3 jobs ARQ, cache TTL 7-30 dias | `enricher.py:1-670` | CNPJ enrichment + IBGE codes + municipios | 🟢 |
| T-C20 | Configurar systemd timers: 20 serviços com schedule | `deploy/systemd/*.timer` | Crawlers executam nas frequências definidas (R12) | 🟢 |

## Dependências entre Tarefas

```
T-C01 (interface) → T-C02..T-C10 (crawlers)
T-C11 (transforms) → T-C12 (upsert)
T-C12 → T-C13 (matching) → T-C14 (coverage)
T-C15 (checkpoint) → T-C02 (integração no incremental)
T-C16..T-C17 (resiliência) → T-C02..T-C10 (todos crawlers)
T-C20 (deploy) → após todos os crawlers funcionais
```

## Estimativa de Esforço

| Categoria | Tarefas | Esforço estimado |
|-----------|---------|-----------------|
| Crawlers (8) | T-C02..T-C10 | 8-12 dias |
| Infraestrutura | T-C11..T-C19 | 4-6 dias |
| Deploy | T-C20 | 1 dia |
| **Total** | 20 tarefas | **13-19 dias** |
