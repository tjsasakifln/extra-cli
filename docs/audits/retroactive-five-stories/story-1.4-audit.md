# Auditoria Retroativa — Story 1.4: Reconcile Open Tenders

**Data:** 2026-07-13
**Auditor:** AIOX Master (coordenação) + Code Security Audit Agent

---

## Veredito: FAIL

## Confiança: Alta

---

## Resumo Executivo

**A Story 1.4 contém um bug CRÍTICO que torna o algoritmo de reconciliação de snapshots completamente não-funcional.** A função `fn_record_snapshot_membership()` chamada por `reconciliation.py:299` não existe em nenhuma migration do banco de dados. Adicionalmente, há um mismatch de nomes de campos (camelCase da API vs snake_case esperado) que quebraria o lookup mesmo se a função existisse. Os erros são capturados silenciosamente em `pncp_audit.py:236` e o pipeline continua como se nada tivesse acontecido.

**O problema central da story (gap 34 vs 673) não foi verificado** porque a Task 8 (executar contra snapshot real) nunca foi executada.

---

## Achado CRÍTICO: Algoritmo de Reconciliação Não-Funcional

### C-01: fn_record_snapshot_membership() não existe

**Arquivo:** `scripts/opportunity_intel/reconciliation.py:299`
```python
cursor.execute(
    "SELECT fn_record_snapshot_membership(%s, %s, %s::jsonb)",
    (run_id, source, json.dumps(payload, default=str)),
)
```

**Problema:** A função `fn_record_snapshot_membership` é chamada mas nenhuma migration a cria. A migration `031_source_snapshot_reconciliation.sql` existe mas não contém esta função. O `KNOWN_FUNCTIONS` em `audit_sql_references.py` também não a lista.

**Consequência:** `record_memberships()` sempre falha com erro de psycopg2. `memberships_recorded` sempre retorna 0. A inativação de registros nunca dispara. A reativação nunca dispara. **Todas as 7 regras do algoritmo de reconciliação são inoperantes.**

### H-05: Erros Engolidos Silenciosamente

**Arquivo:** `scripts/opportunity_intel/pncp_audit.py:235-241`
```python
except Exception as recon_err:
    _logger.error(
        "Snapshot reconciliation failed for run %d: %s",
        db_run_id, recon_err, exc_info=True,
    )
```
O erro é logado mas o `PncpRunOutcome` é retornado como sucesso. O `radar.py:218` verifica `source_outcome is None` e `scope_complete`, mas nunca verifica se a reconciliação funcionou.

### L-11: Mismatch de Nomes de Campos

**Arquivo:** `scripts/opportunity_intel/reconciliation.py:287-289`
```python
source_record_id = rec.get("numero_controle_pncp") or rec.get("source_id") or rec.get("id") or ""
```
Registros da API PNCP usam camelCase (`numeroControlePNCP`), mas o código busca snake_case (`numero_controle_pncp`). O fallback para `source_id` → `id` → string vazia resulta em todos os registros tendo a mesma chave vazia.

---

## Contrato Reconstruído

### Problema Original
Radar exportava 673 registros mas apenas 34 foram confirmados no último snapshot PNCP completo (gap de 639 falsos ativos).

### Escopo Previsto vs Implementado

| Previsto | Status |
|----------|--------|
| Colunas de tracking em opportunity_intel | ✅ Migration 039 |
| Tabela source_snapshot_membership | ✅ Migration 039 |
| Algoritmo de reconciliação (7 regras) | ❌ **NÃO-FUNCIONAL** (C-01) |
| Proteção partial/failed | ✅ Lógica no Python (mas nunca executa) |
| Modificar radar (source_active=TRUE) | ✅ radar.py |
| SLA verificação (last_status_verified_at) | ✅ Implementado |
| URL oficial obrigatória | ✅ Já existia em scoring.py |
| 7 cenários de teste | ✅ Criados (requerem DB) |
| Executar contra snapshot real (gap 34 vs 673) | ❌ Task 8 não executada |
| TD-002 (unificar DEFAULT_DSN) | ✅ crawler_base.py, freshness_gate.py |
| TD-006 (ANSI color codes) | ✅ Substituídos por terminal.py |

---

## Commits e Arquivos

**Commit:** `d2ff075`

### Criados (4)
- `db/migrations/039_source_snapshot_tracking.sql`
- `scripts/opportunity_intel/reconciliation.py` ← **CÓDIGO NÃO-FUNCIONAL**
- `scripts/lib/terminal.py`
- `tests/test_snapshot_reconciliation.py`

### Modificados (8)
- `scripts/opportunity_intel/radar.py`
- `scripts/opportunity_intel/crawler_base.py`
- `scripts/opportunity_intel/pncp_audit.py` ← **ENGOLIMENTO DE ERROS**
- `scripts/freshness_gate.py`
- `scripts/intel-validate.py`
- `scripts/intel_validate.py`
- `scripts/intel_pipeline.py`
- `pyproject.toml`

---

## Critérios de Aceite e Rastreabilidade

| AC | Status | Evidência |
|----|--------|-----------|
| AC #1: active_snapshot_integrity=100% | **NOT-COVERED** | Algoritmo não-funcional (C-01) |
| AC #2: Radar sem ausentes do snapshot | **NOT-COVERED** | Filtro source_active existe mas reconciliação não popula |
| AC #3: Artefato de run (ativados/atualizados/inativados/reativados) | **NOT-COVERED** | Contadores no código mas reconciliação nunca completa |
| AC #4: Gap 34 vs 673 resolvido | **NOT-COVERED** | Task 8 nunca executada |
| AC #5: Quantidade = snapshot atual | **NOT-COVERED** | Dependente de C-01 |
| AC #6: Registros não vistos → inativos | **NOT-COVERED** | Lógica existe mas nunca dispara |
| TD-002 | COVERED | DEFAULT_DSN unificado |
| TD-006 | COVERED | ANSI codes removidos |

---

## Violações Processuais

- **Transição de status violada:** Change Log: "InProgress → Done (dev did not advance to InReview)". @qa moveu de InProgress direto para Done.
- **State file ausente**
- **Task 8 não concluída** mas story fechada
- **REQ-001 (jsonb_build_object bug)** corrigido antes do fechamento — processo OK

---

## Achados

| ID | Severidade | Origem | Descrição |
|----|-----------|--------|-----------|
| A1.4-01 | **CRITICAL** | INTRODUCED-BY-STORY | `fn_record_snapshot_membership()` não existe — reconciliação é no-op |
| A1.4-02 | **CRITICAL** | INTRODUCED-BY-STORY | Mismatch camelCase/snake_case quebra lookup de membership |
| A1.4-03 | HIGH | INTRODUCED-BY-STORY | Erros de reconciliação engolidos em pncp_audit.py |
| A1.4-04 | MEDIUM | INTRODUCED-BY-STORY | Task 8 (execução real) pendente |
| A1.4-05 | MEDIUM | INTRODUCED-BY-STORY | Transição InProgress→Done sem InReview |
| A1.4-06 | LOW | INTRODUCED-BY-STORY | Testes requerem PostgreSQL (não executáveis em CI) |

---

## Recomendação Final

**FAIL.** Bug CRÍTICO torna a funcionalidade central da story (reconciliação de snapshots) completamente inoperante. A story precisa ser reaberta para:
1. Criar a função `fn_record_snapshot_membership` no banco
2. Corrigir o mismatch de nomes de campos (camelCase → snake_case)
3. Garantir que erros de reconciliação sejam propagados (não apenas logados)
4. Executar contra snapshot PNCP real para verificar o gap 34 vs 673
