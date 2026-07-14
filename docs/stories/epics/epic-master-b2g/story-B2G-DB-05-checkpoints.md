---
story_id: B2G-DB-05
title: "Sistema de checkpoints para retomada de backfill"
status: ready
priority: P1
risk_level: STANDARD
effort: M
agent: "@dev"
epic: EPIC-MASTER-B2G-READINESS
phase: 2
depends_on: [B2G-DB-01]
blocks: [B2G-BACKFILL-01]
---

# Story B2G-DB-05: Checkpoint System

## Problema

Backfills longos (90+ dias, múltiplas fontes) precisam sobreviver a interrupções. Atualmente `checkpoint.py` existe (14K linhas) mas nunca foi testado em condições reais de interrupção. Sem checkpoint confiável, qualquer falha força reinício do zero — inviável para backfills de semanas.

## Escopo

**IN:** Validar e expandir `checkpoint.py` com: source, endpoint, entidade, intervalo temporal, página, cursor, último sucesso, última tentativa, status, registros, erro, retry count, crawler version. Testar com interrupção simulada. Integrar com `monitor.py`.

**OUT:** Novo sistema do zero (reaproveitar `checkpoint.py` existente).

## Acceptance Criteria

1. **AC1:** Tabela `ingestion_checkpoints` tem colunas: source, endpoint, entity_type, time_range_start, time_range_end, page, cursor, last_success_at, last_attempt_at, status, records_fetched, error_message, retry_count, crawler_version
2. **AC2:** Backfill interrompido (kill -9) retoma da última página checkpointada, não da página 1
3. **AC3:** Zero duplicatas após retomada (content_hash + upsert)
4. **AC4:** `backfill.py --resume <run_id>` funcional
5. **AC5:** `backfill.py --status <run_id>` mostra progresso (páginas, registros, erros, ETA)

## Tasks

- [ ] Task 1: Auditar schema de `ingestion_checkpoints` e alinhar com código
- [ ] Task 2: Implementar save/load de checkpoint em `checkpoint.py`
- [ ] Task 3: Integrar com `backfill.py` (resume, status)
- [ ] Task 4: Testar interrupção e retomada (simular kill -9)
- [ ] Task 5: Verificar zero duplicatas após retomada

## Definition of Done

- [ ] Checkpoint salvo a cada página processada
- [ ] Resume funcional após interrupção
- [ ] Zero duplicatas
- [ ] CLI status mostra progresso
- [ ] Testado com interrupção simulada

## Arquivos Afetados

- `scripts/crawl/checkpoint.py`
- `scripts/opportunity_intel/backfill.py`
- `db/migrations/004_ingestion_tables.sql`
