---
name: qa-fix-transaction-aborted
description: "Fix transaction aborted cascade em commercial_metrics no consulting_readiness.py — _safe_metric_query com per-query timeout e rollback"
metadata:
  type: project
---

# Fix: Transaction Aborted Cascade in consulting_readiness.py

## Problema

Em `scripts/consulting_readiness.py`, a secao `commercial_metrics` usava `_query()` sem isolamento de transacao. Quando `contract_total_value` atingia statement timeout (30s+ em `pncp_supplier_contracts` com 3.7M rows sem indice), o PostgreSQL entrava em estado `aborted`. As queries subsequentes (`desagio`, `relicitacao_probability`) falhavam com "current transaction is aborted, commands ignored until end of transaction block".

**Root cause:** `_query()` nao fazia `conn.rollback()` ao capturar `Exception`. Cada funcao `_compute_*_stats()` capturava o erro internamente e retornava um dict -- o `except` no caller (que tinha rollback) nunca era alcancado. A transacao abortada nunca era limpa.

## Correcao Aplicada

1. **`_safe_metric_query()`**: Nova funcao helper que:
   - Aceita `query_name`, `query`, `params`, `timeout` como parametros
   - Usa `SET LOCAL statement_timeout` para timeout por query
   - Usa `conn.cursor()` como context manager (`with`)
   - Em caso de excecao: chama `conn.rollback()` e retorna `None`

2. **Cada `_compute_*_stats()` refatorada**:
   - `_compute_contract_value_aggregation()` usa `_safe_metric_query()` com timeout=30s
   - `_compute_desagio_stats()` usa `_safe_metric_query()` com timeout=30s
   - `_compute_relicitacao_stats()` usa `_safe_metric_query()` com timeout=30s
   - Cada uma trata `rows is None` (query falhou) como erro
   - Cada except handler faz `conn.rollback()` adicional como safety

3. **Removido** o `SET statement_timeout = '15s'` global na conexao comercial (redundante com `SET LOCAL` por query)

4. **TODO adicionado**: `pncp_supplier_contracts(orgao_cnpj)` index para prevenir full table scans

5. **`tests/conftest.py`**: Criado com autouse fixture que faz patch de `psycopg2.connect` para todos os testes exceto `TestPostgreSQLFailClosed`, eliminando dependencia de DB real.

## Arquivos modificados

- `/mnt/d/extra consultoria/scripts/consulting_readiness.py` -- core fix
- `/mnt/d/extra consultoria/tests/test_consulting_readiness.py` -- 4 novos testes
- `/mnt/d/extra consultoria/tests/conftest.py` -- criado

## Novos testes

| Teste | O que valida |
|-------|-------------|
| `test_safe_metric_query_rollback_on_error` | Rollback chamado apos excecao |
| `test_safe_metric_query_success_returns_dicts` | Retorno correto com dicts |
| `test_safe_metric_query_sets_per_query_timeout` | SET LOCAL chamado com timeout |
| `test_commercial_metrics_independent_after_timeout` | Timeout em metrica 1 NAO afeta metrica 2 e 3 |

**Why:** O bug foi diagnosticado na auditoria Fase 0 (fase0-audit-2026-07-12.md secao 4) como violacao da Regra #7 (isolar transacoes, rollback correto).
