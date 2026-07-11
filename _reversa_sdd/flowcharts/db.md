# Fluxograma — Módulo `db`

> Gerado pelo Archaeologist em 2026-07-11T13:00:00Z

---

## Migration Sequence

```mermaid
flowchart TD
    M001[001: pncp_raw_bids + índices + trigger] --> M002[002: pncp_supplier_contracts]
    M002 --> M003[003: enriched_entities]
    M003 --> M004[004: ingestion_runs + ingestion_checkpoints]
    M004 --> M005[005: search_datalake RPC]
    M005 --> M006[006: upsert_pncp_raw_bids RPC]
    M006 --> M007[007: sc_public_entities + FK]
    M007 --> M008[008: purge RPC]
    M008 --> M009[009: entity_coverage + indexes]
    M009 --> M010[010: match_logging]
    M010 --> M011[011: v_unmatched_bids view]
    M011 --> M012[012: coverage_snapshots]
```

## Data Flow: Crawl → Upsert → Match → Coverage

```mermaid
flowchart TD
    A[Crawler: raw records] --> B[transformer.py]
    B --> C[Normalized records with content_hash]
    C --> D[upsert_pncp_raw_bids RPC]
    D --> E{INSERT or UPDATE?}
    E -->|INSERT| F[New row in pncp_raw_bids]
    E -->|UPDATE| G[Update existing row]
    F --> H[_match_entities_cascade]
    G --> H
    H --> I[UPDATE matched_entity_id]
    I --> J[DB trigger: refresh entity_coverage]
    J --> K[coverage_snapshots daily job]
```

## Setup Flow

```mermaid
flowchart LR
    A[setup_db.sh] --> B[Create database pncp_datalake]
    B --> C[Apply 12 migrations in order]
    C --> D[python db/seed/001_sc_entities.py]
    D --> E[Parse Excel: Extra - alvos de licitação.xlsx]
    E --> F[INSERT 2.085 sc_public_entities]
    F --> G[Verify: SELECT count(*)]
```
