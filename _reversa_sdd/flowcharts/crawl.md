# Flowcharts — módulo `crawl`

> 🟢 CONFIRMADO — 2026-07-17

## 1. Monitor multi-source

```mermaid
flowchart TD
    A[CLI monitor.py] --> B{source / mode}
    B -->|all| C[iter_sources registry]
    B -->|one| D[lookup source]
    C --> E[Para cada SourceInfo]
    D --> E
    E --> F[Import module crawler]
    F --> G[crawl mode full/incremental]
    G --> H[transform records]
    H --> I[entity match]
    I --> J[upsert DB]
    J --> K[coverage update]
    K --> L{mais sources?}
    L -->|sim| E
    L -->|não| M[report / exit]
    G -->|erro| N[log + DLQ/evidence]
    N --> L
```

## 2. Registry resolve

```mermaid
flowchart LR
    A[alias ou name] --> B[resolve_name]
    B --> C[lookup SourceInfo]
    C --> D[module / purpose / SLA / capabilities]
```

## 3. Resilience adapter cycle (pré-VPS)

```mermaid
flowchart TD
    A[run_cycle live|fixture] --> B[ResilienceConfig.from_env]
    B --> C[mkdir checkpoint raw dlq evidence]
    C --> D[Adapters PNCP CIGA SC]
    D --> E{budget OK?}
    E -->|não| F[stop partial]
    E -->|sim| G[load checkpoint]
    G --> H[fetch page/scope]
    H --> I[persist RawStore]
    I --> J[save CanonicalCheckpoint]
    J --> K{status}
    K -->|success_with_data / success_zero| L[EvidenceLedger write]
    K -->|partial / error / rate_limited| M[FileDLQ push]
    L --> N{more pages?}
    M --> N
    N -->|sim| E
    N -->|não| O[aggregate report]
```

## 4. Fail-closed SC bulk

```mermaid
flowchart TD
    A[SC Compras fetch year] --> B{total_elementos conhecido?}
    B -->|sim| C{len items == expected?}
    B -->|não| D[status partial/error]
    C -->|sim| E[success_with_data]
    C -->|não| D
    D --> F[NÃO promover coverage satisfactory]
    E --> G[evidence + provenance]
```
