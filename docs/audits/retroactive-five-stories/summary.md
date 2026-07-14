# Auditoria Retroativa — Relatório Consolidado das Cinco Stories

**Data:** 2026-07-13
**Auditoria coordenada por:** AIOX Master
**Commit alvo:** `d2ff075` — resolve 23 technical debts across 5 stories (Epic P0 complete)
**HEAD no momento da auditoria:** `173c569`

---

## 1. Vereditos Individuais

| # | Story | Veredito | Confiança | QA Original | Estado Real |
|---|-------|----------|-----------|-------------|-------------|
| 1.1 | Fix Critical Security | **CONCERNS** | Média | CONCERNS | Funcionalmente correto, operacionalmente incompleto |
| 1.2 | Unify Schema | **CONCERNS** | Média | CONCERNS | Schema sólido, 4 ACs sem validação real |
| 1.3 | Universe Authority | **FAIL** | Alta | CONCERNS | ~50% completo. Fechado prematuramente |
| 1.4 | Reconcile Open Tenders | **FAIL** | Alta | CONCERNS | Algoritmo central NÃO-FUNCIONAL |
| 1.5 | Coverage Model | **PASS** | Alta | PASS | Completo, testado, funcional |

---

## 2. Veredito Sistêmico: SYSTEM-FAIL

**O sistema como um todo NÃO está em estado coerente.** Duas stories (1.3, 1.4) têm falhas que impedem o funcionamento correto do conjunto:

1. **Story 1.4 (CRITICAL):** Algoritmo de reconciliação de snapshots é completamente não-funcional. A função `fn_record_snapshot_membership()` não existe no banco. O radar continua exportando 673 registros com apenas 34 válidos.

2. **Story 1.3 (CRITICAL):** ~50 arquivos ainda usam `WHERE raio_200km IS TRUE`. A migração para o novo modelo de universo está grosseiramente incompleta. O sistema opera com duas fontes de verdade conflitantes.

3. **Conflito arquitetural 1.2 ↔ 1.3:** As views canônicas da Story 1.2 expõem `within_200km` como coluna contratual estável. A Story 1.3 tenta eliminar `raio_200km` como fonte de verdade. As duas stories não foram coordenadas.

4. **Nenhuma story tem state file:** Impossível validar gates, QA, ou autorizar push via hooks.

---

## 3. Saúde Geral do Conjunto

| Dimensão | Avaliação |
|----------|-----------|
| **Funcionalidade** | 🔴 2/5 stories com bugs críticos ou incompletas |
| **Segurança** | 🟡 Senha no histórico Git, 17+ scripts com senha em fallback |
| **Testes** | 🟡 Cobertura irregular: 97/97 (1.5) vs 0% (1.3 universe_tools) |
| **Arquitetura** | 🟡 Conflito entre stories 1.2 e 1.3 não resolvido |
| **Processo** | 🔴 Violações generalizadas: state files ausentes, QA header incorreto, DoD ignorado |
| **Dívida Técnica** | 🔴 23 débitos alegados como resolvidos, mas ~50 queries raio_200km e algoritmo de reconciliação quebrado |

---

## 4. Achados Críticos e Altos

### CRITICAL (2)

| ID | Story | Descrição |
|----|-------|-----------|
| C-01 | 1.4 | `fn_record_snapshot_membership()` não existe — reconciliação é no-op |
| C-02 | 1.4 | Mismatch camelCase/snake_case quebra lookup de membership |

### HIGH (8)

| ID | Story | Descrição |
|----|-------|-----------|
| H-01 | 1.1 | Senha no histórico Git (BFG não executado) |
| H-02 | 1.1 | Senha não rotacionada após migração |
| H-03 | 1.1 | 17+ scripts com `smartlic_local` em DEFAULT_DSN fallback |
| H-04 | 1.3 | ~50 arquivos ainda usam `WHERE raio_200km IS TRUE` |
| H-05 | 1.3 | Snapshot inicial nunca gerado — sem baseline de universo |
| H-06 | 1.3 | Ledger de divergência nunca executado |
| H-07 | 1.4 | Erros de reconciliação engolidos silenciosamente |
| H-08 | 1.2 | @dev como Quality Gate — violação de segregação |

