# Database Audit — Extra Consultoria

**Data:** 2026-07-11
**Banco:** PostgreSQL 16.4, `postgres` database, porta 54399
**Tamanho:** 4.1 GB
**Tabelas:** 6 (199K bids + 3.69M contratos + 13.8K enrichments + 2K entes + 2 tabelas de ingestao)

---

## 1. Schema Quality Assessment

### Strengths

1. **Chaves primarias em todas as tabelas** — Nenhuma tabela sem PK.
2. **Check constraints em ingestion_runs** — `run_type` e `status` tem valores validados.
3. **Check constraint em ingestion_checkpoints** — `status` validado.
4. **Unique constraints de dedup** — `content_hash` UNIQUE em bids e contracts, `cnpj_8` UNIQUE em sc_public_entities.
5. **Triggers de updated_at** — Consistentes em bids e contracts.
6. **Trigger de TSVECTOR** — Auto-atualizacao do vetor de full-text search.
7. **Partial indexes** — Uso extensivo de `WHERE` clauses em indexes (bids: `is_active`, `data_encerramento IS NOT NULL`, etc.).
8. **Genereted Always As Identity** — ingestion_checkpoints e ingestion_runs usam identity columns (melhor que SERIAL).
9. **Text search config customizada** — `portuguese_smartlic` com unaccent + portuguese_stem.
10. **Soft-delete padrao** — `is_active` column em todas as tabelas principais.

### Issues Found

#### ISSUE-1: Drift completo entre migrations e schema real
- **Severidade:** CRITICAL
- **Descricao:** Nenhuma das 12 migrations corresponde ao schema real do banco. As migrations 001-008 definem schemas diferentes do que esta em producao (colunas diferentes, tipos diferentes, constraints diferentes). As migrations 009-012 nunca foram aplicadas.
- **Impacto:** Impossivel reconstruir o banco a partir das migrations. Qualquer novo desenvolvedor nao consegue replicar o ambiente.
- **Recomendacao:** Regenerar todas as migrations para refletir o schema real (via `pg_dump --schema-only`). Estabelecer processo de migration tracking.

#### ISSUE-2: `esfera_id` como TEXT (inconsistente)
- **Severidade:** MEDIUM
- **Tabela:** `pncp_raw_bids`
- **Descricao:** Migration 001 define `esfera_id INT`, mas o schema real usa `esfera_id TEXT` com valores como 'F', 'E', 'M', 'D'.
- **Impacto:** Perda de validacao de dominio. Nao ha CHECK constraint para limitar os valores.
- **Recomendacao:** Adicionar CHECK constraint `esfera_id IN ('F','E','M','D')` ou criar tabela de lookup.

#### ISSUE-3: `data_publicacao`, `data_abertura`, `data_encerramento` como TIMESTAMPTZ
- **Severidade:** MEDIUM
- **Tabela:** `pncp_raw_bids`
- **Descricao:** Migration define como DATE, mas o real usa TIMESTAMPTZ. Alem disso, nao ha NOT NULL constraint apesar do codigo aplicar fallback de data.
- **Recomendacao:** Decidir se precisa de TIME (aparentemente nao) e consolidar para DATE com NOT NULL.

#### ISSUE-4: `objeto_compra` NOT NULL sem fallbank no schema
- **Severidade:** MEDIUM
- **Tabela:** `pncp_raw_bids`
- **Descricao:** `objeto_compra` é NOT NULL, mas nao ha DEFAULT. Se um record chegar sem objeto, a query quebra.
- **Recomendacao:** Adicionar DEFAULT '' ou garantir que o loader sempre preencha.

#### ISSUE-5: enriched_entities schema divergente
- **Severidade:** HIGH
- **Tabela:** `enriched_entities`
- **Descricao:** Migration 003 define schema com colunas `cnpj`, `razao_social`, `cnae_principal`, etc. O real usa schema generico `entity_type`/`entity_id`/`data` JSONB. O TTL de 30 dias mencionado no codigo nao é enforceado pelo banco.
- **Impacto:** Cache pode crescer indefinidamente sem garbage collection.
- **Recomendacao:** Adicionar job de cleanup periodico ou TTL-based partitioning.

