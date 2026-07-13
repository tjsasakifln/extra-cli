---
epic: EPIC-MASTER-B2G-READINESS
story_id: FIX-TRANSACTION
title: "ROLLBACK apos statement timeout e isolamento de transacoes"
status: ready
priority: P0
effort: M
agent: @dev
depends_on: []
---

# Story FIX-TRANSACTION: ROLLBACK apos Statement Timeout e Isolamento de Transacoes

## Problem Statement

Em `consulting_readiness.py`, as metricas comerciais apresentam falha em cascata:

```
contract_total_value → ERROR: "canceling statement due to statement timeout"
desagio              → ERROR: "current transaction is aborted, commands ignored until end of transaction block"
relicitacao_probability → ERROR: "current transaction is aborted, commands ignored until end of transaction block"
win_rate             → "manual" (nao calculado)
```

**Root cause:** `consulting_readiness.py` usa `conn.autocommit = True`, mas apos um statement timeout, o PostgreSQL rejeita qualquer comando subsequente na MESMA conexao ate que um `ROLLBACK` explicito seja emitido. Nenhum `ROLLBACK` e executado no codigo atual. As queries 2 e 3 herdam a transacao abortada da query 1.

**Isso viola a Regra Nao-Negociavel #7 — "Isolar transacoes, rollback correto, otimizar indices."**

**Consequencias adicionais:**
- Indices ausentes: `pncp_supplier_contracts` sem FK indexada para `sc_public_entities`
- Sem timeout configuravel por query — todas usam o timeout default do banco
- Se uma query falha, todas as subsequentes falham, gerando manifesto com metricas vazias

## Acceptance Criteria

- [ ] **AC1: ROLLBACK explicito apos excecao de banco** — Apos qualquer excecao de banco (statement timeout, connection error, etc.), `conn.rollback()` e emitido antes de qualquer operacao subsequente na mesma conexao
- [ ] **AC2: Isolamento por savepoint** — Cada query de metrica comercial opera em seu proprio savepoint (ou conexao separada). Se a query de contract_total_value falha, as queries de desagio, relicitacao_probability, e win_rate continuam executando.
- [ ] **AC3: Timeout configuravel por query** — Cada query de metrica aceita um parametro `timeout_seconds` opcional. O timeout e aplicado via `SET statement_timeout = N` antes da query.
- [ ] **AC4: Indice para contract_total_value** — Criar indice na tabela `pncp_supplier_contracts` para acelerar a query que causa timeout (FK indexada em `entity_id`, ou indice composto nas colunas de agrupamento). Query otimizada: `EXPLAIN ANALYZE` mostra index scan, nao sequential scan.
- [ ] **AC5: Teste de recuperacao apos timeout** — Teste que simula um statement timeout e verifica que as queries subsequentes na mesma conexao executam com sucesso apos ROLLBACK. Implementado via `pg_sleep()` ou similar.
- [ ] **AC6: Logging de erros** — Cada timeout ou excecao de banco e logada com nıvel WARNING, incluindo: nome da metrica afetada, duracao da query, stack trace resumido.
- [ ] **AC7: Manifesto resılience** — Apos falha de uma metrica, as demais metricas continuam a ser calculadas e reportadas. A metrica falha aparece como `null` com campo `error` descritivo (nao como `ERROR: "current transaction is aborted..."`).
- [ ] **AC8: Ruff check** — `ruff check scripts/coverage_truth/consulting_readiness.py` retorna 0 erros

## Technical Design

### Estrategia de transacao

```python
import psycopg2
from psycopg2 import sql
from contextlib import contextmanager


@contextmanager
def metrica_transaction(conn, metrica_nome: str, timeout_seconds: int = 30):
    """
    Context manager que isola cada metrica em seu proprio savepoint.
    Garante ROLLBACK apos qualquer erro e timeout configuravel.
    """
    try:
        with conn.cursor() as cur:
            cur.execute(f"SAVEPOINT sp_{metrica_nome}")
            cur.execute(f"SET LOCAL statement_timeout = {timeout_seconds * 1000}")
        yield conn
        conn.commit()
    except (psycopg2.errors.QueryCanceled, psycopg2.errors.DeadlockDetected,
            psycopg2.OperationalError, psycopg2.DatabaseError) as e:
        conn.rollback()
        logger.warning(
            "Metrica '%s' falhou: %s (timeout=%ds)",
            metrica_nome, str(e), timeout_seconds
        )
        return None  # Metrica falha, mas nao aborta as outras
```

