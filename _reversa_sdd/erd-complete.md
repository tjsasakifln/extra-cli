# ERD Completo — Extra Consultoria DataLake

> Gerado pelo Architect em 2026-07-11T15:00:00Z
> 🟢 CONFIRMADO — baseado em 12 migrations SQL, `data-dictionary.md`

---

```mermaid
erDiagram
    sc_public_entities ||--o{ pncp_raw_bids : "matched_entity_id (FK)"
    sc_public_entities ||--o{ entity_coverage : "entity_id (FK)"
    pncp_raw_bids ||--o{ pncp_supplier_contracts : "orgao_cnpj reference"
    ingestion_runs ||--o{ pncp_raw_bids : "run_id → source tracking"
    enriched_entities ||--o{ pncp_raw_bids : "orgao_cnpj → cnpj"
    entity_coverage }o--|| coverage_snapshots : "snapshot aggregation"

    sc_public_entities {
        int id PK "SERIAL"
        text razao_social "Nome do órgão"
        text cnpj_8 "Base CNPJ 8 dígitos"
        text municipio "Município"
        text codigo_ibge "Código IBGE 7 dígitos"
        text natureza_juridica "Natureza jurídica"
        boolean raio_200km "Dentro do raio 200km?"
        boolean is_active "Ativo?"
        timestamptz created_at
        timestamptz updated_at
    }

    pncp_raw_bids {
        text pncp_id PK "numeroControlePNCP ou hash"
        text objeto_compra "Descrição do objeto"
        numeric valor_total_estimado "Valor R$ (18,2)"
        int modalidade_id "4=Concorrência, 5=Pregão..."
        text modalidade_nome
        int esfera_id "1=Federal, 2=Estadual, 3=Municipal"
        text uf "Sigla UF"
        text municipio "Nome do município"
        text codigo_municipio_ibge "IBGE 7 dígitos"
        text orgao_razao_social "Órgão publicante"
        text orgao_cnpj "CNPJ 14 dígitos"
        date data_publicacao
        date data_abertura
        date data_encerramento
        text link_pncp "URL do edital"
        text content_hash UNIQUE "SHA-256 dedup"
        tsvector tsv "FTS PT-BR"
        text source "pncp|dom_sc|pcp|compras_gov|sc_compras|contracts|transparencia|tce_sc"
        text source_id "ID original na fonte"
        int matched_entity_id FK "→ sc_public_entities.id"
        text match_method "cnpj|name_normalized|fuzzy|unmatched"
        numeric match_score "0.0-1.0"
        text match_confidence "high|medium|low"
        timestamptz ingested_at
        timestamptz updated_at
        boolean is_active "Soft delete"
    }

    pncp_supplier_contracts {
        int id PK "SERIAL"
        text supplier_cnpj "CNPJ fornecedor"
        text supplier_name "Nome fornecedor"
        numeric contract_value "Valor R$"
        date contract_date "Data contrato"
        text orgao "Órgão contratante"
        text uf "UF"
        text municipio "Município"
        text modalidade "Modalidade"
        text pncp_contract_id "ID PNCP"
        timestamptz ingested_at
    }

    enriched_entities {
        text cnpj PK "CNPJ 14 dígitos"
        text razao_social "Razão social"
        text nome_fantasia "Nome fantasia"
        text cnae_principal "CNAE principal"
        text[] cnae_secundarios "CNAEs secundários"
        text municipio "Município"
        text uf "UF"
        text natureza_juridica
        text porte "Porte empresa"
        text entity_type "fornecedor|orgao"
        timestamptz enriched_at "TTL: 30 dias"
        jsonb raw_data "Dados brutos API"
    }

    entity_coverage {
        int entity_id PK_FK "→ sc_public_entities.id"
        text source PK "Fonte de dados"
        boolean is_covered "Coberto?"
        boolean within_200km "Raio 200km?"
        timestamptz last_seen_at "Último bid"
        int bid_count "Total bids"
        timestamptz first_seen_at "Primeiro bid"
    }

    ingestion_runs {
        int id PK "SERIAL"
        text source "Fonte"
        text status "running|completed|failed"
        int records_fetched
        int records_upserted
        int entities_covered
        timestamptz started_at
        timestamptz finished_at
        text error_message
        jsonb cursor_data
    }

    ingestion_checkpoints {
        text source PK "Fonte"
        timestamptz last_crawl_at
        text last_pncp_id
        text mode "full|incremental"
        jsonb cursor_data "Página, offset, etc."
    }

    coverage_snapshots {
        date snapshot_date PK
        int total_entities
        int covered_entities
        numeric coverage_pct "5,1"
        int uncovered_within_200km
        jsonb by_source "Breakdown por fonte"
    }
```

## Cardinalidades

| Relacionamento | Cardinalidade | Descrição |
|---------------|---------------|-----------|
| sc_public_entities → pncp_raw_bids | 1:N | Um órgão pode ter N licitações matched |
| sc_public_entities → entity_coverage | 1:N | Um órgão tem coverage tracking por source |
| pncp_raw_bids → pncp_supplier_contracts | N:M (via orgao_cnpj) | Licitações e contratos relacionados por CNPJ |
| enriched_entities → pncp_raw_bids | 1:N (via CNPJ) | Entidade enriquecida referenciada por N licitações |

## Índices Principais

| Tabela | Índice | Tipo | Propósito |
|--------|--------|------|-----------|
| pncp_raw_bids | `idx_bids_tsv` | GIN | Full-text search PT-BR |
| pncp_raw_bids | `idx_bids_uf_data` | B-tree | Filtro UF + data |
| pncp_raw_bids | `idx_bids_source` | B-tree | Filtro por fonte |
| pncp_raw_bids | `idx_bids_matched_entity` | B-tree (partial) | Lookup de órgão matched |
| pncp_raw_bids | `idx_bids_active` | B-tree (partial) | Exclusão de soft-deleted |
| pncp_raw_bids | `content_hash_key` | UNIQUE | Dedup |
| sc_public_entities | `idx_entities_cnpj8` | B-tree | Match CNPJ base |
| sc_public_entities | `idx_entities_ibge` | B-tree | Match por município |
| entity_coverage | `idx_coverage_entity_source` | UNIQUE | (entity_id, source) |
| ingestion_runs | `idx_runs_source_started` | B-tree | Auditoria por fonte |
