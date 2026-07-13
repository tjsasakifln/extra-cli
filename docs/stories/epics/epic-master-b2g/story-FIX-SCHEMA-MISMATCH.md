---
epic: EPIC-MASTER-B2G-READINESS
story_id: FIX-SCHEMA-MISMATCH
title: "Alinhar codigo com schema real do banco de dados"
status: ready
priority: P0
effort: L
agent: @data-engineer
depends_on: []
---

# Story FIX-SCHEMA-MISMATCH: Alinhar Codigo com Schema Real do Banco de Dados

## Problem Statement

A auditoria Fase 0 revelou uma divergencia critica entre o schema que o codigo espera e o schema realmente existente no banco de dados PostgreSQL.

**Tabelas que o codigo referencia mas NAO existem (10):**

```
coverage_evidence, engineering_opportunities, entity_hierarchy,
opportunity_intel, opportunity_checkpoints, opportunity_runs,
opportunity_coverage, pncp_enrichment_cache, sc_municipalities,
sc_dados_abertos_backfill_log
```

**Colunas fantasmas em queries:**

| Query usa | Schema real tem |
|-----------|----------------|
| `ni_fornecedor` | `fornecedor_cnpj` |
| `valor_global` | `valor_total` |
| `data_assinatura` | `data_inicio` / `data_publicacao` |
| `numero_controle_pncp` | `contrato_id` |
| `situacao_compra` | (nao existe) |
| `unidade_nome` | (nao existe) |
| `link_sistema_origem` | (nao existe) |

**`search_datalake` function:** definida com 10 parametros no banco, mas chamada com 12-13 parametros no codigo Python.

**Migration 006-v3 (unified schema):** NUNCA aplicada em producao. Dual track de migrations: v1 (28 migrations) vs v2/v3 (7 migrations) — divergentes. Constraints `NOT VALID` nunca validadas (3 constraints).

**Isso viola a Regra Nao-Negociavel #11 — "Validar migration unificada em PostgreSQL vazio e upgrade."**

**Consequencias:**
- Queries que referenciam colunas inexistentes falham em runtime
- Migrations v3 nao aplicadas significam schema desatualizado
- Funcao `search_datalake` com assinatura incompativel quebra chamadas Python
- Impossivel garantir que o codigo funciona em producao

## Acceptance Criteria

- [ ] **AC1: Auditoria completa de gap schema-codigo** — Documento gerado listando TODAS as divergencias entre schema real e schema esperado por cada query no codigo. Formato: tabela com colunas `Modulo`, `Query/Arquivo`, `Coluna usada`, `Coluna real`, `Acão`.
- [ ] **AC2: Phantom columns mapeadas** — Para cada coluna fantasma (ex: `ni_fornecedor`, `valor_global`, `data_assinatura`, `numero_controle_pncp`, `situacao_compra`, `unidade_nome`, `link_sistema_origem`), uma de: (a) renomear no codigo para coluna real, (b) criar alias na view, (c) criar migration para adicionar coluna.
- [ ] **AC3: `search_datalake` function corrigida** — OU criar overload com 12 params no banco, OU ajustar TODAS as chamadas Python para 10 params. Ambos os lados devem ser consistentes.
- [ ] **AC4: Migration 006-v3 testada** — Migration executada em banco de testes vazio (create + migrate) E em copia do banco real (upgrade test). Resultados documentados: quais colunas/tabelas foram criadas, quais constraints foram validadas, quais conflitos surgiram.
- [ ] **AC5: Tabelas ausentes resolvidas** — Para cada uma das 10 tabelas nao-existentes: (a) criar migration para cria-la se necessaria, OU (b) remover referencia do codigo e adaptar query, OU (c) documentar como tech debt postergado com justificativa
- [ ] **AC6: Validacao de todas as queries do codigo** — Script que extrai TODAS as queries SQL do codigo Python e as executa contra o schema real (ou schema upgrade) em modo dry-run. Zero erros de "relation does not exist" ou "column does not exist".
- [ ] **AC7: Ruff check** — `ruff check` em todos os modulos modificados retorna 0 erros
- [ ] **AC8: Documentacao** — Schema real documentado em `supabase/current-schema.sql` atualizado com pg_dump apos correcoes

## Technical Design

### Fase 1: Auditoria sistematica

Extrair todas as queries SQL do codigo fonte:

```bash
grep -rn "SELECT\|INSERT\|UPDATE\|DELETE" scripts/ --include="*.py" | grep -v "__pycache__" | grep -v ".pyc"
```

Para cada query, extrair:
1. Nome das tabelas referenciadas
2. Nome das colunas referenciadas
3. Comparar com `supabase/current-schema.sql` (pg_dump do banco real)

Output: `docs/stories/epics/epic-master-b2g/schema-gap-audit-{data}.md`

### Fase 2: Mapeamento de colunas fantasmas

