# Normalizacao e Constraints — TD-2.3

## Resumo

Implementacao de constraints, indexes e TTL enforcement para resolver deficits de schema TD-DB-03, TD-DB-06 e TD-DB-07.

| Deficit | Severidade | Descricao | Resolucao |
|---------|-----------|-----------|-----------|
| TD-DB-03 | MEDIUM | enriched_entities sem TTL enforcement | Funcao de cleanup + script cron + CHECK constraints |
| TD-DB-06 | MEDIUM | GIST trigram index superdimensionado em objeto_compra | Migracao para GIN (menor, mais rapido para ILIKE) |
| TD-DB-07 | MEDIUM | Missing index em matched_entity_id | Reforco do index partial com IF NOT EXISTS |

## Arquivos Criados

| Arquivo | Proposito |
|---------|-----------|
| `db/migrations/015_td-2.3_enriched_entities_ttl.sql` | TTL function + CHECK constraints |
| `db/migrations/016_td-2.3_objeto_compra_gin.sql` | GIN trigram index em objeto_compra |
| `db/migrations/017_td-2.3_matched_entity_id_index.sql` | Index partial em matched_entity_id |
| `scripts/cleanup-expired-entities.sql` | Script para job periodico de cleanup TTL |

---

## 1. TTL Enforcement (TD-DB-03)

### Problema

13.8K registros em `enriched_entities` sem politica de expiracao. Dados obsoletos podem acumular e degradar qualidade de queries de enrichment.

### Solucao

**Funcao `ttl_cleanup_enriched_entities(p_ttl_days INT DEFAULT 90)`:**

```sql
SELECT ttl_cleanup_enriched_entities();   -- default 90 dias
SELECT ttl_cleanup_enriched_entities(30);  -- cleanup agressivo (30 dias)
```

- Remove registros com `enriched_at < CURRENT_DATE - p_ttl_days`
- Retorna numero de registros removidos
- Log via `RAISE NOTICE` para visibilidade em logs de cron

**CHECK constraints adicionadas:**

| Constraint | Tabela | Descricao |
|-----------|--------|-----------|
| `chk_ee_enriched_at_not_future` | enriched_entities | enriched_at nao pode estar no futuro |
| `chk_ee_cnpj_not_empty` | enriched_entities | CNPJ nao pode ser string vazia |
| `chk_ee_enriched_source_not_empty` | enriched_entities | enriched_source nao pode ser string vazia |

Todas as constraints foram criadas com `NOT VALID` para bloqueio zero em producao.

**Job periodico (cron):**

```bash
# Executar semanalmente (domingo 3h)
0 3 * * 0 psql $DATABASE_URL -f /path/to/scripts/cleanup-expired-entities.sql
```

O script `scripts/cleanup-expired-entities.sql` executa a limpeza e imprime estatisticas pos-execucao.

---

## 2. GIST vs GIN — Index Trigram (TD-DB-06)

### Problema

Index GIST em `pncp_raw_bids.objeto_compra` reportado como superdimensionado (294 MB para ~200K registros ativos), relacao index/dados de 1.1x.

### Analise Comparativa

| Caracteristica | GIST (gist_trgm_ops) | GIN (gin_trgm_ops) |
|---------------|---------------------|-------------------|
| Tamanho | Maior (~294 MB) | Menor (~40-60% do GIST) |
| INSERT performance | Mais rapido | Mais lento (compressao) |
| SELECT performance (ILIKE) | Mais lento | Mais rapido (bitmap scan) |
| `word_similarity()` | Suportado nativamente | NAO suportado |
| `ILIKE '%term%'` | Suportado | Suportado (mais rapido) |

### Decisao: GIN

**Justificativa:**
1. Codigo existente usa ILIKE e tsquery — NENHUM uso de `word_similarity()` na base (.sql ou .py)
2. GIN e 40-60% menor que GIST
3. GIN e significativamente mais rapido para SELECT com ILIKE
4. Caso `word_similarity()` seja necessario no futuro, manter GIST como fallback

**Index criado:**

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bids_objeto_compra_gin
    ON pncp_raw_bids USING GIN (objeto_compra gin_trgm_ops)
    WHERE is_active = TRUE;
```

**NOTA:** O GIST existente em producao NAO e removido automaticamente. A remocao deve ser feita manualmente apos validacao:

```sql
DROP INDEX IF EXISTS idx_bids_objeto_compra_gist;
```

---

## 3. Index em matched_entity_id (TD-DB-07)

### Problema

Tabela `pncp_raw_bids` sem index em `matched_entity_id` forcando nested loop scan em coverage queries com LEFT JOIN.

### Contexto

O index `idx_bids_matched_entity` foi definido na migration 001, mas o schema real de producao pode nao te-lo. Esta migration reforca com `IF NOT EXISTS`.

### Index criado

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bids_matched_entity
    ON pncp_raw_bids (matched_entity_id)
    WHERE matched_entity_id IS NOT NULL;
```

**Partial index:** `WHERE matched_entity_id IS NOT NULL` porque:
1. ~40% dos bids nao tem match — irrelevantes para coverage queries
2. Reduz tamanho do index
3. Melhor selectivity para o planner

**Index composto para match_logging:**

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_match_logging_lookup
    ON pncp_raw_bids (match_method, matched_entity_id)
    WHERE matched_entity_id IS NOT NULL;
```

---

## 4. Decisoes Tecnicas

### IDS: REUSE > ADAPT > CREATE

| Decisao | Tipo | Justificativa |
|---------|------|---------------|
| GIN com gin_trgm_ops | REUSE | Mesmo padrao da migration 013 (pncp_supplier_contracts.objeto_contrato) |
| idx_bids_matched_entity | REUSE | Index ja definido na migration 001, apenas reforcado com IF NOT EXISTS |
| ttl_cleanup_enriched_entities() | CREATE | Funcao nova — sem precedente na base; necessario para TTL |
| CHECK constraints NOT VALID | ADAPT | Adaptado do padrao Postgres para bloqueio zero em producao |

### CREATE INDEX CONCURRENTLY

Todos os indexes usam `CONCURRENTLY` para evitar lock em producao. Importante:
- CONCURRENTLY exige que o comando seja executado fora de transacao
- Cada migration contem apenas um DDL quando usa CONCURRENTLY
- `IF NOT EXISTS` garante re-execucao segura

### Constraints NOT VALID

CHECK constraints foram criadas com `NOT VALID` para:
1. Zero bloqueio em producao (nao valida registros existentes)
2. Validacao gradual: aplica-se apenas a novos inserts/updates
3. Validacao futura opcional: `ALTER TABLE ... VALIDATE CONSTRAINT`

---

## 5. Migrations Dependencias

```
TD-2.1 (schema baseline) ──► TD-2.2 (migrations adaptadas) ──► TD-2.3 (esta)
```

TD-2.3 depende do schema baseline (TD-2.1) porque as migrations criadas aqui precisam ser aplicadas sobre um schema confiavel. As tabelas e colunas referenciadas existem no schema atual.

---

## Referencias

- [Story TD-2.3](../stories/epics/epic-td-001-resolution/story-TD-2.3-normalizacao-constraints.md)
- [Assessment TD-DB-03](./bids-crawler-diagnosis.md) (secao enriched_entities)
- [Assessment TD-DB-06](./query-optimization.md) (secao GIST index)
- [Assessment TD-DB-07](./query-optimization.md) (secao missing indexes)