#### ISSUE-6: ingestion_checkpoints sem uso
- **Severidade:** LOW
- **Descricao:** Tabela tem 0 registros. A estrutura e os indexes existem mas nunca foram populados.
- **Impacto:** Crawlers nao sao resumeveis — em caso de falha, recomecam do inicio.
- **Recomendacao:** Integrar checkpoints nos crawlers ou remover a tabela.

---

## 2. Security Audit

### RLS Policies
- **NENHUMA** policy de Row-Level Security configurada.
- **Avaliacao:** Aceitavel para single-user (apenas role `postgres`). Se o banco for exposto futuramente, RLS sera necessario.

### SQL Injection Risk
- **Baixo risco** — O codigo Python usa `psycopg2` com query parameterized (`%s` placeholders) em todo o `datalake_helper.py` e `local_datalake.py`.
- **Risco moderado** no `monitor.py` linha 498: `cur.execute("SELECT * FROM upsert_pncp_raw_bids(%s)", (json.dumps(records),))` — embora com placeholder `%s`, o JSON e gerado internamente (sem input do usuario), entao e seguro.
- **Avaliacao:** Aceitavel.

### Permission Model
- Unico role: `postgres` (superuser).
- Sem roles de aplicacao, sem usuarios separados para leitura/escrita.
- **Avaliacao:** Aceitavel para single-user. Se houver expansao, criar roles `datalake_reader` (SELECT apenas) e `datalake_writer` (INSERT/UPDATE).

### Secrets Management
- **Credencial** `postgres:smartlic_local` hardcoded como default no `config/settings.py` e em varios scripts Python.
- **Avaliacao:** Risco MEDIO. A senha "smartlic_local" esta em texto puro em multiplos lugares, versionada no git.
- **Recomendacao:** Mover para `.env` file ou usar `pgpass`. Manter credencial default apenas para desenvolvimento local, nunca em staging/production.

---

## 3. Performance Audit

### Missing Indexes

1. **`pncp_raw_bids.matched_entity_id`** — Nao ha index para joins com `sc_public_entities`. A query de coverage no monitor.py faz LEFT JOIN sem index.
   - **Impacto:** POTENCIALMENTE ALTO se a coverage query rodar frequente.
   - **Sql sugerido:** `CREATE INDEX IF NOT EXISTS idx_bids_matched_entity_id ON pncp_raw_bids(matched_entity_id) WHERE matched_entity_id IS NOT NULL;`

2. **`pncp_raw_bids.source`** — Embora haja `idx_pncp_raw_bids_uf_date`, nao ha index simples apenas em `source` para queries do tipo "todas bids de X source".
   - **Impacto:** BAIXO (source tem baixa cardinalidade).

### Query Analysis

**Query problematica:** `search_datalake` function linha 210-213:
```sql
(1.0 - (b.embedding <=> p_embedding)) > v_cos_threshold
```
Quando `p_embedding` e fornecido, a funcao faz scan sequencial se o HNSW index nao for usado corretamente. O HNSW index com `vector_cosine_ops` requer operador `<=>` no ORDER BY ou WHERE com operador de distancia. A expressao `1.0 - (vec <=> ...)` e uma transformacao que pode impedir o uso do index.

**Recomendacao:** Testar `EXPLAIN ANALYZE` com e sem embedding filter. Se o HNSW nao for usado, reescrever como:
```sql
AND (b.embedding <=> p_embedding) < (1.0 - v_cos_threshold)
```

### Anti-patterns Found

