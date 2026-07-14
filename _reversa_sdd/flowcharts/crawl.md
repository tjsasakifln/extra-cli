# Fluxograma — Módulo Crawl

> Gerado pelo Archaeologist em 2026-07-13

## Orquestrador Central (`monitor.py`)

```mermaid
flowchart TD
    A[main] --> B[parse_args]
    B --> C{mode}
    C -->|full| D[crawl_source ALL sources]
    C -->|incremental| E[crawl_source incremental]
    C -->|report-coverage| F[report_coverage]

    D --> G[Para cada source]
    E --> G

    G --> H[_load_crawler]
    H --> I{Crawler carregado?}
    I -->|No| J[SKIP + log error]
    I -->|Yes| K[_load_entities within_200km]

    K --> L[_start_ingestion_run]
    L --> M[_match_entities_cascade]

    M --> N[Para cada entidade]
    N --> O{crawl_source}
    O --> P[Fetch da API/Scraping]
    P --> Q[Transform + Validate]
    Q --> R[_upsert_raw_records]
    R --> S[_project_entity_evidence]
    S --> T[_record_evidence]

    T --> U{Próxima entidade?}
    U -->|Yes| N
    U -->|No| V[_finish_ingestion_run]
    V --> W[Fim]

    F --> X[Query entity_coverage]
    X --> Y[print_coverage_report]
```

## Pipeline de Crawl por Fonte

```mermaid
flowchart LR
    A[CrawlRequest] --> B{Protocolo}
    B -->|REST| C[sync_client / async_client]
    B -->|Selenium| D[selenium_crawler]
    B -->|CKAN| E[ciga_ckan_crawler]

    C --> F{Retry?}
    F -->|Sim| G[Exponential Backoff + Jitter]
    G --> C
    F -->|Não| H[Circuit Breaker]

    H --> I{Estado}
    I -->|CLOSED| J[Executa]
    I -->|OPEN| K[Skip + CircuitBreakerOpenError]
    I -->|HALF_OPEN| L[Testa 1 request]

    J --> M[FetchResult]
    L --> M
```

## Entity Matching Cascade

```mermaid
flowchart TD
    A[CNPJ do órgão] --> B[Nível 1: CNPJ8 Exact]
    B --> C{Match?}
    C -->|Sim| D[✅ Entity Matched - HIGH]
    C -->|Não| E[Nível 2: Name + Município]

    E --> F[Normalize name]
    F --> G[Match com sc_public_entities]
    G --> H{Match?}
    H -->|Sim| I[✅ Entity Matched - HIGH]
    H -->|Não| J[Nível 2b: Alias Matching]

    J --> K[Expand abbreviations]
    K --> L[Siglas e padrões]
    L --> M{Match?}
    M -->|Sim| N[✅ Entity Matched - HIGH]
    M -->|Não| O[Nível 3: Fuzzy]

    O --> P[rapidfuzz / difflib]
    P --> Q{Score}
    Q -->|>0.90| R[✅ Matched - HIGH]
    Q -->|0.85-0.90| S[⚠️ Matched - MEDIUM]
    Q -->|0.75-0.85| T[⚠️ Matched - LOW]
    Q -->|<0.75| U[❌ No Match]
```

## Ingestion Pipeline

```mermaid
flowchart TD
    A[Records brutos] --> B[Dedup por content_hash]
    B --> C[Validate schema]
    C --> D{Validation}
    D -->|OK| E[Transform to canonical]
    D -->|FAIL| F[Log + Skip]
    E --> G[Enrich: IBGE geocode]
    G --> H[Enrich: Entity match]
    H --> I[Upsert no PostgreSQL]
    I --> J[Update checkpoint]
    J --> K[Project evidence]
    K --> L[Finish]
```

## Circuit Breaker

```mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: N falhas consecutivas
    OPEN --> HALF_OPEN: Timeout expirado
    HALF_OPEN --> CLOSED: Request OK
    HALF_OPEN --> OPEN: Request falhou
```
