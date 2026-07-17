# Spec Impact Matrix — Extra Consultoria

> Architect 2026-07-17 | 25 módulos × regras/ADRs

## 1. Módulo × ADRs críticos

| Módulo | 012 | 013 | 014 | 015 | 016 | 017 | 018 | 019 | 020 | 021 | 022 |
|--------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| crawl | | ● | | | | | | | ● | ● | |
| resilience/ops | | ● | ● | | | | | | ● | ● | |
| source_registry | | | | | | | ● | ● | | ● | |
| coverage | | ● | ● | | | ● | ● | ● | | ● | |
| matching | | | | | | | | | | | |
| schema | | ● | | | | | | | ● | | |
| opportunity_intel | ● | | | ● | ● | ● | | | | | ● |
| contract_intel | | | | ● | ● | ● | | | | | |
| buyer_intel | | | | | ● | ● | | | | | ● |
| workspace | | | | | | ● | ● | | ● | | ● |
| lib | ● | | | ● | | | ● | | | | ● |
| reports | | | | | | ● | ● | | ● | | |
| root_scripts/gates | | ● | ● | | | | ● | | | | |
| db | | ● | | | | | | ● | | ● | |
| deploy | | | ● | | | | | | ● | ● | |
| tests | ● | ● | ● | | | ● | ● | ● | | ● | |

## 2. Módulo × Regras de negócio (R27+)

| Regra | Módulos impactados |
|-------|-------------------|
| R27 dual-metric | coverage, workspace, reports, gates |
| R28 den 1093 | lib, coverage, readiness |
| R29 M2 evidência | coverage, crawl, ESR, db |
| R30 ESR SoT | source_registry, coverage |
| R31 fail-closed 429/bulk | crawl/resilience, ops |
| R32 empty_confirmed | crawl registry, coverage states |
| R33 raw fora git | crawl, ops, deploy, docs |
| R34 workspace facade | workspace, *product modules |
| R35 client profile law | opportunity_intel, workspace, config |
| R36 default REVIEW | workspace/actions |
| R37 acts deterministic | matching, schema |
| R38 value semantics | lib, reports, contract_intel |
| R39 list identity | coverage tests |
| R40 buyer AEC | buyer_intel |

## 3. Mudança típica → blast radius

| Se alterar… | Impacta specs/módulos |
|-------------|----------------------|
| `crawl/registry.py` SourceInfo | crawl, pipeline, credential validation, docs, coverage applicability |
| Coverage contract formulas | workspace, gates, reports, DoD sessions, PRD comercial |
| ESR schema/status enum | source_registry, coverage M2, gap reports |
| Adapter FetchResult semantics | resilience, chaos tests, mig 054, ADR-021 |
| Client profile YAML | scoring, workspace filters, triage |
| official_acts DDL | schema store, reconcile, reports multi-source |
| Universe seed 1093 | **tudo** que usa denominador — mudança HIGH-RISK |

## 4. Dívidas × módulo owner

| Dívida | Owner módulo |
|--------|--------------|
| M2=0/1093 | source_registry + crawl + coverage |
| ADR-022 aderência legada | opportunity_intel + intel_pipeline |
| clients/ingestion dup | crawl refactor |
| lockfile pip | devops/root |

## 5. Rastreio Reversa

| Artefato SDD | Gera impacto em |
|--------------|-----------------|
| domain.md R27–R40 | QA regression-watch, stories AIOX |
| code-analysis A01–A15 | Writer tasks por módulo |
| erd-complete | data-engineer migrations futuras |
| c4-* | architect reviews |
