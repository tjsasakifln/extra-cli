# Auditoria Retroativa — Story 1.3: Universe Authority

**Data:** 2026-07-13
**Auditor:** AIOX Master (coordenação)

---

## Veredito: FAIL

## Confiança: Alta

---

## Resumo Executivo

**Story 1.3 é a mais problemática das cinco.** A infraestrutura core (tabelas de snapshot, bloqueio seed change, .env files) foi implementada, mas a migração das queries analíticas — o objetivo central da story — está grosseiramente incompleta. ~50 arquivos ainda usam `WHERE raio_200km IS TRUE`. 4 das 12 tasks estão com checkboxes desmarcados. O QA identificou 5 issues mas o PO fechou a story mesmo assim, aceitando todo o escopo pendente como "follow-up".

**Esta story NÃO deveria ter sido fechada.** O estado "Done" é falso. A implementação está talvez 50-60% completa.

---

## Contrato Reconstruído

### Objetivo Declarado
Tornar a planilha a única autoridade do universo de entes, com snapshots auditáveis e bloqueio por seed change.

### Critérios de Aceite Violados

| AC | Descrição | Status |
|----|-----------|--------|
| AC1 | Zero `WHERE raio_200km IS TRUE` em queries analíticas | **VIOLADO** — ~50 arquivos pendentes |
| AC2 | universe_run_id em TODAS as queries de sc_public_entities | **VIOLADO** — contract_intel/cli.py e local_datalake.py pendentes |
| AC3 | 1.093 entes incluídos, 992 excluídos, 0 unresolved | **NÃO VERIFICÁVEL** — snapshot inicial não gerado (task 5) |
| AC4 | Ledger de divergência funcional | **NÃO VERIFICÁVEL** — código existe mas não executado (task 6) |
| AC5 | Bloqueio seed change: exit code 42 | ✅ Implementado (task 9) |
| AC6 | Raiz 00394494 resolvida | ✅ Documentado (task 3) |
| AC7 | .env files separados por ambiente | ✅ Implementado (task 10) |
| AC8 | Subprocess JSON output (TD-005) | ✅ Implementado (task 11) |

---

## Tasks Não Concluídas

| Task | Status | Impacto |
|------|--------|---------|
| 5. Gerar snapshot inicial da seed | ❌ Não feito | Sem baseline de universo |
| 6. Criar ledger de divergência | ❌ Não feito | Sem detecção de drift |
| 7. Migrar queries para universe_run_id | ⚠️ Parcial | ~50 arquivos com raio_200km, contract_intel pendente |
| 8. Substituir WHERE raio_200km | ⚠️ Parcial | Apenas key queries atualizadas |

---

## Commits e Arquivos

**Commit:** `d2ff075`

### Arquivos Criados (9)
- `db/migrations/037_target_universe_snapshot.sql`
- `db/migrations/038_target_universe_active_view.sql`
- `scripts/universe_tools.py` (180 linhas)
- `scripts/lib/universe_query.py` (18 linhas)
- `.env.dev`, `.env.staging`, `.env.production`
- `docs/decisions/universe-00394494-duplicate-root-resolution.md`
- `docs/operations/universe-snapshot-runbook.md`

### Arquivos Modificados (5)
- `scripts/consulting_readiness.py`
- `scripts/intel_pipeline.py`
- `scripts/opportunity_intel/manifest.py`
- `scripts/opportunity_intel/backfill.py`
- `scripts/reports/panorama.py`

---

## Critérios de Aceite e Rastreabilidade

| Critério | Código | Teste | Status |
|----------|--------|-------|--------|
| AC1: Zero raio_200km | ~50 arquivos não migrados | grep apenas | **NOT-COVERED** |
| AC2: universe_run_id queries | manifest.py, backfill.py, panorama.py (parcial) | Sem testes | **PARTIALLY-COVERED** |
| AC3: 1.093 incluídos | universe_tools.py snapshot | Sem execução | **NOT-COVERED** |
| AC4: 0 unresolved | universe_tools.py | Sem execução | **NOT-COVERED** |
| AC5: Bloqueio seed change | universe_tools.py check_seed() | Sem testes | **NOT-COVERED** |
| AC6: Raiz 00394494 | Decisão documentada | N/A | COVERED |
| AC7: Ambientes separados | .env.dev/staging/production | Inspeção | COVERED |
| AC8: Subprocess JSON | intel_pipeline.py --pipeline-json | Sem testes | PARTIALLY-COVERED |