---

## 5. Gates Técnicos

**Relatório completo:** `quality-gates-results.md`

| Gate | Veredito | Detalhe |
|------|----------|---------|
| **LINT** (ruff check) | **FAIL** | 2.779 erros (S101 assert, S110 bare-except, F841 unused) |
| **FORMAT** (ruff format) | **FAIL** | 49 arquivos seriam reformatados (18.5% do codebase) |
| **SECURITY** (ruff S) | **CONCERNS** | 177 achados. 1 vetor SQL injection (B608) em `coverage_gaps.py:58` |
| **BANDIT** | **CONCERNS** | 177 issues (51 Medium, 126 Low) |
| **UNIT TESTS** | **FAIL** | 86 failed + 17 errors + 1.264 passed (93.7% pass rate) |
| **MIGRATION TESTS** | **PASS** | 14/14 passaram |
| **IMPORT CHECKS** | **PASS** | 4/4 módulos críticos importam sem erro |

### Causas dos 86 Testes Quebrados

| Causa | Testes Afetados | Story |
|-------|-----------------|-------|
| `TargetUniverse` com interface desatualizada (`total_resolved`) | ~15 | 1.3 |
| Remoção de API pública em `sc_compras_crawler` | 27 | 1.1/1.3 |
| Schema drift (`source_active` coluna ausente) | ~10 | 1.4 |
| Hash SHA-256 vs MD5 em teste de fingerprint | ~3 | 1.2 |
| Dependência de banco indisponível (TEST_DATALAKE_DSN) | 20+ | várias |
| Diversos (mocks, imports, asserções) | ~11 | várias |

### Risco de Segurança Ativo

- **B608 (MEDIUM):** `scripts/reports/coverage_gaps.py:58` — construção de query SQL via concatenação de string. **Vetor de SQL injection não mitigado.**
- **S110 (177 ocorrências):** `try-except-pass` em `scripts/supabase_client.py` e `scripts/validate-report-data.py` — erros engolidos silenciosamente

---

## 6. Banco de Dados: DB-CONCERNS

**Auditoria completa em:** `database-audit.md`

### Achados Críticos de Banco

| ID | Severidade | Descrição |
|----|-----------|-----------|
| C-01 | **CRITICAL** | 3 FKs estruturalmente quebradas. `fk_bids_orgao_entity` referencia `sc_public_entities(cnpj_8)` (8 dígitos) mas `pncp_raw_bids.orgao_cnpj` contém CNPJ de 14 dígitos. Nenhum registro matcha. FK ineficaz por design. |
| C-02 | **CRITICAL** | Gap de baseline. `db/current-schema.sql` foi gerado ANTES das migrations 037-040. Schema real do banco é desconhecido. View `v_opportunity_open` ainda usa definição antiga (sem `source_active = TRUE`). |

### Achados HIGH de Banco

| ID | Descrição |
|----|-----------|
| H-01 | 3 FKs criadas como NOT VALID — `VALIDATE CONSTRAINT` nunca executado |
| H-02 | Migration 039: `ALTER TABLE opportunity_intel` sem `LOCK_TIMEOUT` |
| H-03 | Migration 040: 11 `ALTER TABLE coverage_evidence` sem `LOCK_TIMEOUT` |
| H-04 | Valor `running` do enum `evidence_state` não existe na baseline |

### REQ-001 (Story 1.4): FALSO POSITIVO

O bug `jsonb_build_object(jsonb_build_object(...))` reportado pelo QA era um **falso positivo**. O padrão `jsonb_build_array(jsonb_build_object(...))` está correto e consistente. O QA pode ter lido a versão anterior à correção.