1. **GIST trigram index muito grande (294 MB):** `idx_pncp_raw_bids_objeto_trgm` consome 294 MB para uma tabela de 268 MB de dados. Isso acontece porque o GIST index em texto e muito custoso. Considere substituir por GIN trigram index, que e 2-3x menor (mas lento para updates).
   - **Impacto:** MEDIO (custo de storage + manutencao).
   - **Recomendacao:** Avaliar se `word_similarity()` fallback e usado com frequencia. Se sim, trocar para `idx_pncp_raw_bids_objeto_trgm ON pncp_raw_bids USING GIN (objeto_compra gin_trgm_ops)`.

2. **Constraints sem index no `datalake_helper.py`:** `supplier_contracts()` usa `ILIRE` em `objeto_contrato` sem index GIN/GIST. A tabela de 3.69M contratos faz full table scan a cada busca textual.
   - **Impacto:** ALTO para queries de pricing/competitors.
   - **Recomendacao:** Adicionar index: `CREATE INDEX idx_psc_objeto_trgm ON pncp_supplier_contracts USING GIN (objeto_contrato gin_trgm_ops) WHERE is_active = true;`

3. **`upsert_pncp_supplier_contracts` row-by-row:** A funcao itera com `FOR rec IN SELECT * FROM jsonb_array_elements(...)` e faz SELECT + INSERT separadamente. Isso e ~10x mais lento que a abordagem set-based.
   - **Impacto:** MEDIO (3.69M contratos inseridos com esse metodo).
   - **Recomendacao:** Re-escrever usando `jsonb_to_recordset()` + INSERT ... ON CONFLICT como em `upsert_supplier_contracts`.

4. **`search_datalake` sem index para `websearch_text`:** A funcao tenta parsear `p_websearch_text` como TSQUERY, mas nao ha index GIN que cubra `tsv` para queries websearch-to-tsquery.
   - **Impacto:** BAIXO (o mesmo GIN index atende).

---

## 4. Database Technical Debt Inventory

| ID | Debito | Severidade | Tabela/Objeto | Impacto | Recomendacao |
|----|--------|------------|---------------|---------|-------------|
| DT-01 | Migrations totalmente divergentes do schema real | CRITICAL | Todas | Rebuild impossivel | Regenerar migrations com `pg_dump --schema-only` |
| DT-02 | 4 migrations nunca aplicadas (009-012) | HIGH | entity_coverage, views, snapshots | Funcionalidade de coverage ausente | Aplicar migrations 009, 010, 011, 012 |
| DT-03 | enriched_entities sem TTL enforcement | MEDIUM | enriched_entities | Cache cresce sem controle | Job de cleanup ou partitioning |
| DT-04 | upsert_pncp_supplier_contracts row-by-row | MEDIUM | pncp_supplier_contracts | Performance subotima | Re-escrever set-based |
| DT-05 | Senha hardcoded em multiplos scripts | MEDIUM | config/settings.py | Exposicao de credencial | Migrar para .env |
| DT-06 | GIST trigram index superdimensionado | MEDIUM | pncp_raw_bids | 294 MB de index | Avaliar GIN trigram |
| DT-07 | Missing index matched_entity_id | LOW | pncp_raw_bids | Coverage queries lentas | Adicionar index |
| DT-08 | Missing GIN index on objeto_contrato | HIGH | pncp_supplier_contracts | Full table scans em contratos | Adicionar GIN trigram index |
| DT-09 | esfera_id sem CHECK constraint | LOW | pncp_raw_bids | Dominio nao validado | Adicionar CHECK |
| DT-10 | ingestion_checkpoints sem uso | LOW | ingestion_checkpoints | Dead code | Integrar ou remover |
| DT-11 | search_datalake HNSW pode nao ser usado | MEDIUM | Function | Queries embedding lentas | Reescrever expressao `1.0 - <=>` |
| DT-12 | Codigo referencia tabela/search_results_cache que nao existe | LOW | local_datalake.py | Confusao | Remover da listagem stats |
| DT-13 | Codigo referencia colunas que nao existem no schema | MEDIUM | datalake_helper.py | Queries podem falhar | Sincronizar schema Python x PG |
| DT-14 | `purge_old_bids` faz DELETE fisico (irreversivel) | MEDIUM | pncp_raw_bids | Perda de dados historicos | Migrar para soft-delete |

