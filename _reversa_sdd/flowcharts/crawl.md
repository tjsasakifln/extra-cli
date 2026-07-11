# Fluxograma — Módulo `crawl`

> Gerado pelo Archaeologist em 2026-07-11T13:00:00Z

---

## Pipeline Multi-Source (monitor.py)

```mermaid
flowchart TD
    A[main] --> B{parse_args}
    B -->|--report-coverage| C[report_coverage]
    B -->|--source X --mode Y| D[Load entities from DB]
    D --> E[For each source]
    E --> F[_load_crawler source]
    F --> G{Crawler found?}
    G -->|No| H[Skip + log error]
    G -->|Yes| I[crawl mode]
    I --> J{Records fetched?}
    J -->|0| K[Finish run: completed]
    J -->|N > 0| L[transform records]
    L --> M[Add source tag]
    M --> N[upsert_pncp_raw_bids RPC]
    N --> O{Success?}
    O -->|No| P[Rollback + fail run]
    O -->|Yes| Q[_match_entities_cascade]
    Q --> R[_finish_ingestion_run]
    R --> S[Next source]
    S --> E
    C --> T[Print coverage report]
```

## Entity Matching Cascade

```mermaid
flowchart TD
    A[_match_entities_cascade] --> B[Fetch unmatched bids for source]
    B --> C{Bids found?}
    C -->|No| D[Return zero stats]
    C -->|Yes| E[Build CNPJ index]
    E --> F[Build name indexes]
    F --> G[For each bid]
    
    G --> H{CNPJ match?}
    H -->|Level 1: exact 8-digit| I[match_method=cnpj, score=1.0, confidence=high]
    H -->|No| J{Normalized name + IBGE?}
    J -->|Level 2a: exact| K[match_method=name_normalized, score=1.0, confidence=high]
    J -->|No| L{Normalized name only?}
    L -->|Level 2b: exact| M[match_method=name_normalized, score=1.0, confidence=high]
    L -->|No| N[Filter candidates by IBGE]
    N --> O[Compute fuzzy ratio for each]
    O --> P{Best score >= threshold?}
    P -->|Level 3: >= 0.85| Q[confidence = high/medium/low]
    P -->|No| R[match_method=unmatched]
    
    I --> S[Update bid row]
    K --> S
    M --> S
    Q --> S
    R --> S
    S --> T{More bids?}
    T -->|Yes| G
    T -->|No| U[COMMIT batch]
    U --> V[Return stats]
```

## Ciclo de Ingestion (systemd → monitor.py)

```mermaid
flowchart LR
    A[systemd timer] --> B[monitor.py]
    B --> C[_load_entities]
    C --> D[crawl_source]
    D --> E[crawl API]
    E --> F[transform]
    F --> G[upsert RPC]
    G --> H[match entities]
    H --> I[update coverage]
    I --> J[ingestion_runs log]
    J --> K[report_coverage]
    K --> L[print summary]
```
