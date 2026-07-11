# Story TD-5.3: Otimizacao de Performance

**Status:** Done
**Epic:** EPIC-TD-001
**Executor:** @data-engineer
**Quality Gate:** @dev
**Quality Gate Tools:** [coderabbit, pytest, pgTAP]
**Fase:** 5 -- Resiliencia & Observabilidade
**Estimativa:** 12 horas
**Prioridade:** P1

## Description

Resolver quatro deficits de performance e qualidade de dados no banco:

1. **TD-DB-04 (MEDIUM):** Funcao `upsert_pncp_supplier_contracts` opera row-by-row em vez de set-based. A funcao set-based ja existe -- apenas consolidar (depende da TD-3.2).
2. **TD-DB-09 (LOW):** Coluna `esfera_id` em `pncp_raw_bids` sem CHECK constraint, permitindo valores invalidos. Adicionar `CHECK (esfera_id IN ('F','E','M','D'))`.
3. **TD-DB-13 (MEDIUM):** Codigo Python referencia colunas/tabelas que nao existem no schema real. Auditar `datalake_helper.py`, `local_datalake.py` e `monitor.py` para divergencias de schema.
4. **TD-DB-14 (MEDIUM):** Funcao `purge_old_bids` faz DELETE fisico irreversivel. Migrar para UPDATE `is_active = false` (soft delete).

## Business Value

As quatro correcoes eliminam riscos operacionais e de performance: upserts lentos aumentam tempo de processamento de contratos; dados invalidos em `esfera_id` corrompem analises; divergencias entre codigo e schema causam erros em producao; e DELETE fisico impede恢复 de dados em caso de acidente. Em conjunto, reduzem o risco de incidentes e o tempo de processamento.

## Acceptance Criteria

- [x] AC1: Dado que a funcao `upsert_pncp_supplier_contracts` existe, Quando a consolidacao com a versao set-based for concluida (apos TD-3.2), Entao a operacao de upsert processa multiplos registros por statement e nao row-by-row
- [x] AC2: Dado a coluna `esfera_id` em `pncp_raw_bids`, Quando a migration for aplicada, Entao a CHECK constraint `esfera_id IN (1,2,3,4)` esta ativa e valores fora desse conjunto sao rejeitados (adaptado: coluna e INT, nao TEXT)
- [x] AC3: Dado os modulos `datalake_helper.py`, `local_datalake.py` e `monitor.py`, Quando auditados contra o schema real do banco, Entao todas as divergencias de nomes de colunas/tabelas sao identificadas e corrigidas
- [x] AC4: Dado que zero divergencias foram encontradas apos auditoria, Quando todos os modulos sao testados, Entao nenhum erro de "column not found" ou "table not exists" ocorre
- [x] AC5: Dado a funcao `purge_old_bids`, Quando executada, Entao ela realiza UPDATE `is_active = false` em vez de DELETE fisico
- [x] AC6: Dado que o soft delete esta implementado, Quando um registro e "deletado", Entao ele permanece na tabela com `is_active = false` e pode ser restaurado
- [x] AC7: Dado que a retention de soft-delete esta configurada, Quando registros ultrapassam o periodo de retencao, Entao eles sao elegiveis para purga fisica (opcional, configuravel)

## Scope

### IN
- Consolidacao upsert set-based
- CHECK constraint esfera_id
- Auditoria de divergencia schema vs codigo
- Soft-delete no purge

### OUT
- Outros indexes (GIN, HNSW -- ja na TD-1.1 e TD-2.3)
- Index superdimensionado GIST (ja na TD-2.3)

## Dependencies

- Bloqueado por: TD-2.1 (schema baseline para auditar divergencias), TD-3.2 (consolidacao upsert)
- Bloqueia: NONE

## Risks

| Risco | Probabilidade | Impacto | Mitigacao |
|-------|---------------|---------|-----------|
| Soft-delete quebra queries existentes que assumem DELETE fisico | MEDIA | ALTO | Revisar todas as queries que chamam purge_old_bids; atualizar se necessario |
| Migration de CHECK constraint falha se existem dados invalidos | ALTA | MEDIO | Rodar UPDATE preparatorio para limpar dados antes da constraint |
| Divergencias de schema nao completamente mapeadas | MEDIA | ALTO | Auditoria exaustiva com script automatizado de comparacao |
| Upsert set-based tem performance diferente do esperado | BAIXA | BAIXO | Testar com volume de dados real antes de promover |

## Technical Notes

Referencias ao assessment:
- TD-DB-04 (MEDIUM): upsert_pncp_supplier_contracts row-by-row -- 3h
- TD-DB-09 (LOW): esfera_id sem CHECK constraint -- 1h
- TD-DB-13 (MEDIUM): Schema divergence codigo x banco -- 4h
- TD-DB-14 (MEDIUM): purge_old_bids faz DELETE fisico -- 4h

