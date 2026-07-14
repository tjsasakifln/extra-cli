# Migration Forensics — B2G-FIX-04

**Data:** 2026-07-14
**HEAD:** `11fca9b`
**Método:** 4 subagentes read-only → convergência pelo coordenador
**PostgreSQL canônico:** 16 (Ubuntu 24.04 LTS)
**Extensões:** pg_trgm, uuid-ossp, vector (pgvector)

---

## 1. Resumo dos Achados

| # | Severidade | Achado | Migrations |
|---|-----------|--------|------------|
| F1 | CRITICAL | Falha silenciosa: stderr → /dev/null | setup_db.sh |
| F2 | CRITICAL | Colisão nomenclatura 021 (4 arquivos) | 021a-d |
| F3 | CRITICAL | `b.embedding` nunca criado | 014 |
| F4 | CRITICAL | 026 usa `orgao_cnpj8` (inexistente) | 026 |
| F5 | CRITICAL | 014 referencia colunas de 023 | 014 |
| F6 | CRITICAL | 013 usa `is_active` (ausente em 002) | 013 |
| F7 | CRITICAL | 025 usa `cnpj_raiz` (coluna real: `cnpj_8`) | 025a |
| F8 | HIGH | Sem ledger no setup_db.sh | setup_db.sh |
| F9 | HIGH | Senha `smartlic_local` hardcoded | 4 arquivos |
| F10 | HIGH | Dois diretórios migration concorrentes | db/ vs supabase/ |
| F11 | HIGH | 029 vs 040 conflito ENUM + colunas | 029, 040 |
| F12 | HIGH | FKs NOT VALID sem VALIDATE CONSTRAINT | 029, 034, 041a |
| F13 | HIGH | 034 FKs quebradas (14-digit vs 8-digit) | 034 |
| F14 | MEDIUM | 6 views EXPECTED_VIEWS nunca criadas | diagnostics.py |
| F15 | MEDIUM | 8 views runtime ausentes do EXPECTED_VIEWS | diagnostics.py |
| F16 | MEDIUM | Sem advisory lock | setup_db.sh |
| F17 | LOW | Checksum schema inconsistente | current-schema.sha256 |

---

## 2. Análise por Migration com Falha Reportada

### 013 — `td-1.1_gin_index_objeto_contrato.sql`

**Erro esperado:** `column "is_active" does not exist`

**Causa raiz:** Cria índice GIN `WHERE is_active = TRUE` em `pncp_supplier_contracts`, mas a migration 002 NÃO cria a coluna `is_active`. Foi adicionada via DDL manual fora do sistema de migrations.

**Classificação:** `LEGACY_ASSUMPTION`
**Estratégia:** Adicionar `ALTER TABLE pncp_supplier_contracts ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE` antes da criação do índice.
**Risco de dados:** Nenhum (fresh install).
**Teste:** Fresh install + verificar existência da coluna e índice.

### 014 — `td-1.1_fix_hnsw_expression.sql`

**Erro esperado:** `extension "vector" is not available` (se pgvector não instalado no sistema)

**Causa raiz:** `CREATE EXTENSION IF NOT EXISTS vector` exige que o pacote `postgresql-16-pgvector` esteja instalado no sistema. Em containers Docker oficiais `postgres:16`, pgvector NÃO está incluído.

**Além disso:** A função `search_datalake` referencia colunas (`situacao_compra`, `unidade_nome`, `link_sistema_origem`) que só são criadas na migration 023. Como é `CREATE OR REPLACE FUNCTION` com `LANGUAGE plpgsql`, a criação não falha (late binding), mas a função falharia se invocada antes de 023 ser aplicada.

**Classificação:** `ENVIRONMENT_PREREQUISITE`
**Estratégia:** Bootstrap instalar `postgresql-16-pgvector` OU usar imagem Docker `pgvector/pgvector:pg16`. A função em si não precisa ser alterada (late binding resolve as colunas).
**Risco de dados:** Nenhum (função com late binding, não executada durante migration).
**Teste:** Fresh install + verificar extensão criada.

### 020 — `td-2.4_sync_local_schema.sql`

**Erro esperado:** Provável conflito com 009 (ambas criam `entity_coverage`).

**Causa raiz:** 009 cria `entity_coverage` sem `IF NOT EXISTS`. 020 recria com `IF NOT EXISTS`. Se a ordem for 009 → 020, funciona. Se 020 executar sozinho (banco parcialmente migrado), pode falhar se `sc_public_entities` não existir (FK reference).

**Classificação:** `ORDERING_DEFECT` (menor)
**Estratégia:** Garantir ordem correta (009 antes de 020). Verificar se 020 depende de objetos de 007.
**Risco de dados:** Nenhum (fresh install).
**Teste:** Fresh install na ordem correta.

### 022 — `match_method_coverage.sql`

**Erro esperado:** Coluna `match_method` já existe (criada por 021a).

**Causa raiz:** Duas migrations diferentes (021a e 022) adicionam a mesma coluna `match_method` em `entity_coverage`. 022 usa `ALTER TABLE entity_coverage ADD COLUMN IF NOT EXISTS match_method TEXT` — seguro se 021a executou primeiro.

