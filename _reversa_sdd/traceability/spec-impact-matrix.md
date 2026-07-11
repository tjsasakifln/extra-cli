# Spec Impact Matrix — Extra Consultoria

> Gerado pelo Architect em 2026-07-11T22:00:00Z
> doc_level: completo
> Cross-reference: módulos ↔ specs SDD ↔ ADRs ↔ épicos

## Matriz de Impacto: Módulos × Artefatos

| Módulo | code-analysis | data-dictionary | flowcharts | domain | ADRs | C4 | ERD |
|--------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| crawl | ✅ | ✅ | ✅ | R1,R8,R12,R13 | 001,002,003,008,011 | C1,C2,C3 | pncp_raw_bids |
| intel | ✅ | ✅ | ✅ | R4,R5,R6,R7,R14,R15,R16 | 005,006 | C1,C2,C3 | — |
| reports | ✅ | — | ✅ | R2 | 006 | C1,C2 | views |
| matching | ✅ | — | ✅ | R8,R13 | 004,008 | C2 | pncp_raw_bids |
| lib | ✅ | ✅ | ✅ | R14,R15 | 004,005 | C2 | — |
| config | ✅ | — | — | R7,R14 | 005 | C2 | — |
| db | ✅ | ✅ | ✅ | R2,R9,R10 | 001,007 | C2 | ALL |
| deploy | ✅ | — | — | R12 | 002,009 | C1,C2 | — |
| docs | ✅ | — | — | — | 007 | — | — |

## Matriz de Impacto: Regras de Negócio × Módulos

| Regra | crawl | intel | reports | matching | db | deploy |
|-------|:---:|:---:|:---:|:---:|:---:|:---:|
| R1: Filtro engenharia | ✅ | — | — | — | — | — |
| R2: Janela cobertura 90d | ✅ | — | ✅ | — | ✅ | — |
| R3: Raio 200km | — | ✅ | — | — | ✅ | — |
| R4: Capacidade 10× | — | ✅ | — | — | — | — |
| R5: Threshold participação 0.45 | — | ✅ | — | — | — | — |
| R6: Override recomendação (6) | — | ✅ | — | — | — | — |
| R7: Hard incompatible (4) | — | ✅ | — | — | ✅ | — |
| R8: Dedup cross-source | ✅ | ✅ | — | ✅ | ✅ | — |
| R9: Retenção 400d + 90d | — | — | — | — | ✅ | — |
| R10: Cache TTL 90d | ✅ | ✅ | — | — | ✅ | — |
| R11: Max 3 docs/edital | — | ✅ | — | — | — | — |
| R12: Frequência crawl | ✅ | — | — | — | — | ✅ |
| R13: Schema unificado | ✅ | — | — | ✅ | ✅ | — |
| R14: CNAE gate probabilístico | — | ✅ | — | — | ✅ | — |
| R15: HHI competição | — | ✅ | — | — | — | — |
| R16: Zero false negative | — | ✅ | — | — | — | — |
| R17: Single tenant | ✅ | ✅ | ✅ | — | ✅ | ✅ |

## Matriz de Impacto: ADRs × Módulos

| ADR | crawl | intel | reports | matching | lib | db | deploy |
|-----|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 001: PostgreSQL direto | ✅ | ✅ | ✅ | ✅ | — | ✅ | — |
| 002: Systemd timers | ✅ | — | ✅ | — | — | — | ✅ |
| 003: Crawlers sync HTTP | ✅ | — | — | — | — | — | — |
| 004: Matching cascade 3 níveis | ✅ | — | — | ✅ | ✅ | ✅ | — |
| 005: GPT-4.1-nano | — | ✅ | — | — | ✅ | — | — |
| 006: PDF ReportLab Big Four | — | ✅ | ✅ | — | — | — | — |
| 007: Migrations v2 baseline | — | — | — | — | — | ✅ | — |
| 008: Refactor orquestrador | ✅ | — | — | ✅ | — | — | — |
| 009: Backup PostgreSQL | — | — | — | — | — | ✅ | ✅ |
| 010: Logging JSON | ✅ | ✅ | ✅ | ✅ | — | — | — |
| 011: Template transparência | ✅ | — | — | — | — | — | — |

## Matriz de Impacto: Épicos × Módulos

| Épico | crawl | intel | reports | matching | lib | db | deploy | docs |
|-------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| EPIC-001 (7 stories) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| EPIC-FEAT-001 (10 stories) | ✅ | ✅ | — | — | — | — | ✅ | ✅ |
| EPIC-TD-001 (22 stories) | ✅ | ✅ | — | ✅ | ✅ | ✅ | ✅ | ✅ |

## Hotspots (Alta Densidade de Dependências)

| Módulo | Regras | ADRs | Épicos | Total Links |
|--------|--------|------|--------|-------------|
| **intel** | 10 | 3 | 3 | 🔥 16 |
| **crawl** | 5 | 5 | 3 | 🔥 13 |
| **db** | 6 | 4 | 3 | 🔥 13 |
| reports | 2 | 2 | 2 | 6 |
| matching | 2 | 3 | 2 | 7 |
| deploy | 2 | 2 | 3 | 7 |
| lib | 2 | 2 | 2 | 6 |
| config | 2 | 1 | 2 | 5 |
| docs | 0 | 1 | 3 | 4 |

**Módulos mais críticos:** `intel` (pipeline analítico — maior concentração de regras de negócio), `crawl` (ingestão — maior número de ADRs), `db` (persistência — interseção de todas as camadas).

## Confiança da Matriz

🟢 **CONFIRMADO** — Todos os cross-references foram verificados contra artefatos atualizados (code-analysis.md, domain.md, ADRs, ERD). Nenhum link inferido.