| Coluna fantasma | Acao esperada | Justificativa |
|----------------|--------------|---------------|
| `ni_fornecedor` | Renomear codigo para `fornecedor_cnpj` | Coluna real existe |
| `valor_global` | Renomear codigo para `valor_total` | Coluna real existe |
| `data_assinatura` | Mapear para `data_inicio` OU criar migration com alias | Depende do caso de uso |
| `numero_controle_pncp` | Renomear codigo para `contrato_id` | Coluna real existe |
| `situacao_compra` | Migration para adicionar OU remover do codigo | Investigar se necessario |
| `unidade_nome` | Migration para adicionar OU remover do codigo | Investigar se necessario |
| `link_sistema_origem` | Migration para adicionar OU remover do codigo | Investigar se necessario |

### Fase 3: Correcao de `search_datalake`

Cenario atual:
```sql
-- Banco: 10 parametros
CREATE FUNCTION search_datalake(p_uf TEXT, p_dias INT, ...) RETURNS TABLE(...)

-- Codigo Python: 12-13 parametros
cur.callproc('search_datalake', [uf, dias, param3, param4, param5, param6, param7, param8, param9, param10, param11, param12])
```

Solucao preferencial: **Ajustar chamadas Python para 10 params**, pois alterar funcao no banco pode quebrar outros consumidores. Documentar cada parametro removido com justificativa.

Alternativa: Criar overload no banco:
```sql
CREATE FUNCTION search_datalake(p_uf TEXT, p_dias INT, ..., p_param11 TEXT DEFAULT NULL, p_param12 TEXT DEFAULT NULL)
RETURNS TABLE(...)
```

### Fase 4: Teste de migration 006-v3

```bash
# 1. Banco de teste vazio
createdb extra_test_empty
psql extra_test_empty < supabase/migrations/006-v3-unified-schema.sql

# 2. Copia do banco real
pg_dump extra_consultoria > /tmp/extra_backup.sql
createdb extra_upgrade_test
psql extra_upgrade_test < /tmp/extra_backup.sql
psql extra_upgrade_test < supabase/migrations/006-v3-unified-schema.sql

# 3. Validar constraints
psql extra_upgrade_test -c "SET constraint_exclusion = off; SELECT COUNT(*) FROM information_schema.table_constraints WHERE constraint_type = 'FOREIGN KEY' AND is_valid = 'NO';"
```

### Arquivos a modificar

- Multiplos arquivos `.py` — conforme auditoria de gap (a definir na Fase 1)
- `supabase/current-schema.sql` — Atualizado apos correcoes

### Testes

| Teste | Descricao |
|-------|-----------|
| `test_all_tables_exist` | Todas as tabelas referenciadas no codigo existem no schema |
| `test_all_columns_exist` | Todas as colunas referenciadas existem nas tabelas correspondentes |
| `test_search_datalake_signature` | Numero de parametros na chamada Python corresponde a definicao no banco |
| `test_migration_006_v3_empty` | Migration 006-v3 aplica limpa em banco vazio |
| `test_migration_006_v3_upgrade` | Migration 006-v3 aplica sem erros em copia do banco real |
| `test_constraints_validated` | Zero constraints `NOT VALID` apos migracao |
| `test_all_queries_dry_run` | Todas as queries SQL do codigo executam sem erro em modo dry-run com o schema real |

## File List

- **MODIFY** `supabase/current-schema.sql` (atualizado com pg_dump apos correcoes)
- **MODIFY** Multiplos arquivos `.py` (mapeamento de colunas — a definir na auditoria)
- **CREATE** `docs/stories/epics/epic-master-b2g/schema-gap-audit-{data}.md` (auditoria)

## Dependencies

- Nenhuma — pode ser implementada em paralelo com FIX-UNIVERSE e FIX-MANIFEST
- Idealmente executada apos FIX-TRANSACTION para evitar conflitos em `consulting_readiness.py`

## Rollback

- **Migration rollback:** `supabase/migrations/006-v3-down.sql` (se existir) ou pg_restore do backup pre-migration
- **Codigo:** git revert dos commits de correcao de colunas
- Backup do banco real antes de qualquer operacao de migracao

## Security Considerations

- Queries com colunas fantasmas podem vazar informacao errada ou falhar silenciosamente
- Indices e constraints faltantes podem permitir dados invalidos ou duplicados
- `search_datalake` com assinatura errada pode retornar colunas trocadas (data leak potencial)
- Migration de schema requer backup completo do banco antes da execucao

## Tests

Testes de integracao contra banco de teste (nao producao):
- Schema validation: queries SQL extraidas do codigo executadas em modo dry-run
- Migration tests: aplicacao em banco vazio + em copia do banco real
- `search_datalake` signature validation via reflection: `SELECT pronargs FROM pg_proc WHERE proname = 'search_datalake'`

## Definition of Done

- [ ] Auditoria de gap completa e documentada (AC1)
- [ ] Colunas fantasmas mapeadas e corrigidas (AC2)
- [ ] `search_datalake` corrigido (AC3)
- [ ] Migration 006-v3 testada (AC4 — banco vazio + upgrade)
- [ ] Tabelas ausentes resolvidas ou documentadas como tech debt (AC5)
- [ ] Todas as queries do codigo validadas contra schema real (AC6)
- [ ] ruff check passa em todos os modulos modificados
- [ ] Testes de schema passam
- [ ] QA gate PASS