**Classificação:** `NON_IDEMPOTENT` (risco baixo, IF NOT EXISTS protege)
**Estratégia:** Garantir ordem: 021a → 022. O `IF NOT EXISTS` na 022 protege contra duplicação.
**Risco de dados:** Nenhum.
**Teste:** Fresh install, verificar que a coluna existe com a definição correta.

### 023 — `pncp_engineering_pipeline.sql`

**Erro esperado:** Nenhum erro SQL direto. Mas `UPDATE` massivo em `pncp_raw_bids` pode ser lento.

**Causa raiz:** Adiciona 13 colunas e 3 tabelas. O UPDATE `SET numero_controle_pncp = COALESCE(numero_controle_pncp, pncp_id)` em banco vazio é instantâneo.

**Classificação:** `SAFE_FRESH_INSTALL`
**Estratégia:** Nenhuma correção necessária para fresh install.
**Risco de dados:** Nenhum (fresh install, tabela vazia).
**Teste:** Fresh install, verificar colunas e tabelas criadas.

### 025a — `contract_intel_views.sql`

**Erro esperado:** `column e.cnpj_raiz does not exist`

**Causa raiz:** Views usam `e.cnpj_raiz` para JOIN com `sc_public_entities`. A coluna real em `sc_public_entities` é `cnpj_8`. `cnpj_raiz` nunca foi criada em nenhuma migration.

**Classificação:** `LEGACY_ASSUMPTION`
**Estratégia:** Corrigir views 025a para usar `e.cnpj_8` em vez de `e.cnpj_raiz`. OU adicionar coluna `cnpj_raiz` como generated column.
**Risco de dados:** Nenhum (views são read-only).
**Teste:** Fresh install, verificar que views compilam sem erro.

### 025b — `coverage_evidence_null_uniqueness.sql`

**Erro esperado:** `DROP CONSTRAINT` falha se constraint não existe.

**Causa raiz:** Usa lookup dinâmico em `pg_constraint` para dropar a UNIQUE constraint. Se a constraint foi criada com nome diferente ou não existe, o lookup retorna NULL e o DROP é pulado (protegido por IF).

**Classificação:** `SAFE_UPGRADE`
**Estratégia:** Nenhuma correção necessária. O script é condicional.
**Risco de dados:** Baixo (janela sem constraint durante DROP → CREATE INDEX).
**Teste:** Fresh install, verificar partial unique indexes.

### 026 — `contract_intel_truth_v1.sql`

**Erro esperado:** `column c.orgao_cnpj8 does not exist`

**Causa raiz:** Views fazem JOIN com `c.orgao_cnpj8 = e.cnpj_8`. A coluna `orgao_cnpj8` (sem underscore) nunca foi criada. A migration 041a cria `orgao_cnpj_8` (com underscore) como generated column. Nome diferente.

**Classificação:** `LEGACY_ASSUMPTION`
**Estratégia:** Corrigir 026 para usar `c.orgao_cnpj_8` (com underscore) OU criar coluna `orgao_cnpj8` como alias.
**Risco de dados:** Nenhum (views read-only).
**Teste:** Fresh install, verificar views compilam.

### 039 — `source_snapshot_tracking.sql`

**Erro esperado:** `UPDATE` em `opportunity_intel` (tabela vazia em fresh install — OK). Possível falha se 029 não executou.

**Causa raiz:** Adiciona colunas a `opportunity_intel` e referencia colunas que 029 adicionou a `opportunity_runs`. Ordem numérica é correta (029 < 039).

**Classificação:** `ORDERING_DEFECT` (se 029 não executou)
**Estratégia:** Garantir ordem: 029 → 039.
**Risco de dados:** Nenhum (fresh install).
**Teste:** Fresh install, verificar função `fn_record_snapshot_membership`.

### 040 — `coverage_model_expansion.sql`

**Erro esperado:** `ALTER TYPE evidence_state ADD VALUE 'pending'` falha se 029 já adicionou. Ou conflito de colunas com 029.

**Causa raiz:** 029 e 040 adicionam as mesmas colunas a `coverage_evidence` e os mesmos valores ao ENUM `evidence_state`. 040 usa `IF NOT EXISTS` para colunas e trata exceção para ENUM values — seguro, mas comportamento não determinístico (depende da ordem).

**Classificação:** `NON_IDEMPOTENT` (protegido por exception handler)
**Estratégia:** Unificar evidências de 029 e 040. Garantir ordem: 029 → 040.
**Risco de dados:** Nenhum (fresh install).
**Teste:** Fresh install, verificar ENUM values e colunas sem duplicação.

### 041a — `fix_fk_constraints.sql`

**Erro esperado:** `DROP CONSTRAINT` falha se FKs de 034 não existem (fresh install sem 034).

**Causa raiz:** 041a faz DROP das FKs quebradas de 034 com `IF EXISTS`. Se 034 nunca foi aplicada, o DROP é pulado. Em fresh install, 041a criaria as FKs NOT VALID diretamente (linhas de DROP são NO-OP).

