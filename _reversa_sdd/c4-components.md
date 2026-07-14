# C4 Componentes (Nível 3) — Extra Consultoria

> Gerado pelo Architect em 2026-07-13T17:30:00Z
> doc_level: completo
> Base: commit 249340d
> Delta: +Opportunity Intel components, +Contract Intel components, +Gates components

---

## Componentes do Opportunity Intel System

```mermaid
C4Component
    title Componentes — Opportunity Intel (QW-01 Radar)

    Container_Boundary(oi, "Opportunity Intel System") {
        Component(cli, "CLI", "Python/argparse", "Entry point: radar, list, show, explain, coverage, source-health, update, export")
        Component(radar, "QW-01 Radar", "Python", "Orquestrador: schema check→universe load→crawl→dedup→status→ranking→scoring→CSV")
        Component(crawler_base, "Crawler Base", "Python", "Base class com retry/backoff/rate limit/checkpoint. Interface comum para fontes.")
        Component(transformer, "Transformer", "Python", "Normalização de records: padroniza campos, infere UF, formata datas")
        Component(dedup, "Deduplicator", "Python", "4 níveis: content_hash→pncp_id→objeto+orgao→fuzzy. Cross-source aware.")
        Component(status_engine, "Status Engine", "Python", "Status canônico 3 níveis: source_map→temporal→heuristic. Janelas 90/365 dias.")
        Component(ranking_engine, "Ranking Engine", "Python", "24 regras: 6 HARD_BLOCKS + 9 POSITIVE + 9 NEGATIVE. Score 0-100.")
        Component(scoring, "Scoring Engine", "Python", "Dual scoring: data_confidence (0-100) + client_fit (0-100). Triage GO/REVIEW/NO_GO.")
        Component(models, "Domain Models", "Python", "Dataclasses: OpportunityRecord, CrawlRequest, FetchResult, RadarScores, RadarExecution")
        Component(pncp_audit, "PNCP Audit", "Python", "Monitoramento auditável PNCP: run→fetch→audit→outcome. Threshold 95%.")
        Component(manifest, "Manifest Generator", "Python", "Coverage manifest: entidades cobertas, gaps, blockers, métricas")
        Component(profile, "Client Profile", "Python", "Carrega YAML de perfil: CNAEs, keywords, municípios, limites financeiros")
    }

    ContainerDb(postgres, "PostgreSQL", "opportunity_intel table + views")

    Rel(cli, radar, "dispara", "cmd_radar()")
    Rel(radar, crawler_base, "usa", "crawl sources")
    Rel(radar, transformer, "usa", "normalize records")
    Rel(radar, dedup, "usa", "cross-source dedup")
    Rel(radar, status_engine, "usa", "canonical status")
    Rel(radar, ranking_engine, "usa", "compute ranking")
    Rel(radar, scoring, "usa", "dual scoring")
    Rel(radar, manifest, "usa", "coverage manifest")
    Rel(radar, profile, "lê", "client profile YAML")
    Rel(radar, pncp_audit, "usa", "PNCP monitoring")
    Rel(radar, postgres, "psycopg2", "INSERT/UPDATE opportunity_intel")
    Rel(cli, postgres, "psycopg2", "SELECT list/show/explain")
```

## Componentes do Contract Intel System

```mermaid
C4Component
    title Componentes — Contract Intel (Competitive Intelligence)

    Container_Boundary(ci, "Contract Intel System") {
        Component(ci_cli, "CLI", "Python/argparse", "Entry point: historical, suppliers, readiness, competitive")
        Component(target_universe, "Target Universe", "Python", "Load canonical universe→resolve entities→compute metrics. Denominador conservador.")
        Component(historical, "Historical Query", "Python", "Consulta contratos históricos: filtro por entidade, período, valor")
        Component(supplier_ranking, "Supplier Ranking", "Python", "TOP 20: contratos→valor total→entidades servidas. ORDER BY total_value DESC.")
        Component(market_share, "Market Share", "Python", "share = valor_fornecedor / valor_total_entidade. Agrupado por órgão.")
        Component(hhi, "HHI Calculator", "Python", "Σ(share²). Global + por entidade. Classificação: BAIXA/MEDIA/ALTA/MUITO_ALTA.")
        Component(expiring, "Expiring Contracts", "Python", "Contratos com data_fim_vigência nos próximos N dias. Oportunidade de renovação.")
        Component(readiness_check, "Readiness Check", "Python", "Threshold 95% — exit code 2 abaixo. Denominador conservador.")
    }

    ContainerDb(postgres, "PostgreSQL", "pncp_supplier_contracts + sc_public_entities")

    Rel(ci_cli, target_universe, "usa", "load + resolve")
    Rel(ci_cli, historical, "usa", "cmd_historical()")
    Rel(ci_cli, supplier_ranking, "usa", "cmd_suppliers()")
    Rel(ci_cli, readiness_check, "usa", "cmd_readiness()")
    Rel(supplier_ranking, market_share, "usa", "_compute_market_share()")
    Rel(supplier_ranking, hhi, "usa", "_compute_hhi()")
    Rel(ci_cli, postgres, "psycopg2", "SELECT contratos + métricas")
```

