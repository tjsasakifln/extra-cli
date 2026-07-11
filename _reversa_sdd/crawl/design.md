# Design — Módulo `crawl`

> 🟢 CONFIRMADO — extraído de `monitor.py`, `transformer.py`, `enricher.py`, `db/migrations/`

## Arquitetura Interna

```
monitor.py (orquestrador)
  ├── parse_args() → source, mode, report-coverage, within-200km-only, dsn
  ├── _get_conn() → psycopg2.connect(DSN)
  ├── _load_entities(conn, within_200km_only) → list[dict]
  ├── crawl_source(source, entities, mode) → dict (status, fetched, upserted, matched)
  │     ├── _load_crawler(source) → module | None (importlib.import_module)
  │     ├── crawler.crawl(mode) → list[dict] (raw records)
  │     ├── crawler.transform(records) → list[dict] (normalized)
  │     ├── upsert_pncp_raw_bids(records) → RPC PostgreSQL
  │     ├── _match_entities_cascade(conn, source, entities) → stats dict
  │     └── _finish_ingestion_run(conn, run_id, ...) → void
  ├── report_coverage(conn) → dict (groups, by_source, uncovered)
  └── print_coverage_report(result) → terminal output
```

## Interface de Crawler

Todo crawler deve expor:

```python
def crawl(mode: str) -> list[dict]:
    """Coleta dados brutos da fonte.
    mode: 'full' | 'incremental' | 'dry-run'
    Retorna lista de dicts com dados brutos da API."""

def transform(records: list[dict]) -> list[dict]:
    """Normaliza registros para schema pncp_raw_bids.
    Retorna lista de dicts prontos para upsert."""
```

## Fluxo de Entity Matching

```
_match_entities_cascade(conn, source, entities)
  │
  ├── 1. Busca unmatched bids (WHERE matched_entity_id IS NULL)
  │
  ├── 2. Constrói índices de busca:
  │     cnpj_index: dict[cnpj_8, entity]
  │     name_exact_index: dict[norm_name, entity]
  │     name_muni_index: dict[(norm_name, ibge), entity]
  │     all_entities_norm: list[entity] (com _normalized_name)
  │
  ├── 3. Para cada bid:
  │     ├── Level 1: CNPJ (score=1.0, confidence=high)
  │     │   Match exato de 8 dígitos ou prefixo de 14 dígitos
  │     │
  │     ├── Level 2a: Nome normalizado + IBGE (score=1.0, confidence=high)
  │     │   Match exato de (nome_norm, codigo_ibge)
  │     │
  │     ├── Level 2b: Nome normalizado sem IBGE (score=1.0, confidence=high)
  │     │   Match exato de nome_norm apenas
  │     │
  │     ├── Level 3: Fuzzy (score=ratio, confidence=high/medium/low)
  │     │   rapidfuzz.ratio() ou SequenceMatcher.ratio()
  │     │   Filtra candidatos por IBGE se disponível
  │     │   Threshold: 0.85 (ENTITY_MATCH_FUZZY_THRESHOLD)
  │     │   Confidence: >=0.95=high, >=threshold=medium, <threshold=low
  │     │
  │     └── Unmatched: match_method='unmatched', score=0.0
  │
  └── 4. COMMIT em batch (todas as atualizações de uma vez)
```

## Schema de Dados

Registros normalizados seguem o schema de `pncp_raw_bids`:
- `pncp_id` (PK), `objeto_compra`, `valor_total_estimado`, `modalidade_id/nome`
- `esfera_id`, `uf`, `municipio`, `codigo_municipio_ibge`
- `orgao_razao_social`, `orgao_cnpj`, `data_publicacao/abertura/encerramento`
- `link_pncp`, `content_hash` (SHA-256), `source`, `source_id`
- Campos de match: `matched_entity_id`, `match_method`, `match_score`, `match_confidence`

## Decisões de Design

| Decisão | Escolha | Razão |
|---------|---------|-------|
| Interface de crawler | `crawl(mode)` + `transform(records)` | Simples, compatível com import dinâmico |
| Carregamento dinâmico | `importlib.import_module()` | Adicionar fonte = adicionar módulo, sem alterar monitor.py |
| Entity matching | Cascade 3 níveis em Python (não SQL) | Lógica complexa de normalização + fuzzy, mais legível em Python |
| Upsert | RPC PostgreSQL (`upsert_pncp_raw_bids`) | Performance de batch, ON CONFLICT handling no DB |
| Commit do matching | Batch único após todos os bids | Evita N round-trips ao DB |
