# ERD Completo — Extra Consultoria DataLake

> Gerado pelo Architect em 2026-07-11T22:00:00Z
> doc_level: completo
> PostgreSQL 18.4 com extensões: pg_trgm, uuid-ossp, unaccent, vector

```mermaid
erDiagram
    sc_public_entities ||--o{ pncp_raw_bids : "matched_entity_id (SET NULL)"
    sc_public_entities ||--o{ entity_coverage : "entity_id (CASCADE)"
    pncp_raw_bids ||--o{ entity_coverage : "trigger AFTER INSERT/UPDATE"
    ingestion_runs ||--o{ ingestion_checkpoints : "source reference"

    sc_public_entities {
        serial id PK "identificador interno"
        text razao_social "nome do ente público"
        text cnpj_8 UK "base CNPJ 8 dígitos"
        text municipio "município sede"
        text codigo_ibge "código IBGE 7 dígitos"
        text natureza_juridica "Prefeitura, Câmara, Fundo..."
        double_precision latitude "coordenada"
        double_precision longitude "coordenada"
        double_precision distancia_fk "km de Florianópolis (Haversine)"
        boolean raio_200km "dentro do raio de 200km?"
        boolean is_active "ente ativo?"
        timestamptz created_at "data de criação"
    }

    pncp_raw_bids {
        text pncp_id PK "ID da licitação"
        text objeto_compra "descrição do objeto"
        numeric valor_total_estimado "18,2"
        int modalidade_id "4=Conc 5=PE 6=PP 7=CD 8=Inex"
        text modalidade_nome "nome da modalidade"
        text situacao_compra "situação"
        text esfera_id "F|E|M|D"
        text uf "sigla UF 2 chars"
        text municipio "nome do município"
        text codigo_municipio_ibge "IBGE 7 dígitos"
        text orgao_razao_social "nome do órgão"
        text orgao_cnpj "CNPJ 14 dígitos"
        text unidade_nome "unidade administrativa"
        timestamptz data_publicacao "publicação do edital"
        timestamptz data_abertura "abertura das propostas"
        timestamptz data_encerramento "encerramento"
        text link_sistema_origem "link fonte"
        text link_pncp "link PNCP"
        text content_hash UK "SHA-256 dedup"
        tsvector tsv "full-text search PT-BR"
        text source "pncp|dom_sc|doe_sc|pcp|compras_gov|..."
        text source_id "ID na fonte original"
        int matched_entity_id FK "FK sc_public_entities.id"
        text match_method "cnpj|name_normalized|fuzzy|unmatched"
        decimal match_score "4,3 (0.0-1.0)"
        text match_confidence "high|medium|low"
        vector embedding "256d text-embedding-3-small"
        boolean is_active "soft-delete flag"
        timestamptz ingested_at "data de ingestão"
        timestamptz updated_at "última atualização"
    }

    pncp_supplier_contracts {
        serial id PK "identificador interno"
        text contrato_id UK "ID do contrato PNCP"
        text numero_controle_pncp "número controle"
        text orgao_cnpj "CNPJ órgão"
        text orgao_nome "nome órgão"
        text fornecedor_cnpj "CNPJ fornecedor"
        text fornecedor_nome "nome fornecedor"
        text objeto_contrato "objeto"
        numeric valor_total "18,2"
        date data_inicio "início vigência"
        date data_fim "fim vigência"
        date data_publicacao "publicação"
        text uf "UF do contrato"
        text municipio "município"
        text source "fonte"
        text source_id "ID fonte"
        text content_hash UK "hash dedup"
        timestamptz ingested_at "data ingestão"
    }

    enriched_entities {
        text entity_type PK "cnpj|municipio"
        text entity_id PK "CNPJ 14d|IBGE 7d"
        jsonb data "dados BrasilAPI/IBGE"
        timestamptz enriched_at "data enriquecimento"
        text enriched_source "brasilapi|ibge"
    }

    entity_coverage {
        int entity_id PK_FK "FK sc_public_entities CASCADE"
        text source PK "fonte de dados"
        timestamptz last_seen_at "última aparição"
        int total_bids "total licitações"
        boolean is_covered "coberto 90d?"
        boolean within_200km "raio 200km?"
    }

    coverage_snapshots {
        serial id PK "identificador"
        date snapshot_date "data snapshot"
        text source "fonte"
        int total_entities "total entes"
        int covered_entities "entes cobertos"
        decimal pct_covered "5,2 percentual"
    }

    ingestion_checkpoints {
        text source PK "fonte"
        text scope_key PK "escopo (uf_modalidade)"
        int last_page "última página"
        date last_date "última data"
        text last_id "último ID"
        int records_fetched "total baixado"
        timestamptz updated_at "atualização"
    }

    ingestion_runs {
        serial id PK "identificador"
        text source "fonte"
        timestamptz started_at "início"
        timestamptz finished_at "fim"
        int records_fetched "baixados"
        int records_upserted "inseridos/atualizados"
        int entities_covered "entes cobertos"
        text status "running|completed|failed"
        text error_message "erro se falhou"
        jsonb metadata "metadados extra"
    }
```

