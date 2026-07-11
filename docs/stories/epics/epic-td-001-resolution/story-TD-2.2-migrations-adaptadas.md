# Story TD-2.2: Aplicar Migrations 009-012 Adaptadas

**Status:** Done
**Epic:** EPIC-TD-001
**Executor:** @data-engineer
**Quality Gate:** @dev
**Quality Gate Tools:** [coderabbit]
**Fase:** 2 -- Schema & Migrations
**Estimativa:** 5 horas
**Prioridade:** P2

## Description

As migrations 009, 011 e 012 (criacao das tabelas `entity_coverage`, views `v_coverage_summary`, `v_unmatched_bids`, e tabela `coverage_snapshots`) nunca foram aplicadas no schema real. A migration 010 (`match_logging`) pode ja ter sido aplicada parcialmente.

Criar novas migrations adaptadas ao schema atual (baseado no baseline da TD-2.1), tratando conflitos e garantindo que as funcionalidades de coverage e match logging estejam operacionais sem quebrar o schema existente.

## Business Value

As funcionalidades de coverage (entity_coverage, coverage_snapshots) e match_logging sao essenciais para o pipeline de inteligencia que rastreia quais licitacoes foram cobertas e como os matches foram feitos. Sem estas tabelas e views, nao ha visibilidade sobre a efetividade do crawler nem base para diagnosticar lacunas de cobertura.

## Acceptance Criteria

- [x] AC1: Verificado: colunas match_logging NAO estao no baseline 001-v2, mas existem no banco real (adicao direta via monitor.py). Documentado.
- [x] AC2: entity_coverage ja existe no baseline 001-v2 (Section 2.3). Migration 002-v2 adaptada com IF NOT EXISTS e triggers.
- [x] AC3: v_coverage_summary ja existe no baseline 001-v2 (Section 4.3). Incluida em 003-v2 com CREATE OR REPLACE.
- [x] AC4: v_unmatched_bids NAO existe no baseline. Criada como NOVA em migration 003-v2. Testada com 989 registros retornados.
- [x] AC5: coverage_snapshots ja existe no baseline 001-v2 (Section 2.6). Migration 004-v2 adaptada com IF NOT EXISTS.
- [x] AC6: match_logging colunas ja existem no banco real. Migration 005-v2 adaptada com ADD COLUMN IF NOT EXISTS (NO-OP no banco atual, necessaria para ambientes novos).
- [x] AC7: Todas as 4 migrations registradas em _migrations: 002-v2, 003-v2, 004-v2, 005-v2.
- [x] AC8: Views e triggers testados com dados existentes. v_unmatched_bids: 989 rows. v_coverage_summary: 5 rows. v_coverage_gaps: 1864 entes. generate_coverage_snapshot: 2 snapshots gerados.

## Scope

### IN
- Migrations adaptadas para entity_coverage, views, coverage_snapshots
- Verificacao de match_logging
- Registro na tabela _migrations

### OUT
- Correcao de dados existentes (apenas schema)
- Refatoracao das funcoes de coverage (apenas criacao das estruturas)

## Dependencies

- Bloqueado por: TD-2.1 (schema baseline necessario)
- Bloqueia: NONE (funcionalidades standalone apos criacao das estruturas)

## Risks

| Risco | Probabilidade | Impacto | Mitigacao |
|-------|---------------|---------|-----------|
| Triggers e views referenciarem tabelas/colunas renomeadas ou removidas no schema real | MEDIA | ALTO | Validar cada referencia contra o schema baseline antes de criar |
| Match_logging ja existir parcialmente com schema diferente do esperado | MEDIA | MEDIO | Documentar diferencas e adaptar migration |
| Conflito de nomes com objetos existentes no schema | BAIXA | ALTO | Usar IF NOT EXISTS e verificar conflitos antes de aplicar |

## Technical Notes

Referencias ao assessment:
- TD-DB-02a (HIGH): Migrations 009/011/012 nao aplicadas (entity_coverage, views, coverage_snapshots)
- TD-DB-02b (LOW): Migration 010 nao aplicada (match_logging)
- Risco: triggers e views podem referenciar tabelas/colunas que nao existem no schema real
- Estrategia: criar migrations adaptadas, nao copiar as originais cegamente

## Definition of Done

- [x] entity_coverage funcional com triggers (ja existia no baseline, verificado)
- [x] v_coverage_summary e v_unmatched_bids criadas e retornando dados (989 rows em v_unmatched_bids)
- [x] coverage_snapshots criada (ja existia no baseline, generate_coverage_snapshot gerou 2 snapshots)
- [x] match_logging verificado e adaptado (colunas ja existem no banco real, migration 005-v2 criada)
- [x] Todas registradas em _migrations (002-v2, 003-v2, 004-v2, 005-v2)

## File List

- `supabase/migrations/002-v2-td-2.2_entity_coverage.sql` (criado)
- `supabase/migrations/003-v2-td-2.2_coverage_views.sql` (criado)
- `supabase/migrations/004-v2-td-2.2_coverage_snapshots.sql` (criado)
- `supabase/migrations/005-v2-td-2.2_match_logging.sql` (criado)
- `docs/td-001/migrations-adaptadas.md` (criado)
- `plan/self-critique-td-2.2.json` (criado)
- `plan/dod-report-td-2.2.md` (criado)

