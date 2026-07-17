# ERD Completo — Extra Consultoria

> Architect 2026-07-17 🟢 (migrations 001–054 + models código)

```mermaid
erDiagram
    SC_PUBLIC_ENTITIES ||--o{ ENTITY_SOURCE_REGISTRY : "canonical entity"
    SC_PUBLIC_ENTITIES ||--o{ COVERAGE_EVIDENCE : "per source evidence"
    SC_PUBLIC_ENTITIES ||--o{ PNCP_RAW_BIDS : "matched"
    SC_PUBLIC_ENTITIES ||--o{ PNCP_SUPPLIER_CONTRACTS : "matched"
    SC_PUBLIC_ENTITIES ||--o{ OPPORTUNITY_INTEL : "opportunities"

    SOURCE_INFO ||--o{ COVERAGE_EVIDENCE : "source_id"
    SOURCE_INFO ||--o{ INGESTION_RUNS : "source"
    SOURCE_INFO ||--o{ PIPELINE_WATERMARKS : "source"
    SOURCE_INFO ||--o{ DLQ_ENTRIES : "source"

    INGESTION_RUNS ||--o{ OFFICIAL_ACT_RESOURCES : "run_id soft"
    OFFICIAL_ACT_RESOURCES ||--o{ OFFICIAL_ACTS : "resource"
    OFFICIAL_ACTS ||--o{ OFFICIAL_ACT_CLASSIFICATIONS : "history"
    OFFICIAL_ACTS ||--o{ OFFICIAL_ACT_LINKS : "docs"
    OFFICIAL_ACTS ||--o{ OFFICIAL_ACT_MATCHES : "to PNCP"
    OFFICIAL_ACTS ||--o{ OFFICIAL_ACT_SOURCE_LINKS : "multi-obs"

    PNCP_RAW_BIDS ||--o{ OFFICIAL_ACT_MATCHES : "bid match"
    PNCP_SUPPLIER_CONTRACTS ||--o{ OFFICIAL_ACT_MATCHES : "contract match"

    PIPELINE_RUNS ||--o{ DLQ_ENTRIES : "run_id"
    PIPELINE_RUNS ||--o{ PIPELINE_WATERMARKS : "run_id"
    PIPELINE_RUNS ||--o{ COVERAGE_EVIDENCE : "run_id"

    ENRICHED_ENTITIES ||--o{ ENTITY_ALIASES : "aliases"
    SC_PUBLIC_ENTITIES ||--o{ ENRICHED_ENTITIES : "enrichment"

    SC_PUBLIC_ENTITIES {
        text id PK
        text cnpj
        text razao_social
        boolean raio_200km
        boolean is_active
        float distance_km
    }

    ENTITY_SOURCE_REGISTRY {
        bigserial id PK
        text canonical_id UK
        text cnpj
        text natureza_juridica
        text access_status
        text integration_type
        text[] plataformas
        jsonb evidences
        float mapping_confidence
        int priority
    }

    COVERAGE_EVIDENCE {
        bigserial id PK
        text entity_id
        text source
        text state
        text request_scope
        int pages_fetched
        int pages_expected
        jsonb provenance
        boolean satisfactory
        text run_id
        text error_code
    }

    OFFICIAL_ACT_RESOURCES {
        bigserial id PK
        text source
        text resource_id
        text content_sha256
        text fetch_status
        text run_id
    }

    OFFICIAL_ACTS {
        bigserial id PK
        text source
        text external_id
        text record_hash
        text title
        date publication_date
        text date_semantics
        jsonb raw_json
    }

    OFFICIAL_ACT_MATCHES {
        bigserial id PK
        bigint act_id FK
        text target_type
        text target_id
        text rule_name
        float score
    }

    PNCP_RAW_BIDS {
        text id PK
        text objeto_compra
        numeric valor_total_estimado
        text match_method
        text content_hash
    }

    PNCP_SUPPLIER_CONTRACTS {
        text id PK
        numeric valor_global
        text fornecedor_cnpj
        date vigencia_fim
    }

    OPPORTUNITY_INTEL {
        bigserial id PK
        text status_canonical
        float score
        text triage
        text entity_id
    }

    DLQ_ENTRIES {
        bigserial id PK
        text source
        text run_id
        text phase
        jsonb payload
        text payload_hash
        text status
        int retry_count
    }

    PIPELINE_WATERMARKS {
        bigserial id PK
        text source
        text scope_key
        text watermark_type
        text watermark_value
        text status
        text run_id
    }

    PIPELINE_RUNS {
        text run_id PK
        text source
        timestamptz started_at
        text status
    }

    INGESTION_RUNS {
        bigserial id PK
        text source
        text status
    }

    ENTITY_ALIASES {
        bigserial id PK
        text entity_id
        text alias_normalized
    }
```

## Notas de cardinalidade e integridade

| Tema | Detalhe |
|------|---------|
| Universo | 1093 ativos `raio_200km` — denominador M1/M2 |
| ESR | UNIQUE `canonical_id`; UNIQUE (cnpj, natureza, razao_social) |
| Official acts | UNIQUE parcial (source, resource_id) / (source, content_sha256) |
| Evidence satisfactory | CHECK composto mig 054 |
| DLQ pending | UNIQUE parcial (source, payload_hash, error_code) |
| Watermarks | UNIQUE (source, scope_key, type, value) |
| Soft FKs | `run_id` frequentemente TEXT soft-ref (não FK rígida) |

## Tabelas legadas adicionais (não expandido no diagrama)

`capability_coverage`, `target_universe_snapshot`, `value_observations`, `supplier_identity`, reporting views 036, schema contract views 030 — ver migrations 030–040.