### Métricas

- 12 migrations auditadas (11 novas + 1 modificada)
- 7 tabelas criadas, 17 views, 1 materialized view, 8 funções, 3 triggers
- Migrations 030-036: aplicadas e na baseline ✅
- Migrations 037-040: **NÃO aplicadas** — gap de deployment ❌
- Reversa docs desatualizadas: `erd-complete.md`, `data-dictionary.md`, `db/design.md`

---

## 7. Compatibilidade Reversa

| Story | Regras Preservadas | Regras Alteradas | Regras Quebradas | Specs Desatualizadas |
|-------|-------------------|------------------|------------------|---------------------|
| 1.1 | Todas | Nenhuma | Nenhuma | Nenhuma |
| 1.2 | Schema legado arquivado | Views podem divergir do schema antigo | Nenhuma | data-dictionary.md |
| 1.3 | Raio_200km ainda em uso | Transição para snapshot universe | ~50 queries não migradas | architecture.md (DB section) |
| 1.4 | Dados históricos preservados | Inativação adicionada | Algoritmo não-funcional | Nenhuma |
| 1.5 | Comportamento legado mantido | Registry expandido | Nenhuma | state-machines.md (MS7: 10 vs 14 estados) |

**12 artefatos Reversa desatualizados.** Re-extração parcial recomendada (prioridade ALTA para state-machines.md, architecture.md, domain.md).

---

## 8. Dívida Técnica Introduzida

| ID | Story | Descrição | Severidade |
|----|-------|-----------|------------|
| NEW-01 | 1.1 | BFG cleanup pendente | HIGH |
| NEW-02 | 1.1 | sys.path.insert workaround permanente | MEDIUM |
| NEW-03 | 1.2 | AC #10 (perf) não benchmarkeado | MEDIUM |
| NEW-04 | 1.2 | Fresh install/upgrade não testados em DB real | MEDIUM |
| NEW-05 | 1.3 | ~50 arquivos com raio_200km | HIGH |
| NEW-06 | 1.3 | 0% cobertura universe_tools.py | MEDIUM |
| NEW-07 | 1.4 | fn_record_snapshot_membership ausente | CRITICAL |
| NEW-08 | 1.4 | Erros de reconciliação engolidos | HIGH |
| NEW-09 | 1.4 | Mismatch camelCase/snake_case | CRITICAL |
| NEW-10 | 1.5 | RUNNING state sem uso | LOW |

---

## 9. Ordem Recomendada de Remediação

```
1. Story 1.4 (P0) — Corrigir reconciliação (fn_record_snapshot_membership + field names)
2. Story 1.3 (P0) — Migrar ~50 queries raio_200km → universe_run_id
3. Story 1.1 (P0) — BFG repo-cleaner + rotação de senha
4. Story 1.3 (P1) — Gerar snapshot inicial + executar ledger
5. Story 1.1 (P1) — Migrar 17+ scripts com DEFAULT_DSN hardcoded
6. Story 1.2 (P2) — Benchmark AC #10 + testar fresh install em DB real
7. Story 1.3 (P2) — Adicionar testes universe_tools.py
8. Reversa (P2) — Re-extrair state-machines.md, architecture.md, domain.md
9. Processo (P1) — Criar state files para stories 1.1-1.5
```

---

## 10. Stories Que Podem Permanecer Fechadas

| Story | Pode Ficar Fechada? | Condição |
|-------|---------------------|----------|
| **1.5** | ✅ Sim | Nenhuma correção necessária |
| **1.2** | ✅ Sim (com ressalvas) | Criar follow-up para AC #10 benchmark |
| **1.1** | ⚠️ Não até BFG | Reabrir até BFG + rotação concluídos |
| **1.4** | ❌ Não | Reabrir — CRITICAL não resolvido |
| **1.3** | ❌ Não | Reabrir — ~50% incompleto |

