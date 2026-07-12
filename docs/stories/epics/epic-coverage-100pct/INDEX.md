# EPIC-COVERAGE-100PCT — Plano Mestre de Cobertura 100%

## Status: Em Andamento — 3.4 Concluida

Este epic coordena a expansao de cobertura de 47% para 95%+ das 2.085 entidades publicas de Santa Catarina.

**Relatorio final de validacao:** [coverage-final.md](../epic-coverage/coverage-final.md)
**Dashboard interativo:** [dashboard-cobertura.html](../epic-coverage/dashboard-cobertura.html)
**CSV de entes descobertos:** [entes-descobertos.csv](../epic-coverage/entes-descobertos.csv) (1264 entes)

## Cobertura Atual: 39.4% (821/2085) — Fontes: PNCP, CIGA CKAN, PCP

## Quick Wins (Dia 0 — Zero Crawl Adicional)

| # | Story | Ganho | Esforco | Arquivo |
|---|-------|-------|---------|---------|
| 1.8 | Match Hierárquico Secretaria → Prefeitura | **+350-400 entes** | 3h | `story-COVERAGE-1.8-hierarchical-match.md` (22 KB) |
| 1.11 | Geocoding 604 Entes Sem Coordenadas | 604 entes geocodificados | 2h | `story-COVERAGE-1.11-geocoding.md` (28 KB) |
| 1.9 | SC Dados Abertos Municipality Fix | +30-80 entes | 2h | `story-COVERAGE-1.9-sc-dados-abertos-fix.md` (25 KB) |
| 1.10 | PCP Diagnostic & Fix | Diagnóstico | 3h | `story-COVERAGE-1.10-pcp-diagnostic.md` (15 KB) |

## Todas as Stories (19)

### Fase 1 — Fontes Sem Autenticação + Quick Wins (Dias 1-2) → 65-75%

| # | Story | Prio | Horas | Executor | Arquivo |
|---|-------|------|-------|----------|---------|
| 1.1 | Entity Matching Enhancement | P0 | 3h | @analyst + @dev | `story-COVERAGE-1.1-entity-matching-enhancement.md` |
| 1.2 | CIGA CKAN Crawler | P0 | 5h | @dev | `story-COVERAGE-1.2-ciga-ckan-crawler.md` |
| 1.3 | Portal Transparencia Batch Detect | P1 | 5h | @dev | `story-COVERAGE-1.3-portal-transparencia-batch-detect.md` |
| 1.4 | PNCP v3 Coverage Expansion | P1 | 2h | @dev | `story-COVERAGE-1.4-pncp-v3-coverage-expansion.md` |
| 1.5 | DOM-SC Crawler Expansion | P1 | 3h | @dev | `story-COVERAGE-1.5-dom-sc-expansion.md` |
| 1.6 | PCP Coverage Expansion | P2 | 2h | @dev | `story-COVERAGE-1.6-pcp-coverage-expansion.md` |
| 1.7 | Gap Analysis Report | P1 | 2h | @analyst | `story-COVERAGE-1.7-gap-analysis-report.md` |
| 1.8 🆕 | Match Hierárquico | P0 | 3h | @data-engineer | `story-COVERAGE-1.8-hierarchical-match.md` |
| 1.9 🆕 | SC Dados Abertos Fix | P1 | 2h | @data-engineer | `story-COVERAGE-1.9-sc-dados-abertos-fix.md` |
| 1.10 🆕 | PCP Diagnostic | P1 | 3h | @dev | `story-COVERAGE-1.10-pcp-diagnostic.md` |
| 1.11 🆕 | Geocoding | P1 | 2h | @dev | `story-COVERAGE-1.11-geocoding.md` |

### Fase 2 — Fontes com Credenciais (Dias 3-6) → 80-90%

| # | Story | Prio | Horas | Executor | Arquivo |
|---|-------|------|-------|----------|---------|
| 2.1 | MiDES BigQuery Integration | P0/PULAR | 8h | @data-engineer | `story-COVERAGE-2.1-mides-bigquery-integration.md` | **PULADA** — BigQuery account indisponivel |
| 2.2 | SC Compras Crawler Activation | P1 | 5h | @dev | `story-COVERAGE-2.2-sc-compras-crawler-activation.md` |
| 2.3 | DOE-SC Crawler Activation | P1 | 5h | @dev | `story-COVERAGE-2.3-doe-sc-crawler-activation.md` |
| 2.4 | Entity Coverage Rebuild | P1 | 2h | @dev + @data-engineer | `story-COVERAGE-2.4-entity-coverage-rebuild.md` |

### Fase 3 — Scraping Pesado + Residuais (Dias 7-11) → 95%+

| # | Story | Prio | Horas | Executor | Arquivo |
|---|-------|------|-------|----------|---------|
| 3.1 | Selenium Crawler JS Portals | P0 | 8h | @dev | `story-COVERAGE-3.1-selenium-crawler-js-portals.md` |
| 3.2 | Portal Transparencia Individual | P1 | 6h | @dev | `story-COVERAGE-3.2-portal-transparencia-individual.md` |
| 3.3 | Multi-Source Backfill Pipeline | P1 | 5h | @dev + @data-engineer | `story-COVERAGE-3.3-multi-source-backfill-pipeline.md` |
| **3.4** | **Coverage Validation & Documentation** | **P1** | **4h** | **@dev** | **`story-COVERAGE-3.4-coverage-validation-documentation.md` ✅** |

## Projeção de Cobertura

```
47% → [1.8+1.11 Quick Wins D0] → 66% → [Fase 1 D1-2] → 75% → [Fase 2 D3-6] → 90% → [Fase 3 D7-11] → 95%+
```

## Próximos Passos

1. `@po *validate-story-draft` — validar cada story (transição Draft → Ready)
2. Quick Wins Dia 0: 1.8 + 1.11 + 1.9 em paralelo
3. Fase 1 Dias 1-2: 1.1-1.7 + 1.10 em paralelo
4. Gate review após cada Fase
