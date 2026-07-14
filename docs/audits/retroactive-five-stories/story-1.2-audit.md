# Auditoria Retroativa — Story 1.2: Unify Schema

**Data:** 2026-07-13
**Auditor:** AIOX Master (coordenação)

---

## Veredito: CONCERNS

## Confiança: Média

---

## Resumo Executivo

Story 1.2 estabeleceu a fundação de schema para todo o projeto: 7 migrations, 5 views canônicas, auditoria automática de SQL e baseline SHA-256. As migrações são estruturalmente corretas com padrões adequados (IF NOT EXISTS, NOT VALID, LOCK_TIMEOUT). Porém, 3 ACs críticos não foram validados: performance do upsert set-based (AC #10), métricas de concorrência contra PostgreSQL real (AC #9), e fresh install/upgrade testados contra banco real (TST-001). A segregação de agentes foi quebrada: @dev atuou como Quality Gate em story com executor @data-engineer.

---

## Contrato Reconstruído

### Problema Original
Três verdades concorrentes de schema (migrations locais, supabase migrations, dump congelado). Bloqueava pipeline de oportunidade e queries de concorrência.

### Escopo Previsto vs Implementado

| Previsto | Status |
|----------|--------|
| Auditoria automática SQL + gap report | ✅ Implementado |
| 5 views canônicas | ✅ Implementado |
| 7 migrations (030-036) | ✅ Implementado |
| Colunas match_logging | ✅ Já existiam (verificado) |
| FK constraints (DT-19, DT-20) | ✅ Implementado |
| UNIQUE cnpj_8 (DT-06) | ✅ Implementado com pre-check |
| Upsert set-based (DT-05) | ✅ Implementado em 006 |
| Baseline SHA-256 | ✅ Implementado |
| Fresh install/upgrade test | ⚠️ Testes existem mas não executados contra DB real |
| Performance benchmark (AC #10) | ❌ Não validado |
| Métricas concorrência PostgreSQL (AC #9) | ❌ Não testado |

---

## Process Violations

| Violação | Detalhe |
|----------|---------|
| **Segregação QA quebrada** | Story declara `Quality Gate: @dev` mas `Executor: @data-engineer`. @dev não é @qa. Story 1.2 é a única com esta violação explícita. |
| **PO close sem QA estruturado** | PO fechou aceitando 4 QA issues como "tech debt". Sem state file. |

---

## Commits e Arquivos

**Commit:** `d2ff075`

### Arquivos Criados (14)
- `scripts/schema/audit_sql_references.py`
- `tests/integration/test_all_sql_references.py`
- `tests/integration/test_migration_fresh_install.py`
- `docs/stories/story-1.2-canonical-views-contract.md`
- `db/migrations/030` a `036` (7 arquivos)
- `output/schema/schema-gap-report.md` + `.json`
- `db/current-schema.sql` + `.sha256`

### Arquivos Modificados (2)
- `db/migrations/006_upsert_rpcs.sql`
- `pyproject.toml`

### Arquivos Arquivados (2)
- `supabase/archive/current-schema.sql_HISTORICAL`
- `supabase/current-schema.sql_HISTORICAL_20260713`

---

## Critérios de Aceite e Rastreabilidade

| AC | Descrição | Status |
|----|-----------|--------|
| AC #1 | Zero query com erro em test_all_sql_references.py | COVERED |
| AC #2 | Zero função com assinatura incompatível | COVERED |
| AC #3 | db/current-schema.sql reflete HEAD | COVERED |
| AC #4 | supabase/current-schema.sql removido/arquivado | COVERED |
| AC #5 | Fresh install passa | NOT-COVERED (teste existe mas não executado contra DB real) |
| AC #6 | Upgrade passa | NOT-COVERED |
| AC #7 | Rollback sem perda de dados | PARTIALLY-COVERED |
| AC #8 | Views canônicas com nomes estáveis | COVERED |
| AC #9 | Métricas concorrência contra PostgreSQL real | NOT-COVERED |
| AC #10 | Upsert set-based <= 30% row-by-row | NOT-COVERED |
| AC #11 | Colunas match_logging existem | COVERED |
| AC #12 | FK orgao_cnpj válida | COVERED |

---

## Segurança

- ✅ SQL injection mitigado: whitelist + %I na função de purge
- ✅ Sem RLS necessário (sistema local)
- ✅ Bandit rule "S" adicionada ao ruff

---

## Banco de Dados

*(Preenchido pelo agente database-audit)*

---

## Arquitetura e Causa Raiz

**Parecer:** PARTIALLY-RESOLVED

- Schema unification: ✅ Três verdades → uma verdade (db/migrations/)
- Views canônicas: ✅ Abstração estável para consumers
- Performance: ⚠️ AC #10 não benchmarkeado — melhoria alegada sem evidência
- Baseline: ✅ SHA-256 + dump permite reconstrução

---

## Dívida Técnica

| ID | Descrição | Severidade | Origem |
|----|-----------|------------|--------|
| REQ-001 | AC #10 (perf set-based) não validado | MEDIUM | INTRODUCED-BY-STORY |
| TST-001 | Fresh install/upgrade não testados contra DB real | MEDIUM | INTRODUCED-BY-STORY |
| TST-002 | AC #9 (métricas concorrência) não testado | MEDIUM | INTRODUCED-BY-STORY |
| DOC-001 | Views contract drift da migration | LOW | INTRODUCED-BY-STORY |

---

## Achados

| ID | Severidade | Origem | Descrição |
|----|-----------|--------|-----------|
| A1.2-01 | HIGH | INTRODUCED-BY-STORY | @dev como Quality Gate em story de @data-engineer — violação de segregação |
| A1.2-02 | MEDIUM | INTRODUCED-BY-STORY | AC #10 (performance) alegado mas não medido |
| A1.2-03 | MEDIUM | INTRODUCED-BY-STORY | Testes de instalação/upgrade nunca executados contra DB |
| A1.2-04 | MEDIUM | INTRODUCED-BY-STORY | Métricas de concorrência não validadas contra PostgreSQL real |
| A1.2-05 | LOW | INTRODUCED-BY-STORY | Contrato das views tem drift da implementação real |

---

## Recomendação Final

**CONCERNS.** Schema estruturalmente sólido. A violação de segregação de agentes (Quality Gate: @dev) é significativa para o protocolo AIOX. ACs de performance e testes de instalação pendentes de validação real. As views canônicas são uma boa abstração mas precisam de verificação de performance em produção.