---

## 11. Novas Stories Necessárias

| ID Proposto | Título | Prioridade | Escopo |
|-------------|--------|------------|--------|
| FIX-1.4-01 | Deploy fn_record_snapshot_membership + fix reconciliation | P0 | Criar função no banco, corrigir field names, propagar erros |
| FIX-1.3-01 | Completar migração raio_200km → universe_run_id | P0 | Migrar ~50 queries restantes |
| FIX-1.3-02 | Gerar snapshot inicial e ledger de divergência | P1 | Executar universe_tools.py contra DB real |
| FIX-1.1-01 | BFG repo-cleaner + rotação de senha | P0 | Executar BFG, rotacionar senha PostgreSQL |
| FIX-1.1-02 | Centralizar DSN — eliminar 17+ hardcoded passwords | P1 | Todos os scripts usarem config.settings |
| FIX-1.3-03 | Testes para universe_tools.py | P2 | 80% cobertura mínima |
| REVERSA-01 | Re-extração pós-stories | P2 | state-machines.md, architecture.md, domain.md |
| PROCESS-01 | Criar state files retroativos para stories 1.1-1.5 | P1 | State files em .aiox/state/stories/ |

---

## 12. Segurança para Publicação

**❌ NÃO SEGURO PUBLICAR.**

Motivos:
1. Senha `smartlic_local` no histórico Git (BFG não executado)
2. Algoritmo de reconciliação não-funcional (Story 1.4)
3. ~50 queries ainda usando fonte de verdade antiga (Story 1.3)
4. Nenhum state file para validação de hooks
5. 17+ scripts com senha em DEFAULT_DSN fallback

---

## 13. Migração para o Protocolo Endurecido

Para cada story, o que seria necessário para atender o protocolo atual:

| Story | State File | Risk Level | PO Validated | QA Verdict | PO Closed | reviewed_commit | status |
|-------|-----------|------------|-------------|------------|-----------|-----------------|--------|
| 1.1 | Criar | HIGH-RISK | Sim (10/10) | CONCERNS | Sim | Definir após fixes | InReview (não Done) |
| 1.2 | Criar | HIGH-RISK | Sim (10/10) | CONCERNS | Sim | Definir após fixes | InReview (não Done) |
| 1.3 | Criar | STANDARD | Sim (10/10) | CONCERNS | ❌ Prematuro | N/A | InProgress (não Done) |
| 1.4 | Criar | HIGH-RISK | Sim (10/10) | CONCERNS | ❌ Prematuro | N/A | InProgress (não Done) |
| 1.5 | Criar | STANDARD | Sim (10/10) | PASS | Sim | `d2ff075` | Done ✅ |

---

## 14. Resumo Executivo

As cinco stories foram implementadas em um único commit (`d2ff075`) durante a transição do protocolo AIOX, antes da implantação completa de state files, hooks de enforcement e gates estruturados.

**Uma story está genuinamente completa (1.5).** Duas estão funcionalmente corretas mas operacionalmente incompletas (1.1, 1.2). Duas estão quebradas ou grosseiramente incompletas (1.3, 1.4).

O sistema **não está seguro para publicação** e **não está seguro para continuar evoluindo** sem antes corrigir os achados críticos, especialmente:
- O algoritmo de reconciliação quebrado (Story 1.4)
- As ~50 queries não migradas (Story 1.3)
- As credenciais no histórico Git (Story 1.1)

**Recomendação:** Não publicar. Corrigir na ordem: 1.4 → 1.3 → 1.1 → 1.2. Story 1.5 pode ser publicada independentemente.

---

## 15. Decisão Pendente

Aguardando decisão do operador sobre:
1. Prosseguir com correções imediatamente?
2. Quais stories reabrir?
3. Ordem de remediação aprovada?
4. Autorização para criar state files retroativos?

**Nenhuma correção funcional será implementada sem decisão explícita.**
