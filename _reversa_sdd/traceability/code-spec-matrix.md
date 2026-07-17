# Code ↔ Spec Matrix

> Writer/Reviewer re-extração 2026-07-17 | HEAD `d3e82ba`  
> Cobertura: **25 módulos** mapeados · specs em `_reversa_sdd/<modulo>/` quando geradas

## Legenda
| Status | Significado |
|--------|-------------|
| ✅ | Spec unit presente e alinhada ao código |
| 🔄 | Spec legado 2026-07-13; delta coberto em domain/code-analysis |
| 🆕 | Spec nova nesta re-extração |

## Matriz

| Módulo | Código path | requirements | design | tasks | Status |
|--------|-------------|:------------:|:------:|:-----:|:------:|
| crawl | scripts/crawl | ✅ | 🔄 | 🔄 | 🆕 RFs delta |
| source_registry | scripts/source_registry | ✅ | ✅ | ✅ | 🆕 |
| workspace | scripts/workspace | ✅ | ✅ | ✅ | 🆕 |
| coverage | scripts/coverage | ✅ | ✅ | ✅ | 🆕 refresh |
| opportunity_intel | scripts/opportunity_intel | 🔄 | 🔄 | 🔄 | 🔄 + domain R |
| contract_intel | scripts/contract_intel | 🔄 | 🔄 | 🔄 | 🔄 |
| buyer_intel | scripts/buyer_intel | ✅ | ✅ | ✅ | 🆕 |
| extra_ledger | scripts/extra_ledger | ✅ | ✅ | ✅ | 🆕 |
| matching | scripts/matching | 🔄 | 🔄 | 🔄 | 🔄 + flowchart |
| lib | scripts/lib | 🔄 | 🔄 | 🔄 | 🔄 |
| schema | scripts/schema | ✅ | ✅ | ✅ | 🆕 |
| ops | scripts/ops | ✅ | ✅ | ✅ | 🆕 |
| reports | scripts/reports | 🔄 | 🔄 | 🔄 | 🔄 |
| fix | scripts/fix | 🔄 | 🔄 | 🔄 | 🔄 |
| pipeline | scripts/pipeline | 🔄 | 🔄 | 🔄 | 🔄 |
| clients | scripts/clients | ✅ | ✅ | ✅ | 🆕 |
| ingestion | scripts/ingestion | ✅ | ✅ | ✅ | 🆕 |
| diagnose | scripts/diagnose | 🔄 | 🔄 | 🔄 | 🔄 |
| transparencia | scripts/transparencia | 🔄 | 🔄 | 🔄 | 🔄 |
| config | config/ | 🔄 | 🔄 | 🔄 | 🔄 |
| db | db/ | 🔄 | 🔄 | 🔄 | 🔄 + ERD |
| deploy | deploy/ | 🔄 | 🔄 | 🔄 | 🔄 |
| root_scripts | scripts/*.py | 🔄 | 🔄 | 🔄 | 🔄 |
| tests | tests/ | 🔄 | 🔄 | 🔄 | 🔄 |
| docs | docs/ | 🔄 | 🔄 | 🔄 | 🔄 |

## Rastreio regra → código (delta)

| Regra | Spec / ADR | Código |
|-------|------------|--------|
| R27–R29 | ADR-018, coverage/requirements | coverage_contract.py |
| R30 | ADR-019, source_registry/* | source_registry/* |
| R31–R32 | ADR-021, crawl requirements | resilience/adapters.py |
| R33 | ADR-020 | .gitignore / ops paths |
| R34–R36 | ADR-017, workspace/* | workspace/* |
| R35 | ADR-022 | client_profiles + profile.py |
| R37 | matching flowchart | official_acts_reconcile.py |
| R38 | ADR-015 | value_semantics.py |
| R40 | buyer_intel | ranking.py |

## Entradas totais
- Units com triple SDD novo/refresh: **10**  
- Units com SDD prévio mantido + cobertura transversal: **15**  
- Artefatos transversais: inventory, dependencies, code-analysis, data-dictionary, domain, state-machines, permissions, architecture, C4×3, ERD, ADRs 017–022, flowcharts×9, impact matrix  