---

## Cobertura de Testes

| Módulo | Linhas | Cobertura |
|--------|--------|-----------|
| universe_tools.py | 180 | **0%** |
| universe_query.py | 18 | **0%** |
| universe.py | ? | 34% |

**DoD exigia >= 80% em universe.py. Não atingido.**

---

## Segurança

- ✅ Queries parametrizadas
- ✅ Sem hardcoded secrets
- ⚠️ .env.production versionado no commit d2ff075 (contém DATABASE_URL?)

---

## Arquitetura e Causa Raiz

**Parecer:** SYMPTOM-PATCHED

- **Causa raiz:** Múltiplas fontes de verdade para o universo de entes
- **O que foi feito:** Infraestrutura de snapshot criada, migrations aplicadas
- **O que NÃO foi feito:** A migração real das queries — ~50 arquivos ainda usam o filtro antigo
- **Efeito:** O sistema continua operando com a lógica antiga. A nova infraestrutura existe mas não é usada pela maioria das queries.

**A story entregou a Fundação mas não a Casa.**

---

## Compatibilidade com Reversa

*(Preenchido pelo agente architecture-reversa)*

---

## Dívida Técnica

| ID | Descrição | Severidade | Origem |
|----|-----------|------------|--------|
| REQ-001 | ~50 arquivos com raio_200km não migrados | **HIGH** | INTRODUCED-BY-STORY |
| REQ-002 | contract_intel/cli.py e local_datalake.py pendentes | MEDIUM | INTRODUCED-BY-STORY |
| TST-001 | Zero testes para universe_tools.py (180 linhas) | MEDIUM | INTRODUCED-BY-STORY |
| TST-002 | universe.py cobertura 34% (meta 80%) | MEDIUM | INTRODUCED-BY-STORY |
| MNT-001 | ruff format pendente | LOW | INTRODUCED-BY-STORY |
| MNT-002 | E501 line too long (146 > 120) | LOW | INTRODUCED-BY-STORY |

---

## Achados

| ID | Severidade | Origem | Descrição | Correção Sugerida |
|----|-----------|--------|-----------|-------------------|
| A1.3-01 | **CRITICAL** | INTRODUCED-BY-STORY | ~50 arquivos ainda usam WHERE raio_200km — objetivo central da story não atingido | Nova story para completar migração de queries |
| A1.3-02 | HIGH | INTRODUCED-BY-STORY | Snapshot inicial nunca gerado — sem baseline de universo | Gerar snapshot imediatamente |
| A1.3-03 | HIGH | INTRODUCED-BY-STORY | Ledger de divergência nunca executado | Executar contra DB real |
| A1.3-04 | MEDIUM | INTRODUCED-BY-STORY | 0% cobertura de testes em universe_tools.py (180 linhas) | Adicionar testes unitários |
| A1.3-05 | MEDIUM | INTRODUCED-BY-STORY | PO fechou story com 4/12 tasks não concluídas | Reabrir story ou criar follow-ups |
| A1.3-06 | MEDIUM | INTRODUCED-BY-STORY | .env.production versionado com secrets? | Verificar conteúdo, adicionar ao .gitignore se necessário |

---

## Trabalho Necessário

1. **P0:** Migrar ~50 queries restantes de raio_200km → universe_run_id
2. **P0:** Gerar snapshot inicial da seed atual
3. **P1:** Executar ledger de divergência contra DB real
4. **P1:** Adicionar testes para universe_tools.py (mínimo 80% cobertura)
5. **P2:** Completar contract_intel/cli.py e local_datalake.py
6. **P2:** Executar ruff format

---

## Recomendação Final

**FAIL.** Story fechada prematuramente com ~50% de completude funcional. A infraestrutura core está correta, mas o objetivo central (migrar todas as queries para a nova fonte de verdade) não foi atingido. O PO不应该 ter fechado esta story com 4/12 tasks pendentes. Requer reabertura ou nova story de follow-up com escopo claro para completar a migração.