## Componentes dos CI Gates

```mermaid
C4Component
    title Componentes — CI Gates (Fail-Closed)

    Container_Boundary(gates, "CI Gates System") {
        Component(readiness_gate, "Readiness Gate", "Python", "consulting_readiness.py — coverage ≥ 95%? SOURCE_BLOCKERS override. Exit 0/2.")
        Component(freshness_gate, "Freshness Gate", "Python", "freshness_gate.py — SLA PNCP 24h, Contracts 24d. Exit 0/2.")
        Component(coverage_calc, "Coverage Calculator", "Python", "covered/conservative_population. Evidência do coverage_evidence ledger.")
        Component(blocker_registry, "SOURCE_BLOCKERS", "Python/dict", "7 fontes bloqueadas com justificativa. Override hardcoded do DB.")
        Component(freshness_check, "Freshness Checker", "Python", "MAX(last_run_at) ≥ NOW() - SLA_hours por critical source.")
    }

    ContainerDb(postgres, "PostgreSQL", "coverage_evidence + ingestion_runs")

    Rel(readiness_gate, coverage_calc, "usa", "compute coverage%")
    Rel(readiness_gate, blocker_registry, "lê", "SOURCE_BLOCKERS dict")
    Rel(readiness_gate, postgres, "psycopg2", "SELECT coverage_evidence")
    Rel(freshness_gate, freshness_check, "usa", "check SLA per source")
    Rel(freshness_gate, postgres, "psycopg2", "SELECT ingestion_runs")
```

## Componentes do Evidence Ledger

```mermaid
C4Component
    title Componentes — Coverage Evidence Ledger

    Container_Boundary(evidence, "Evidence Ledger System") {
        Component(projection, "Evidence Projection", "Python/monitor.py", "_project_entity_evidence(): projeta estado por (entity, source, data_type, run_id)")
        Component(state_mapper, "State Mapper", "Python/monitor.py", "_map_evidence_state(): monitor_status+error_code→evidence_state enum")
        Component(upsert, "Evidence Upsert", "Python/monitor.py", "DELETE+INSERT idempotente por run_id. Nunca UPDATE.")
        Component(schema_check, "Schema Validator", "Python/monitor.py", "Verifica existência da tabela coverage_evidence antes de escrever")
    }

    ContainerDb(postgres, "PostgreSQL", "coverage_evidence table + evidence_state enum")

    Rel(projection, state_mapper, "usa", "map status→enum")
    Rel(projection, upsert, "usa", "idempotent write")
    Rel(projection, schema_check, "usa", "table exists?")
    Rel(projection, postgres, "psycopg2", "DELETE+INSERT coverage_evidence")
```

## Tabela de Componentes por Container

| Container | Componentes | Complexidade |
|-----------|-----------|-------------|
| Opportunity Intel | CLI, Radar, CrawlerBase, Transformer, Dedup(4 níveis), Status(3 níveis), Ranking(24 regras), Scoring(dual), Models, PncpAudit, Manifest, Profile | 🔴 VERY_HIGH |
| Contract Intel | CLI, TargetUniverse, Historical, SupplierRanking, MarketShare, HHI, Expiring, ReadinessCheck | 🟠 HIGH |
| CI Gates | ReadinessGate, FreshnessGate, CoverageCalc, BlockerRegistry, FreshnessCheck | 🟡 MEDIUM |
| Evidence Ledger | Projection, StateMapper, Upsert, SchemaCheck | 🟡 MEDIUM |
| Crawl System | Monitor, Orchestrator v2, 10 Crawlers, 4 Templates, Common, Checkpoint, Security, Enricher, Transformer | 🔴 VERY_HIGH |
| Intel Pipeline | 7 estágios, 5 quality gates, 12 algoritmos | 🟠 HIGH |
