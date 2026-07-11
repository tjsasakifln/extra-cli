# Crawl — Multi-Source Ingestion

> Gerado pelo Writer em 2026-07-11T22:30:00Z | doc_level: completo | Base: e9729e1

## Visão Geral

Pipeline de ingestão multi-source: 10 crawlers sync, 8 fontes externas, 4 templates de transparência. Coleta, transforma, faz upsert com dedup SHA-256, vincula a entes públicos SC e atualiza cobertura.

## Responsabilidades

- Coletar licitações de 8 fontes (PNCP, DOM-SC, DOE-SC, PCP, ComprasGov, TCE-SC, SC Compras, Portais Transparência)
- Transformar registros crus em schema unificado `pncp_raw_bids` (31 colunas)
- Upsert idempotente: ON CONFLICT content_hash DO NOTHING
- Entity matching cascade (CNPJ → nome+município → fuzzy)
- Tracking de cobertura via triggers PostgreSQL
- Checkpointing para retomada de crawls interrompidos
- Rate limiting adaptativo com circuit breaker

## Regras de Negócio

- R1: 17 keywords de engenharia filtram PNCP — sem match = descarte 🟢
- R2: Cobertura = ente com ≥1 licitação em 90 dias 🟢
- R8: Dedup cross-source por SHA-256 🟢
- R12: Frequência por fonte (PNCP full diário, DOM-SC 3×/dia, Transparência semanal) 🟢

## Requisitos Funcionais

| ID | Requisito | Prioridade | Fonte |
|----|-----------|-----------|-------|
| RF-C01 | Crawl PNCP com paginação day-by-day, filtro UF/modalidade | Must | `pncp_crawler_adapter.py:1-294` |
| RF-C02 | Crawl DOM-SC com Basic Auth, 3 categorias | Must | `dom_sc_crawler.py:1-360` |
| RF-C03 | Crawl DOE-SC com Bearer token, cache 30min | Must | `doe_sc_crawler.py:1-728` |
| RF-C04 | Crawl PCP v2 com fuzzy modalidade mapping | Should | `pcp_crawler.py:1-438` |
| RF-C05 | Crawl ComprasGov (legado + Lei 14.133) | Must | `compras_gov_crawler.py:1-612` |
| RF-C06 | Crawl contratos PNCP com janelas 90 dias | Must | `contracts_crawler.py:1-371` |
| RF-C07 | Crawl TCE-SC via SCMWeb | Should | `tce_sc_crawler.py:1-767` |
| RF-C08 | Scraping transparência: 4 templates (Betha,Ipam,E-gov,Genérico) | Should | `transparencia_crawler.py:1-1221` |
| RF-C09 | Transformar → schema unificado com content_hash | Must | `common.py:1-213` |
| RF-C10 | Upsert batch: ON CONFLICT content_hash DO NOTHING | Must | `upsert_pncp_raw_bids()` |
| RF-C11 | Entity matching cascade pós-upsert | Must | `entity_matcher.py:1-297` |
| RF-C12 | Atualizar entity_coverage via triggers | Must | `migration 009` |
| RF-C13 | Checkpoint para retomada de crawls | Should | `checkpoint.py:1-448` |
| RF-C14 | Verificar checkpoint antes de incremental | Should | `orchestrator.py:crawl_source()` |
| RF-C15 | Rate limiting adaptativo + circuit breaker | Must | `circuit_breaker.py:1-523` |
| RF-C16 | URL sanitization + User-Agent padronizado | Must | `security.py:1-102` |

## Requisitos Não Funcionais

| Tipo | Requisito | Evidência | Confiança |
|------|----------|----------|-----------|
| Performance | Timeout modalidade(20s) < UF(30s) | `_parallel_mixin.py:validate_timeout_chain()` | 🟢 |
| Disponibilidade | Exponential backoff 2^N em 7 crawlers | MAX_RETRIES=2-3 em todos | 🟢 |
| Disponibilidade | Circuit breaker → degraded mode (3 UFs) | `circuit_breaker.py:523` | 🟢 |
| Segurança | Credenciais via env vars (TD-1.2) | `settings.py` | 🟢 |
| Segurança | SSL verify + URL sanitize | `security.py:SSL_VERIFY_ENABLED=True` | 🟢 |

## Critérios de Aceitação

```gherkin
Cenário: Crawl PNCP full SC
Dado PNCP API acessível e mode="full" 90 dias
Quando crawler PNCP executa
Então retorna registros com pncp_id + content_hash SHA-256
E descarta registros sem keywords de engenharia
E paginação percorre todos os dias disponíveis

Cenário: Incremental skip por checkpoint
Dado is_crawl_completed_today() = True para source "pncp"
Quando orchestrator.crawl_source("pncp", mode="incremental")
Então retorna skipped_by_checkpoint=True sem chamadas HTTP

Cenário: Circuit breaker abre após 3 falhas
Dado PNCP API falha 3× consecutivas
Então estado → degraded por cooldown_seconds
E try_recover() testa com 1 request após cooldown
```
