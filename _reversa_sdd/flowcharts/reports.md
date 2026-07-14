# Fluxograma — Módulo Reports

> Gerado pelo Archaeologist em 2026-07-13

## Relatório Semanal de Cobertura

```mermaid
flowchart TD
    A[coverage_weekly.py] --> B[Conectar PostgreSQL]
    B --> C[Query: entity_coverage + evidence]

    C --> D[Para cada fonte]
    D --> E[Calcular % cobertura]
    E --> F[Agrupar por município]
    F --> G[Agrupar por natureza jurídica]

    G --> H[Gerar PDF: reportlab]
    G --> I[Gerar Excel: openpyxl]

    H --> J[Gráficos: barras, pizza, linha temporal]
    I --> K[Abas: resumo, por fonte, por município, gaps]

    J --> L[output/reports/coverage-semanal-{date}.pdf]
    K --> M[output/reports/coverage-semanal-{date}.xlsx]
```

## Panorama Setorial

```mermaid
flowchart LR
    A[panorama.py] --> B[Query sectors_config.yaml]
    B --> C[13 setores B2G]

    C --> D[Para cada setor]
    D --> E[Filtrar licitações por keywords]
    E --> F[Agrupar: modalidade, valor, região]
    F --> G[Calcular market share]

    G --> H[PDF/Excel executivo]
    H --> I[output/reports/panorama-{date}.pdf]
```

## Pipeline de Geração PDF (Big Four)

```mermaid
flowchart TD
    A[Dados de entrada] --> B{Template}

    B -->|Consultoria| C[generate_consultoria_pdf.py]
    B -->|Proposta| D[generate_proposta_pdf.py]
    B -->|B2G| E[generate_report_b2g.py]
    B -->|Coleta| F[collect_report_data.py]

    C --> G[reportlab Canvas]
    D --> G
    E --> G
    F --> G

    G --> H[Header + Logo]
    H --> I[Sumário Executivo]
    I --> J[Tabelas de dados]
    J --> K[Gráficos e visualizações]
    K --> L[Recomendações]
    L --> M[Footer + metadata]

    M --> N[PDF final]
    N --> O[output/pdfs/]
```

## Freshness Gate

```mermaid
flowchart TD
    A[freshness_gate.py] --> B[Conectar PostgreSQL]
    B --> C[CRITICAL_SOURCES config]

    C --> D[pncp: SLA 24h]
    C --> E[contracts: SLA 24d]

    D --> F[Query: MAX data_publicacao FROM pncp_raw_bids]
    E --> G[Query: MAX data_publicacao FROM pncp_supplier_contracts]

    F --> H{Último registro}
    H -->|< SLA| I[✅ FRESH]
    H -->|> SLA| J[❌ STALE]
    H -->|NULL| K[🔴 NEVER]

    G --> L{Último registro}
    L -->|< SLA| M[✅ FRESH]
    L -->|> SLA| N[❌ STALE]
    L -->|NULL| O[🔴 NEVER]

    I --> P{All fresh?}
    J --> P
    K --> P
    M --> P
    N --> P
    O --> P

    P -->|Yes| Q[Exit 0 — ✅]
    P -->|No| R[Exit 2 — ❌]

    Q --> S[output/readiness/freshness-gate.json]
    R --> S
    S --> T[output/readiness/freshness-gate.csv]
```
