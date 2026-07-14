---
story_id: B2G-BACKFILL-01
title: "Backfill PNCP controlado — 90 dias, SC/PR/RS, modalidades AEC"
status: ready
priority: P0
risk_level: STANDARD
effort: M
agent: "@dev"
epic: EPIC-MASTER-B2G-READINESS
phase: 4
depends_on: [B2G-CRAWL-01, B2G-DB-01, B2G-DB-05]
blocks: [B2G-INTEL-02]
---

# Story B2G-BACKFILL-01: Backfill PNCP Controlado

## Problema

Dados históricos de licitações e contratos são a matéria-prima da inteligência comercial. O PNCP é a fonte mais confiável (100% source health), mas o backfill nunca foi executado de forma controlada na VPS. O crawl de 30 dias feito em 2026-07-11 (1.463 records, 528 matched) foi manual e local.

## Escopo

**IN:** Backfill 90 dias (depois expandir para 365), SC/PR/RS, modalidades 4 (Concorrência), 5 (Pregão), 6 (Concurso), 7 (Dispensa), com checkpoints, resume, e manifest de execução.

**OUT:** Backfill de outras fontes (B2G-BACKFILL-04), backfill nacional (todos os estados).

## Acceptance Criteria

1. **AC1:** Backfill 90 dias PNCP executado na VPS — registros persistidos sem duplicação
2. **AC2:** Checkpoint funcional — interromper e retomar não reinicia da página 1
3. **AC3:** Manifest de execução gerado com: records obtidos, inseridos, atualizados, erros, duração
4. **AC4:** Entity matching executado após backfill — ≥80% dos records matched
5. **AC5:** Cobertura de entidades no raio 200km ≥40% (baseline: 8.2% só PNCP)

## Tasks

- [ ] Task 1: Configurar parâmetros (UFs, modalidades, date range, max pages)
- [ ] Task 2: Executar backfill 7 dias (teste controlado)
- [ ] Task 3: Validar dados — sem duplicatas, content_hash único, matching OK
- [ ] Task 4: Executar backfill 90 dias
- [ ] Task 5: Executar entity matching
- [ ] Task 6: Gerar coverage manifest

## Definition of Done

- [ ] Backfill 90 dias completo
- [ ] Zero duplicatas (content_hash único)
- [ ] Checkpoint funcional (testado com interrupção simulada)
- [ ] Manifest de execução gerado
- [ ] Cobertura ≥40%

## Arquivos Afetados

- `scripts/crawl/monitor.py`
- `scripts/crawl/checkpoint.py`
- `scripts/opportunity_intel/backfill.py`
- `scripts/opportunity_intel/manifest.py`