## Definition of Done

- [x] Upsert set-based operacional (ja consolidado pelo TD-3.2)
- [x] CHECK constraint esfera_id ativa
- [x] Zero divergencias schema vs codigo
- [x] Soft-delete ativo em purge_old_bids
- [x] Migrations versionadas

## File List

- `db/migrations/018-td-5.3_esfera_id_check.sql` (novo)
- `db/migrations/019-td-5.3_soft_delete_purge_docs.sql` (novo)
- `scripts/datalake_helper.py` (modificado -- correcao de divergencias schema)
- `scripts/local_datalake.py` (modificado -- correcao de divergencias schema)
- `docs/stories/epics/epic-td-001-resolution/story-TD-5.3-otimizacao-performance.md` (modificado -- status, checkboxes)
- `plan/self-critique-td-5.3.json` (novo)

### Notas sobre o File List original vs. realidade

O File List original da story mencionava:
- `scripts/upsert_supplier_contracts.sql` (modificado) -- Nao existe; a funcao upsert ja foi consolidada no TD-3.2 em `db/migrations/006_upsert_rpcs.sql`
- `supabase/migrations/XXX-td-5.3_esfera_id_check.sql` -- Criado como `db/migrations/018-td-5.3_esfera_id_check.sql` (migrations estao em db/migrations/)
- `supabase/migrations/XXX-td-5.3_soft_delete_purge.sql` -- Criado como `db/migrations/019-td-5.3_soft_delete_purge_docs.sql`
- `monitor.py` (modificado) -- Nao havia divergencias (monitor.py delega para modulos especializados)
- `scripts/purge_old_bids.py` (modificado) -- Nao existe; purge e via SQL RPC (migration 008 ja implementa soft-delete)

## Change Log

| Data | Mudanca | Autor |
|------|---------|-------|
| 2026-07-11 | Story criada | @pm |
| 2026-07-11 | Validated GO (10/10) — adicionado Business Value, Risks, Executor, QG, Prioridade; ACs convertidas para Given/When/Then | @po |
| 2026-07-11 | 1.0.0 | Development started (yolo mode) — Status: Ready → InProgress | @dev |
| 2026-07-11 | 1.0.0 | Development complete — Status: InProgress → InReview | @dev |
| 2026-07-11 | 1.0.0 | QA Gate PASS — Status: InReview → Done — 7/7 ACs, zero issues | @qa |

## QA Results

### Review Date: 2026-07-11

### Reviewed By: Quinn (Guardian)

### Verdict: PASS

### Quality Checks Summary

| Check | Result | Notes |
|-------|--------|-------|
| 1. Code Review | PASS | Clean refactoring, constants centralize column refs, _normalize_esferas() robust |
| 2. Unit Tests | PASS | 7 test cases for _normalize_esferas(), upsert contract schema validated |
| 3. Acceptance Criteria | PASS | 7/7 ACs fully implemented and verified |
| 4. No Regressions | PASS | All changes are bug fixes for non-existent columns — no behavioral regression |
| 5. Performance | PASS | CHECK constraint negligible overhead, soft-delete UPDATE acceptable |
| 6. Security | PASS | No injection vectors, parameterized queries, data integrity via CHECK |
| 7. Documentation | PASS | Migrations documented, COMMENTS ON FUNCTION, File List notes explain deviations |

### Correcoes Verificadas

**datalake_helper.py:**
- Substituidas colunas inexistentes (`numero_controle_pncp`, `ni_fornecedor`, `esfera`, `valor_global`, `data_assinatura`, `situacao_compra`, `unidade_nome`, `link_sistema_origem`) por aliases corretos (`contrato_id AS numero_controle_pncp`, `fornecedor_cnpj AS ni_fornecedor`, `valor_total AS valor_global`, `data_publicacao AS data_assinatura`)
- Removido `is_active` filter em `pncp_supplier_contracts` (coluna nao existe na tabela)
- Adicionada `_normalize_esferas()` para converter ['F','E','M','D'] → [1,2,3,4]

**local_datalake.py:**
- Corrigidos aliases SQL em 4 comandos (supplier, pricing, competitors, search)
- Removidas referencias a `is_active`, `situacao_compra`, `ni_fornecedor`, `valor_global`, `data_assinatura`

**Migration 018:** CHECK constraint `esfera_id IS NULL OR IN (1,2,3,4)` ativa

**Migration 019:** `purge_old_bids` confirmado como soft-delete (UPDATE is_active = FALSE); `purge_old_bids_hard()` adicionada para purga fisica controlada

### Gate Status

Gate: PASS → docs/qa/gates/td-5.3-otimizacao-performance.yml
