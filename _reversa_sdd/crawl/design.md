# Crawl — Design

> Gerado pelo Writer em 2026-07-11T22:30:00Z | doc_level: completo

## Arquitetura do Pipeline

```
crawl_source(source, entities, mode) →
  load_crawler(source) → crawler.crawl(mode) → crawler.transform(records) →
  upsert(records) → match_entities_cascade(conn, source, entities) →
  save_checkpoint() → finish_ingestion_run()
```

Cada crawler é um módulo Python que expõe `crawl(mode)→list[dict]` e `transform(records)→list[dict]`.

## Interfaces dos Crawlers

```python
# Interface comum (10 crawlers sync)
def crawl(mode: str = "full") -> list[dict]:
    """Retorna registros crus da API/portal."""

def transform(records: list[dict]) -> list[dict]:
    """Converte registros crus → schema pncp_raw_bids (31 colunas)."""
```

## Schema de Saída (pncp_raw_bids — 31 colunas)

Campos chave: `pncp_id` PK, `objeto_compra`, `valor_total_estimado` NUMERIC(18,2), `modalidade_id` INT, `esfera_id` TEXT(F|E|M|D), `uf` TEXT, `municipio` TEXT, `orgao_razao_social` TEXT, `orgao_cnpj` TEXT, `data_publicacao` TIMESTAMPTZ, `content_hash` TEXT UNIQUE (SHA-256), `source` TEXT, `matched_entity_id` INT FK, `is_active` BOOLEAN.

## Orquestradores (2)

| Arquivo | Linhas | Status |
|---------|--------|--------|
| `monitor.py` | 684 | Legado — entity matching inline, 8 sources |
| `orchestrator.py` | 306 | Refatorado — checkpoint TD-5.2, matching externo, 10 sources (inclui doe_sc) |

## Matriz de Crawlers

| Crawler | Arquivo | Auth | Paginação | Retry | Esfera |
|---------|---------|------|-----------|-------|--------|
| PNCP | `pncp_crawler_adapter.py` | Public | offset+has_next | 2× 2^N | F/E/M |
| DOM-SC | `dom_sc_crawler.py` | Basic+APIKey | 3 categorias | 0 | M |
| DOE-SC | `doe_sc_crawler.py` | Bearer(login) | offset+totalPages | 2× 2^N | E |
| PCP v2 | `pcp_crawler.py` | Public | offset+pageCount | 2× 2^N | F/E/M |
| ComprasGov | `compras_gov_crawler.py` | Public | offset+paginasRestantes | 2× 2^N×2 | F |
| Contracts | `contracts_crawler.py` | Public | offset+totalPaginas | 3× 2^N | F/E/M |
| TCE-SC | `tce_sc_crawler.py` | Public | heurística(<20) | 3× 2^N | E |
| SC Compras | `sc_compras_crawler.py` | Public | HTML regex | 3× 2×N | E |
| Transparência | `transparencia_crawler.py` | Public | N/A | 1× | M |

## Infraestrutura Compartilhada

| Módulo | Função |
|--------|--------|
| `common.py` | Helpers: digits_only, safe_float, parse_date, generate_content_hash |
| `checkpoint.py` | Sync (psycopg2) + Async (Supabase). Tabela ingestion_checkpoints |
| `security.py` | USER_AGENT padronizado, sanitize_url_param, make_url |
| `circuit_breaker.py` | 5 singletons (pncp, pcp, comprasgov, brasilapi, ibge) |
| `retry.py` | validate_timeout_chain, calculate_delay |
| `transformer.py` | compute_content_hash SHA-256, transform_pncp_item |
| `loader.py` | bulk_upsert, embedding opcional text-embedding-3-small |
| `sanctions.py` | SanctionsChecker async CEIS+CNEP, cache 24h |
| `enricher.py` | 3 jobs ARQ: entities, municipios, ibge_codes |

## Transparência Templates

| Template | Plataforma | Mun. SC | URL Pattern |
|----------|-----------|---------|-------------|
| `betha.py` | Betha Sistemas | ~80 | `{slug}.atende.net/transparencia` |
| `ipam.py` | Ipam | ~50 | `{slug}.ipm.org.br/transparencia` |
| `egov.py` | E-gov Betha | ~40 | `{slug}.e-gov.betha.com.br` |
| `generico.py` | Fallback | ∞ | Score tables → divs → any table |

## Confiança

🟢 CONFIRMADO — Todos os 35 arquivos lidos. 10 crawlers sync verificados com interface comum. 3 GAPs: orquestrador dual, checkpoint dual, imports quebrados em _parallel_mixin.py.