---

## 5. Migration Hygiene

### Problemas Graves

1. **Migrations nao sao o source of truth.** O banco foi evoluido diretamente com DDL avulso. As migrations existentes sao versoes desatualizadas e enganosas.

2. **Nao ha tracking de migrations aplicadas.** Nenhuma tabela `_migrations` ou `schema_migrations_history` controla o estado.

3. **Nomes de migrations nao seguem convencao de reversibilidade.** Nao ha `DOWN` scripts para rollback.

4. **Ordem de aplicacao problematica:** Migration 009 referencia `entity_coverage` tabela e triggers que dependem de `sc_public_entities` e `pncp_raw_bids`, mas estas tabelas tem schema diferente do esperado.

### Recomendacoes

1. Executar `pg_dump --schema-only --no-owner --no-acl > db/schemas/current-schema.sql` para capturar o estado real.
2. Criar migrations regeneradas (`migration 001-v2`, `002-v2`, etc.) que refletem o schema real.
3. Aplicar migrations 009-012 (adaptadas para o schema atual).
4. Criar tabela de tracking de migrations.

---

## 6. Recommendations (Prioritized)

### Criticas (fazer imediatamente)

1. **[CRITICAL] Regenerar migrations** — `pg_dump --schema-only > db/schema/schema-current.sql` e criar novo conjunto de migrations que corresponda ao banco real.

2. **[HIGH] Aplicar migrations 009-012** — Criar entity_coverage, views de coverage, unmatched_bids, coverage_snapshots. Sem isso, o sistema de monitoramento de cobertura nao funciona.

3. **[HIGH] Adicionar index GIN em `pncp_supplier_contracts.objeto_contrato`** — Queries ILIKE atualmente varrem 3.69M registros sequencialmente.
   ```sql
   CREATE INDEX idx_psc_objeto_trgm ON pncp_supplier_contracts
   USING GIN (objeto_contrato gin_trgm_ops) WHERE is_active = true;
   ```

### Importantes (fazer nessa sprint)

4. **[MEDIUM] Otimizar `upsert_pncp_supplier_contracts`** — Substituir FOR loop por `jsonb_to_recordset()`.

5. **[MEDIUM] Mover senha do DB para .env** — Remover `smartlic_local` do codigo fonte.

6. **[MEDIUM] Auditar expressao HNSW em `search_datalake`** — Verificar se o index de embedding esta sendo utilizado.

7. **[MEDIUM] Adicionar `matched_entity_id` index** — Facilitar joins com sc_public_entities.

### Baixa prioridade (para referencia)

8. **[LOW] CHECK constraint em `esfera_id`** — Validar valores como 'F', 'E', 'M', 'D'.

9. **[LOW] Decidir destino das `ingestion_checkpoints`** — Usar ou remover.

10. **[LOW] Atualizar `local_datalake.py`** — Remover referencias a tabelas inexistentes da lista `CORE`.

---

## Resumo de Metricas

| Metrica | Valor |
|---------|-------|
| Tabelas | 6 |
| Indices | 36 (sum 36) |
| Funcoes customizadas | 10 (8 projeto + 162 extensao = 170) |
| Triggers | 3 |
| Views | 0 |
| RLS Policies | 0 |
| Roles | 1 (superuser) |
| Extensoes | 4 (pg_trgm, plpgsql, unaccent, vector) |
| Total de debitos identificados | 14 |
| Debitos criticos | 1 (DT-01) |
| Debitos high | 3 (DT-02, DT-05, DT-08) |
| Debitos medium | 7 |
| Debitos low | 3 |
