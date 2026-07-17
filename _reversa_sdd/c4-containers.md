# C4 — Containers (Nível 2)

> Architect 2026-07-17 🟢

```mermaid
C4Container
    title Extra Consultoria — Containers

    Person(consultor, "Consultor")

    Container_Boundary(host, "Host local / VPS") {
        Container(workspace, "Workspace CLI", "Python", "Facade operacional diária ADR-017")
        Container(crawl, "Crawl Runtime", "Python + systemd", "monitor, adapters, 11 sources")
        Container(intel, "Intel CLIs", "Python", "opportunity/contract/buyer/source_registry/coverage")
        Container(reports, "Reports", "Python+ReportLab+openpyxl", "PDF/Excel/amostras")
        Container(gates, "Gates", "Python/Shell", "readiness, freshness, coverage, ci_gate")
        Container(fs, "FS Operational Zone", "output/ data/", "raw, checkpoints, DLQ file, session JSONL")
        ContainerDb(pg, "PostgreSQL", "pgvector:pg16", "DataLake + ESR + acts + evidence")
    }

    Container_Ext(sources, "Fontes gov", "HTTPS", "PNCP, SC, DOE/DOM, CKAN, ...")
    Container_Ext(ci, "GitHub Actions", "CI", "fail-closed pipeline")

    Rel(consultor, workspace, "comandos today/coverage/decide")
    Rel(workspace, intel, "delega")
    Rel(workspace, reports, "briefing/report")
    Rel(workspace, pg, "SQL se disponível")
    Rel(workspace, fs, "fallback sessão")
    Rel(crawl, sources, "fetch")
    Rel(crawl, fs, "raw/checkpoint/evidence")
    Rel(crawl, pg, "upsert bids/contracts/acts")
    Rel(intel, pg, "queries + metrics")
    Rel(intel, fs, "artefatos multi-source")
    Rel(reports, pg, "dados executivos")
    Rel(gates, pg, "coverage/freshness checks")
    Rel(ci, gates, "invoca testes/lint")
    Rel(crawl, intel, "alimenta registry/coverage")
```

## Runtime notes
- **Pré-VPS:** filesystem é SoT de resilience; PG recebe projeções.  
- **Produção VPS:** systemd timers disparam crawl/report/health.  