## Cardinalidades

| Entidade A | Relação | Entidade B | Cardinalidade |
|-----------|---------|-----------|---------------|
| sc_public_entities | has | pncp_raw_bids | 1:N (matched_entity_id FK, SET NULL) |
| sc_public_entities | has | entity_coverage | 1:N (entity_id FK, CASCADE) |
| pncp_raw_bids | updates | entity_coverage | Trigger (AFTER INSERT/UPDATE) |
| ingestion_runs | references | — | source (sem FK, acoplamento fraco) |

## Índices (33)

| Tabela | Índice | Tipo | Propósito |
|--------|--------|------|-----------|
| pncp_raw_bids | tsv | GIN | Full-text search português |
| pncp_raw_bids | objeto_compra | GIN (trgm) | Trigram similarity |
| pncp_raw_bids | embedding | HNSW | Vector similarity (pgvector) |
| pncp_raw_bids | content_hash | UNIQUE BTREE | Dedup cross-source |
| pncp_raw_bids | (uf, data_publicacao DESC) | BTREE | Filtro geo-temporal |
| pncp_raw_bids | (modalidade_id, data_publicacao DESC) | BTREE | Filtro modalidade |
| pncp_raw_bids | (is_active, data_publicacao DESC) | BTREE (partial) | Purge scans |
| pncp_supplier_contracts | (fornecedor_cnpj, data_publicacao DESC) | BTREE | Competitive intel |
| pncp_supplier_contracts | objeto_contrato | GIN (trgm) | Contract search |
| sc_public_entities | cnpj_8 | BTREE (unique) | Entity matching nivel 1 |
| sc_public_entities | (raio_200km, is_active) | BTREE | Geo-foco filter |
| entity_coverage | (is_covered, within_200km) | BTREE | Coverage dashboard |
| entity_coverage | (source, is_covered) | BTREE | Source breakdown |

## Views (5)

| View | Propósito | Fonte |
|------|----------|-------|
| v_coverage_summary | Cobertura % por source, 90d window | migration 009 |
| v_coverage_gaps | Entes sem cobertura | migration 012 |
| v_coverage_gaps_by_municipio | Gaps agregados por município | migration 012 |
| v_coverage_trend | Tendência semanal com LAG | migration 012 |
| v_unmatched_bids | Bids sem entity match | migration 011 |

## Funções PL/pgSQL (10)

| Função | Tipo | Retorno |
|--------|------|---------|
| search_datalake(10 params) | STABLE | TABLE (13 cols) — FTS + ILIKE |
| upsert_pncp_raw_bids(JSONB) | VOLATILE | TABLE (action, pncp_id, hash) |
| upsert_pncp_supplier_contracts(JSONB) | VOLATILE | TABLE (action, contrato_id) |
| purge_old_bids(INT) | VOLATILE | TABLE (purged, remaining) — soft-delete |
| purge_old_bids_hard(INT) | VOLATILE | Hard-delete pós soft-retention |
| ttl_cleanup_enriched_entities(INT) | VOLATILE | TTL cache cleanup |
| set_updated_at() | TRIGGER | BEFORE UPDATE — auto timestamp |
| update_entity_coverage() | TRIGGER | AFTER INSERT — coverage tracking |
| update_entity_coverage_on_update() | TRIGGER | AFTER UPDATE — re-match tracking |
| generate_coverage_snapshot(DATE) | VOLATILE | Snapshot semanal por source |