**MAS:** As generated columns `orgao_cnpj_8` e `fornecedor_cnpj_8` são criadas via `ALTER TABLE ADD COLUMN IF NOT EXISTS`. Isso funciona em fresh install OU upgrade.

**Classificação:** `SAFE_UPGRADE`
**Estratégia:** Garantir que 041a execute. Adicionar migration separada para `VALIDATE CONSTRAINT`.
**Risco de dados:** Baixo (NOT VALID não bloqueia dados existentes).
**Teste:** Fresh install, verificar FKs existem, validar FKs.

### 041b — `fix_snapshot_membership.sql`

**Erro esperado:** Nenhum. `CREATE OR REPLACE FUNCTION` é idempotente.

**Causa raiz:** Substitui funções de 039. Corrige key mismatch Python/JSON.

**Classificação:** `SAFE_UPGRADE`
**Estratégia:** Nenhuma correção necessária.
**Risco de dados:** Nenhum (função substituída, sem perda).
**Teste:** Fresh install, verificar função substituída.

---

## 3. Classificação Consolidada

| Classificação | Count | Migrations |
|---------------|-------|------------|
| ENVIRONMENT_PREREQUISITE | 1 | 014 (pgvector) |
| ORDERING_DEFECT | 3 | 014/023, 029/039, 029/040 |
| MIGRATION_DEFECT | 0 | — |
| LEGACY_ASSUMPTION | 5 | 013, 014, 025a, 026, diagnostics.py views |
| NON_IDEMPOTENT | 4 | 001, 002, 003, 007 (sem IF NOT EXISTS) |
| OBSOLETE_MIGRATION | 0 | — |
| RUNNER_DEFECT | 3 | setup_db.sh (stderr, ledger, lock) |
| SCHEMA_CONTRACT_DEFECT | 2 | diagnostics.py (views fantasma/ausentes) |

---

## 4. Estratégia de Correção

### Bootstrap (pré-migrations)

1. Instalar PostgreSQL 16 + pgvector (imagem `pgvector/pgvector:pg16` ou `apt install postgresql-16-pgvector`)
2. Criar database vazio
3. Criar extensões: `pg_trgm`, `uuid-ossp`, `vector`

### Runner

1. `db/setup_db.sh`: remover `2>&1`, adicionar log file
2. Adicionar `_migrations` ledger com checksums
3. Adicionar advisory lock
4. Substituir fallback `smartlic_local` por `${VAR:?erro}`

### Migrations — correções pontuais

| Migration | Correção | Tipo |
|-----------|---------|------|
| 013 | Adicionar `is_active` antes do índice | Bootstrap SQL antes de 013 |
| 014 | Garantir pgvector instalado. Manter função (late binding seguro) | Bootstrap |
| 025a | Corrigir `cnpj_raiz` → `cnpj_8` | Editar migration |
| 026 | Corrigir `orgao_cnpj8` → `orgao_cnpj_8` | Editar migration |
| 029/040 | Garantir ordem. Documentar conflito | Runner |
| 041a | Adicionar `VALIDATE CONSTRAINT` como migration separada | Nova migration |
| 021* | Renomear para 021a-d com prefixos explícitos | Renomear arquivos |

### diagnostics.py

1. Remover 6 views fantasma do EXPECTED_VIEWS
2. Adicionar 8 views runtime ao EXPECTED_VIEWS
3. Adicionar `functions_missing` e `triggers_missing` à saída

### current-schema.sql

- Regenerar via `pg_dump --schema-only` após fresh install aprovado
- Atualizar SHA256

---

## 5. Plano de Implementação

### Lane A: Bootstrap + Runner (@data-engineer + @dev)
- `db/setup_db.sh`: correções de runner
- Bootstrap script: extensões + pré-requisitos
- Migration ledger
- Testes do runner

### Lane B: Migrations 001-028 (@data-engineer)
- Correções: 013, 025a, 026
- Renomeação: 021a-d
- Testes fresh install parcial (001-028)

### Lane C: Migrations 029-041 (@data-engineer)
- Ordenação: 029 → 040
- VALIDATE CONSTRAINT após 041a
- Testes fresh install completo
- Testes upgrade path

### Lane D: Diagnostics + Schema (@dev)
- Correção EXPECTED_VIEWS
- Adição de functions/triggers check
- Regeneração current-schema.sql (após fresh install)

---

## 6. Matriz de Riscos Residuais

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| pgvector não disponível no ambiente | Baixa | Alto | Documentar requisito, fallback para imagem pgvector/pgvector |
| Colunas manuais não documentadas | Média | Médio | Auditoria de schema drift como follow-up |
| FKs NOT VALID em dados existentes | Média | Alto | VALIDATE CONSTRAINT com lock_timeout |
| 029/040 divergência em upgrade | Baixa | Médio | Testar ambos os caminhos |
| Views de 025a/026 com colunas diferentes em schema antigo | Média | Baixo | Verificar schema real antes de aplicar |

---

*Forensics consolidado de 4 subagentes — 2026-07-14*