## Change Log

| Data | Mudanca | Autor |
|------|---------|-------|
| 2026-07-11 | Story criada | @pm |
| 2026-07-11 | 1.0.1 | Validated GO (10/10) — Revalidated Ready — Adicionados: Executor, Quality Gate, Prioridade, Business Value, Risks; ACs convertidas para GWT | @po |
| 2026-07-11 | 1.1.0 | Development started (YOLO mode) — Status: Ready → InProgress | @dev |
| 2026-07-11 | 2.0.0 | Development complete — Status: InProgress → InReview | @dev |
| 2026-07-11 | 3.0.0 | QA Gate CONCERNS — Status: InReview → Done | @qa |
| 2026-07-11 | 3.1.0 | CONCERNS fixes applied — Status: Done → InReview. MNT-001: dependencia 005-v2 → 003-v2 documentada. MNT-002: public. qualifier adicionado em trigger functions e generate_coverage_snapshot. DOC-001: checksums substituidos por sha256 real. | @dev |
| 2026-07-11 | 4.0.0 | QA Gate PASS (re-run) — Status: InReview → Done. Todos os 3 CONCERNS issues resolvidos. 7/7 checks aprovados. | @qa |

## QA Results

### Review 1: 2026-07-11 (CONCERNS)

### Reviewed By: Quinn (Guardian)

### 7 Quality Checks

| Check | Result | Details |
|-------|--------|---------|
| 1. Code Review | PASS with issues | SQL bem estruturado, idempotente, schema qualificado (1 excecao em triggers). 2 issues medium documentados. |
| 2. Unit Tests | N/A | Schema-only changes (SQL migrations), sem codigo de aplicacao para testar. |
| 3. Acceptance Criteria | ALL PASS (8/8) | AC1-AC8 verificados contra o schema baseline 001-v2, confirmados individualmente. |
| 4. No Regressions | PASS | Todas as operacoes sao idempotentes (IF NOT EXISTS / OR REPLACE). Nenhum objeto existente e alterado destrutivamente. |
| 5. Performance | PASS | Indexes adequados para as queries esperadas. Sem problemas de performance evidentes. |
| 6. Security | PASS | SQL estatico, sem injecao, sem credenciais hardcoded, sem EXECUTE dinamico. |
| 7. Documentation | PASS | docs/td-001/migrations-adaptadas.md com analise completa. COMMENT ON em todos os objetos. Ordem de aplicacao documentada. |

### Gate Status (Review 1)

Gate: CONCERNS → docs/qa/gates/td-2.2-migrations-adaptadas.yml

---

### Review 2: 2026-07-11 (Re-run — PASS)

### Reviewed By: Quinn (Guardian)

### Fixes Verificados

| Issue | Status | Evidencia |
|-------|--------|-----------|
| MNT-001: Dependencia 005-v2→003-v2 | RESOLVIDO | Header de 003-v2 documenta explicitamente que DEPENDE de 005-v2, com ordem de aplicacao obrigatoria (1. 002-v2, 2. 004-v2, 3. 005-v2, 4. 003-v2). |
| MNT-002: public. qualifier ausente | RESOLVIDO | 8 referencias corrigidas: entity_coverage em trigger functions (002-v2) e generate_coverage_snapshot (004-v2) agora usam public. prefix. sc_public_entities e coverage_snapshots tambem qualificados. |
| DOC-001: checksums placeholder | RESOLVIDO | sha256 reais em todas 4 migrations: e83b7c... (002-v2), b8f1a5... (003-v2), 996398... (004-v2), 0d4da4... (005-v2). |

### 7 Quality Checks (Re-run)

| Check | Result | Details |
|-------|--------|---------|
| 1. Code Review | PASS | SQL bem estruturado, idempotente. public. qualifier consistente em todos os objetos e funcoes. CodeRabbit identificou 2 achados menores pre-existentes (rollback_sql generico em 002-v2 que referenciaria tabela do baseline; escopo de constraint check em DO blocks) — ambos sao padroes herdados, nao introduzidos por TD-2.2. Documentados como divida tecnica. |
| 2. Unit Tests | N/A | Schema-only changes (SQL migrations). |
| 3. Acceptance Criteria | ALL PASS (8/8) | AC1-AC8 permanecem satisfeitos. Os 3 CONCERNS eram de qualidade de codigo, nao de lacunas de requisitos. |
| 4. No Regressions | PASS | Todas as operacoes sao idempotentes (IF NOT EXISTS / OR REPLACE). Nenhum objeto existente alterado destrutivamente. |
| 5. Performance | PASS | Indexes adequados. Sem alteracoes de performance desde a revisao anterior. |
| 6. Security | PASS | SQL estatico, sem injecao, sem credenciais, sem EXECUTE dinamico. |
| 7. Documentation | PASS | 003-v2 header atualizado com secao de dependencia. Ordem de aplicacao documentada. Real sha256 checksums permitem deteccao de drift. |

### Gate Status (Review 2)

Gate: PASS → docs/qa/gates/td-2.2-migrations-adaptadas.yml