### Uso no codigo de metricas

```python
# Antes: transacao compartilhada sem rollback
contract_total_value = _calc_contract_total_value(conn)
desagio = _calc_desagio(conn)            # Falha se anterior timeout
relicitacao = _calc_relicitacao(conn)    # Falha se anterior timeout

# Depois: cada metrica isolada
with metrica_transaction(conn, "contract_total_value", timeout_seconds=60):
    contract_total_value = _calc_contract_total_value(conn)

with metrica_transaction(conn, "desagio", timeout_seconds=30):
    desagio = _calc_desagio(conn)

with metrica_transaction(conn, "relicitacao_probability", timeout_seconds=30):
    relicitacao = _calc_relicitacao(conn)
```

### Indice a criar

```sql
CREATE INDEX IF NOT EXISTS idx_pncp_supplier_contracts_entity_id
    ON pncp_supplier_contracts (entity_id);

-- Indice composto se a query de contract_total_value usa mais colunas:
-- CREATE INDEX IF NOT EXISTS idx_pncp_contracts_value_entity
--     ON pncp_supplier_contracts (entity_id, valor_total);
```

### Modificacoes em `consulting_readiness.py`

1. Adicionar `metrica_transaction()` context manager
2. Envolver cada metrica (contract_total_value, desagio, relicitacao_probability, win_rate) no context manager
3. Adicionar logging estruturado (logger ja existente ou criar)
4. Modificar `_calc_contract_total_value()` para usar `SET LOCAL statement_timeout`
5. Estrutura de retorno: metrica com erro retorna `{"value": None, "error": "descricao", "timeout_seconds": N}`

### Formatacao do manifesto para metricas com erro

```json
{
  "commercial_metrics": {
    "contract_total_value": {"value": null, "error": "Query cancelled due to statement timeout after 60s", "timeout_seconds": 60},
    "desagio": {"value": 0.12, "error": null, "timeout_seconds": 30},
    "relicitacao_probability": {"value": 0.45, "error": null, "timeout_seconds": 30},
    "win_rate": {"value": null, "error": "Requires proposal_tracking — not implemented", "status": "manual"}
  }
}
```

### Arquivos a modificar

- `scripts/coverage_truth/consulting_readiness.py` — Correcao principal

### Arquivos a criar

- Nenhum (modificacao em arquivo existente)

### Testes

| Teste | Descricao |
|-------|-----------|
| `test_timeout_recovery` | Simula timeout via `pg_sleep(999)` com timeout curto; verifica ROLLBACK e que queries subsequentes executam |
| `test_metrica_isolation` | Uma metrica que falha nao impede as demais de executar |
| `test_metrica_timeout_config` | Timeout personalizado por metrica e respeitado |
| `test_no_aborted_transaction_cascade` | Apos erro, proxima query nao recebe "current transaction is aborted" |
| `test_index_effectiveness` | `EXPLAIN ANALYZE` da query otimizada mostra index scan |
| `test_logging_on_error` | Erro de banco gera registro no log com nivel WARNING |
| `test_manifest_error_format` | Metrica com erro tem formato `{"value": null, "error": "..."}` |

## File List

- **MODIFY** `scripts/coverage_truth/consulting_readiness.py`

## Dependencies

- Nenhuma — independente de FIX-UNIVERSE e FIX-MANIFEST
- Pode ser implementada em paralelo

## Security Considerations

- Statement timeout evita que queries runaway consumam recursos do banco indefinidamente
- Indices melhoram performance geral do banco sem impacto de seguranca
- Sem autenticacao adicional

## Tests

Implementar em um novo arquivo `tests/test_consulting_readiness_transactions.py` ou adicionar ao arquivo de testes existente:
- Simulacao de timeout via `psycopg2.extensions.QueryCanceled` mock ou `pg_sleep`
- Verificacao de rollback via query de estado da transacao (`SELECT * FROM pg_prepared_xacts` ou `SELECT pg_current_xact_id_if_assigned()`)
- Logging verificado via `caplog` do pytest

## Definition of Done

- [ ] Codigo implementado (AC1-AC4)
- [ ] ruff check passa em scripts/coverage_truth/consulting_readiness.py
- [ ] mypy passa (scoped) em scripts/coverage_truth/consulting_readiness.py
- [ ] Testes unitarios passam (com mock de timeout)
- [ ] Testes de integracao passam (contra banco real com timeout reduzido)
- [ ] Manifesto gerado mostra metricas isoladas (falha em 1 nao afeta as outras)
- [ ] QA gate PASS
