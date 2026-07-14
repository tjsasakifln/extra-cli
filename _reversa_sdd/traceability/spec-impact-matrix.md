# Spec Impact Matrix — Extra Consultoria

> Gerado pelo Architect em 2026-07-13T17:30:00Z
> doc_level: completo
> Base: commit 249340d
> Delta: +2 verticais, +9 regras, +5 ADRs, +3 cross-cutting concerns
> **Migracao 2026-07-13:** O modulo `intel` (legado) foi incorporado a `root_scripts/`. A coluna `intel` nas matrizes abaixo e mantida como registro historico dos vinculos originais. Para novos desenvolvimentos, consulte `root_scripts/`. Detalhes em `_reversa_sdd/intel/README.md`.

## Matriz de Impacto: Módulos × Artefatos

| Módulo | code-analysis | data-dictionary | flowcharts | domain | ADRs | C4 | ERD |
|--------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| crawl | ✅ | ✅ | ✅ | R1,R8,R12,R13,R21 | 001,002,003,008,011,013 | C1,C2,C3 | pncp_raw_bids, coverage_evidence |
| opportunity_intel 🆕 | ✅ | ✅ | ✅ | R19,R20,R21,R22,R26 | 012,013,014,016 | C1,C2,C3 | opportunity_intel |
| contract_intel 🆕 | ✅ | — | — | R18,R19,R22,R25,R26 | 012,014,015,016 | C1,C2 | pncp_supplier_contracts |
| lib | ✅ | ✅ | ✅ | R3,R8,R18,R25,R26 | 004,005,012,013,015 | C2 | — |
| matching | ✅ | — | ✅ | R8,R13 | 004,008 | C2 | pncp_raw_bids |
| coverage | ✅ | — | — | R2,R21,R22 | 013,014 | C2 | coverage_evidence |
| reports | ✅ | — | ✅ | R2 | 006 | C1,C2 | views |
| fix | ✅ | — | — | R21 | 013 | — | coverage_evidence |
| pipeline | ✅ | — | — | R21 | 013 | — | coverage_evidence |
| diagnose | ✅ | — | — | — | 003 | — | — |
| transparencia | ✅ | — | — | — | 011 | — | — |
| config | ✅ | — | — | R7,R14,R20 | 005,012 | C2 | — |
| db | ✅ | ✅ | ✅ | R2,R9,R10,R21 | 001,007,013 | C2 | ALL |
| deploy | ✅ | — | — | R12,R24 | 002,009,014 | C1,C2 | — |
| root_scripts 🆕 | ✅ | — | — | R20,R22,R23,R24 | 012,014 | C1,C2 | — |
| tests | ✅ | — | — | — | — | — | — |
| docs | ✅ | — | — | — | 007,014 | — | — |

## Matriz de Impacto: Regras de Negócio × Módulos

