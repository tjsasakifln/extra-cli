---
name: epic-coverage-100pct
description: "Master plan EPIC-COVERAGE-100PCT: go from 47% to 100% coverage of 2,085 SC public entities across 3 phases, 15 stories, 12 sources"
metadata:
  type: project
---

# EPIC-COVERAGE-100PCT — Plano Mestre de Cobertura 100%

**Criado:** 2026-07-11 por River (SM)
**Localizacao:** `docs/stories/epics/epic-coverage-100pct/EPIC-COVERAGE-100PCT.md`

## Contexto

O projeto atingiu 47% de cobertura (972/2.085 entidades SC) apos a execucao de 8 crawlers (EPIC-FEAT-001) e correcao da PNCP API v3 (TD-8.3). Este plano mestre coordena os passos restantes para 100%.

## Baseline

- **47% (972/2.085)** cobertos por PNCP + DOM-SC + PCP + ComprasGov + Contracts
- **53% (1.113)** descobertos
- Fonte mais promissora descoberta recentemente: **CIGA CKAN** (317 municipios, sem auth)

## Estrutura

| Fase | Dias | Cobertura Alvo | Fontes Principais |
|------|------|----------------|-------------------|
| 1 | 1-2 | 60-70% | Entity matching, CIGA CKAN, Portal Transparencia batch, PNCP expandido, DOM-SC, PCP |
| 2 | 3-6 | 80-90% | MiDES BigQuery (se conta disponivel), SC Compras, DOE-SC, Coverage rebuild |
| 3 | 7-11 | 95-100% | Selenium, Portal Transparencia individual, Multi-source backfill, Validacao |

## Inviavel

- **TCE-SC e-Sfinge** — exige certificado ICP-Brasil A1/A3 (R$ 300-800/ano)
- DOM-SC API oficial exige API Key (contrato CIGA)
- 295 portais individuais inviaveis; batch detect_platform cobre ~8 plataformas

## Story IDs

COVERAGE-1.1 a COVERAGE-1.7 (Fase 1), COVERAGE-2.1 a COVERAGE-2.4 (Fase 2), COVERAGE-3.1 a COVERAGE-3.4 (Fase 3)

**Dependencia:** PM precisa revisar e aprovar o plano mestre antes de iniciar a criacao das stories individuais.

## Arquivo Principal

`docs/stories/epics/epic-coverage-100pct/EPIC-COVERAGE-100PCT.md`