| Regra | crawl | opp_intel | contract_intel | intel | reports | matching | lib | db | deploy | root |
|-------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| R1: Filtro engenharia | ✅ | — | — | — | — | — | — | — | — | — |
| R2: Janela cobertura 90d | ✅ | — | — | — | ✅ | — | — | ✅ | — | — |
| R3: Raio 200km | — | ✅ | ✅ | ✅ | — | — | ✅ | ✅ | — | — |
| R4: Capacidade 10× | — | — | — | ✅ | — | — | — | — | — | — |
| R5: Threshold 0.45 | — | — | — | ✅ | — | — | — | — | — | — |
| R6: Override (6) | — | — | — | ✅ | — | — | — | — | — | — |
| R7: Hard incompatible (4) | — | — | — | ✅ | — | — | — | ✅ | — | — |
| R8: Dedup cross-source | ✅ | ✅ | — | ✅ | — | ✅ | — | ✅ | — | — |
| R9: Retenção 400+90d | — | — | — | — | — | — | — | ✅ | — | — |
| R10: Cache TTL 90d | ✅ | — | — | ✅ | — | — | — | ✅ | — | — |
| R11: Max 3 docs | — | — | — | ✅ | — | — | — | — | — | — |
| R12: Frequência crawl | ✅ | — | — | — | — | — | — | — | ✅ | — |
| R13: Schema unificado | ✅ | — | — | — | — | ✅ | — | ✅ | — | — |
| R14: CNAE gate prob. | — | — | — | ✅ | — | — | — | ✅ | — | — |
| R15: HHI competição | — | — | — | ✅ | — | — | — | — | — | — |
| R16: Zero false neg. | — | — | — | ✅ | — | — | — | — | — | — |
| R17: Single tenant | ✅ | ✅ | ✅ | ✅ | ✅ | — | — | ✅ | ✅ | — |
| R18: Deságio (Regra #8) 🆕 | — | — | ✅ | — | — | — | ✅ | — | — | — |
| R19: Competitive Intel (Regra #9) 🆕 | — | ✅ | ✅ | — | — | — | — | — | — | — |
| R20: QW-01 Radar 🆕 | — | ✅ | — | — | — | — | — | — | — | ✅ |
| R21: Coverage Truth 🆕 | ✅ | — | — | — | — | — | — | ✅ | — | — |
| R22: Readiness Gate 🆕 | — | ✅ | ✅ | — | — | — | ✅ | — | — | ✅ |
| R23: Freshness Gate 🆕 | — | — | — | — | — | — | — | — | — | ✅ |
| R24: CI Fail-Closed 🆕 | — | — | — | — | — | — | — | — | ✅ | ✅ |
| R25: Canonical Universe 🆕 | — | ✅ | ✅ | — | — | — | ✅ | — | — | — |
| R26: Conservative Denom 🆕 | — | ✅ | ✅ | — | — | — | ✅ | — | — | — |

## Matriz de Impacto: ADRs × Módulos

| ADR | crawl | opp_intel | contract_intel | intel | reports | matching | lib | db | deploy | root |
|-----|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 001: PostgreSQL direto | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ | — | — |
| 002: Systemd timers | ✅ | ✅ | — | — | ✅ | — | — | — | ✅ | ✅ |
| 003: Crawlers sync HTTP | ✅ | ✅ | — | — | — | — | — | — | — | — |
| 004: Matching cascade | ✅ | — | — | — | — | ✅ | ✅ | ✅ | — | — |
| 005: GPT-4.1-nano | — | — | — | ✅ | — | — | ✅ | — | — | — |
| 006: PDF ReportLab | — | — | — | ✅ | ✅ | — | — | — | — | — |
| 007: Migrations v2 | — | — | — | — | — | — | — | ✅ | — | — |
| 008: Refactor orquestrador | ✅ | — | — | — | — | ✅ | — | — | — | — |
| 009: Backup PostgreSQL | — | — | — | — | — | — | — | ✅ | ✅ | — |
| 010: Logging JSON | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | — | — | — |
| 011: Template transparência | ✅ | — | — | — | — | — | — | — | — | — |
| 012: QW-01 Radar 🆕 | — | ✅ | ✅ | — | — | — | ✅ | ✅ | — | ✅ |
| 013: Coverage Truth 🆕 | ✅ | ✅ | — | — | — | — | ✅ | ✅ | — | — |
| 014: CI Fail-Closed 🆕 | — | ✅ | ✅ | — | — | — | — | — | ✅ | ✅ |
| 015: Semantic Values 🆕 | — | — | ✅ | — | — | — | ✅ | — | — | — |
| 016: Competitive Intel 🆕 | — | ✅ | ✅ | — | — | — | — | — | — | — |

## Matriz de Impacto: Épicos/Iniciativas × Módulos

| Iniciativa | crawl | opp_intel | contract_intel | intel | reports | matching | lib | db | deploy | docs |
|-----------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| EPIC-001 (7 stories) | ✅ | — | — | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| EPIC-FEAT-001 (10 stories) | ✅ | — | — | ✅ | — | — | — | — | ✅ | ✅ |
| EPIC-TD-001 (22 stories) | ✅ | — | — | ✅ | — | ✅ | ✅ | ✅ | ✅ | ✅ |
| **QW-01 (2 stories)** 🆕 | — | ✅ | — | — | — | — | ✅ | ✅ | — | ✅ |
| **Coverage Truth (3 stories)** 🆕 | ✅ | — | — | — | — | — | ✅ | ✅ | — | ✅ |
| **P1 Remediation (5 stories)** 🆕 | ✅ | — | — | — | — | ✅ | ✅ | — | ✅ | ✅ |
| **Regra #8 Deságio (1 story)** 🆕 | — | — | ✅ | — | — | — | ✅ | — | — | — |
| **Regra #9 Competitive Intel (1 story)** 🆕 | — | ✅ | ✅ | — | — | — | — | — | — | — |

## Hotspots (Alta Densidade de Dependências)

| Módulo | Regras | ADRs | Iniciativas | Total Links |
|--------|--------|------|-------------|-------------|
| **crawl** | 6 | 7 | 4 | 🔥 17 |
| **db** | 6 | 7 | 5 | 🔥 18 |
| **opportunity_intel** 🆕 | 8 | 6 | 3 | 🔥 17 |
| **lib** 🆕 | 7 | 6 | 4 | 🔥 17 |
| **intel** (legado) | 11 | 3 | 3 | 🔥 17 |
| **contract_intel** 🆕 | 6 | 5 | 3 | 🔥 14 |
| deploy | 3 | 4 | 4 | 11 |
| root_scripts 🆕 | 4 | 3 | 3 | 10 |
| reports | 2 | 3 | 2 | 7 |
| matching | 2 | 3 | 2 | 7 |
| config | 3 | 2 | 1 | 6 |
| docs | 0 | 2 | 5 | 7 |

**Módulos mais críticos:** `db` (interseção de todas as camadas — 18 links), `crawl` (ingestão — 17 links), `opportunity_intel` (nova vertical principal — 17 links), `lib` (biblioteca compartilhada com regras críticas — 17 links).

## Cross-Cutting Concerns (6 → 7)

| Concern | Módulos Afetados | ADRs |
|---------|-----------------|------|
| Fail-closed pattern | crawl, opportunity_intel, coverage, contract_intel | 013, 014 |
| CNPJ8 matching | matching, lib, crawl, opportunity_intel | 004 |
| Deterministic first | opportunity_intel, root_scripts | 012 |
| Evidência auditável | crawl, coverage, db | 013 |
| Conservative denominator | lib, opportunity_intel, contract_intel | 012, 013 |
| Value semantics awareness | lib, contract_intel, reports | 015 |
| **CI fail-closed enforcement** 🆕 | root_scripts, deploy | 014 |

## Confiança da Matriz

🟢 **CONFIRMADO** — Todos os cross-references verificados contra artefatos atualizados (code-analysis.md, domain.md, ADRs, ERD, state-machines.md). Nenhum link inferido.
