# Database Audit — Extra Consultoria

**Data:** 2026-07-13
**Schema snapshot:** `supabase/current-schema.sql` (2026-07-11, v2 baseline)
**Ultima migration:** `006-v3-unified-schema.sql` (2026-07-12, v3 consolidated)
**Database version:** PostgreSQL 18.4 (Ubuntu 18.4-1.pgdg24.04+1)

---

## 1. Security Audit

### 1.1 RLS Coverage

| Tabela | RLS Ativa | Policies | Risco | Notas |
|--------|-----------|----------|-------|-------|
| `sc_public_entities` | NAO | 0 | BAIXO | Dados publicos, sem PII |
| `pncp_raw_bids` | NAO | 0 | BAIXO | Dados de licitacao (publicos por lei) |
| `pncp_supplier_contracts` | NAO | 0 | BAIXO | Dados contratuais publicos |
| `enriched_entities` | NAO | 0 | BAIXO | Cache de API publica |
| `entity_coverage` | NAO | 0 | BAIXO | Metadados internos |
| `coverage_snapshots` | NAO | 0 | BAIXO | Metricas internas |
| `ingestion_runs` | NAO | 0 | BAIXO | Audit trail interno |
| `ingestion_checkpoints` | NAO | 0 | BAIXO | Estado de crawler |

**Avaliacao:** Nao ha RLS policy em nenhuma tabela. Nao ha necessidade atual pois o banco opera como single-user (role `postgres`). Se o banco for exposto via Supabase ou API no futuro, RLS sera necessario para:
- Separar acesso leitura vs escrita
- Prevenir delecao acidental de dados de batch
- Proteger metadados de ingestao (ingestion_runs contem error_message com possivel informacao interna)

### 1.2 Access Patterns

- **Unico role:** `postgres` (superuser)
- **Conexao:** Driver `psycopg2` raw (sem ORM, sem pooler, sem Supabase REST)
- **Porta:** 5432 (default PostgreSQL, nao 54399 como documentado anteriormente)
- **Host:** Local (sem exposicao externa)

### 1.3 Secrets Management

| Risco | Descricao | Localizacao | Severidade |
|-------|-----------|-------------|------------|
| Credencial em texto puro | `postgres:smartlic_local` hardcoded em config/settings.py | `config/settings.py` e scripts Python | **MEDIO** |
| Senha versionada | A credencial esta em arquivos versionados no git | Multiplos scripts | **MEDIO** |

**Recomendacao:** Mover para `.env` file ou `pg_service.conf`. Manter credencial default apenas para desenvolvimento local. Nunca usar em staging/production.

### 1.4 SQL Injection Risk

- **Baixo risco** — O codigo Python usa `psycopg2` com query parameterized (`%s` placeholders) em `datalake_helper.py` e `local_datalake.py`.
- Funcoes PL/pgSQL usam `ON CONFLICT` e `jsonb_array_elements` com dados internos (sem input direto do usuario).
- Risco moderado se houver endpoints HTTP que aceitem SQL params sem sanitizacao.

**Avaliacao:** Aceitavel para uso atual.

---

## 2. Performance Audit

### 2.1 Table Sizing (estimado)

| Tabela | Registros (est.) | Storage (est.) | Indexes |
|--------|-----------------|----------------|---------|
| `pncp_raw_bids` | ~200K | ~650 MB dados + ~400 MB indices | 15 |
| `pncp_supplier_contracts` | ~3.7M | ~2.2 GB dados + ~1.3 GB indices | 8 |
| `enriched_entities` | ~14K | < 1 MB | 2 |
| `sc_public_entities` | ~2K | < 1 MB | 6 |
| `entity_coverage` | ~4K | < 1 MB | 4 |
| `coverage_snapshots` | variavel | < 1 MB | 3 |
| `ingestion_runs` | ~5 | < 1 MB | 2 |
| `ingestion_checkpoints` | 0 | < 1 MB | 1 |

### 2.2 Index Coverage Analysis

**pncp_raw_bids (15 indexes):** Cobertura boa para os principais padroes de consulta. Destaques:

| Index | Coverage | Notas |
|-------|----------|-------|
| `idx_bids_tsv` (GIN) | Full-text search | Essencial para `search_datalake()` |
| `idx_bids_uf_data` (BTREE) | Filtro UF + data | Cobre o padrao mais comum |
| `idx_bids_modalidade` (BTREE) | Filtro modalidade | Composto com data |
| `idx_bids_active` (BTREE, partial) | Filtro ativos | Partial index reduz tamanho |
| `idx_bids_matched_entity` (BTREE, partial) | Join coverage | Partial index, eficiente |
| `idx_bids_valor` (BTREE) | Filtro valor | Index separado, necessario para range scans |
| `idx_bids_encerramento` (BTREE, partial) | Filtro encerramento | Partial, IS NOT NULL |
| `idx_bids_source` (BTREE) | Filtro fonte | Baixa cardinalidade (~5 valores), util para cobertura |

**Potenciais indexes faltantes:**
- `idx_bids_objeto_trgm` nao existe no v2 baseline (mas esta no v1 divergente) — sem trigram fallback. A funcao `search_datalake` usa ILIKE como fallback, que faz full table scan.
- `idx_bids_objeto_trgm` seria necessario se o ILIKE fallback for usado com frequencia.

**pncp_supplier_contracts (8 indexes):** Cobertura adequada.

| Index | Coverage | Notas |
|-------|----------|-------|
| `idx_psc_objeto_trgm` (GIN) | Trigram search | Essencial para buscas em `objeto_contrato` |
| `idx_psc_fornecedor` (BTREE) | Lookup fornecedor | Composto com data_publicacao DESC |
| `idx_psc_orgao` (BTREE) | Lookup orgao | Index simples |
| `idx_psc_uf` (BTREE) | Filtro UF | Composto com data |
| `idx_psc_valor` (BTREE) | Filtro valor | Index separado |
| `idx_psc_data` (BTREE) | Ordenacao data | DESC para mais recentes primeiro |

**Potenciais indexes faltantes:**
- Nao ha partial index `is_active` em `pncp_supplier_contracts` (diferente de `pncp_raw_bids`) — queries que filtram por ativos podem escanear mais registros.

**sc_public_entities (6 indexes):** Cobertura excessiva para 2K registros.

| Index | Necessidade | Notas |
|-------|-------------|-------|
| `idx_spe_cnpj` | Util | Lookup por CNPJ 8-digit |
| `idx_spe_ibge` | Util | Join por codigo IBGE |
| `idx_spe_municipio` | Moderada | 293 municipios, baixa cardinalidade |
| `idx_spe_natureza` | Moderada | ~10 valores distintos |
| `idx_spe_raio` | Util | Filtro geografico |
| `idx_spe_municipio` duplicata da funcionalidade de `idx_spe_ibge` | — | Ambos usados em contextos diferentes |

**Nota:** Para 2K registros, indexes extras tem custo negligible e sao justificaveis pela frequencia das queries.

### 2.3 Full-Text Search Performance

A funcao `search_datalake` usa:
1. `ts_rank(b.tsv, to_tsquery('portuguese', p_tsquery))` — usa GIN index `idx_bids_tsv`
2. Fallback ILIKE: `b.objeto_compra ILIKE '%' || p_tsquery || '%'` — **sem index de trigram**, faz full table scan

**Recomendacao:** Adicionar index GIN trigram em `objeto_compra` se o ILIKE fallback for usado com frequencia.

### 2.4 Coverage Query Performance

O trigger `trg_bids_coverage` executa `update_entity_coverage()` a cada INSERT em `pncp_raw_bids`. A funcao faz:
1. SELECT em `sc_public_entities` por `id` — usa PK (rapido)
2. INSERT ... ON CONFLICT em `entity_coverage` — usa PK composto (rapido)

**Avaliacao:** Performance aceitavel para volume atual (~200K registros). Monitorar se volume aumentar > 1M.

### 2.5 Batch Upsert Performance

`upsert_pncp_raw_bids` e `upsert_pncp_supplier_contracts` usam **iteracao row-by-row** com `FOR rec IN SELECT * FROM jsonb_array_elements(p_records)`. Esta abordagem e:
- 1 round-trip por registro dentro da funcao (pl/pgsql loop)
- ~5-10x mais lento que abordagem set-based com `jsonb_to_recordset()` + INSERT ... ON CONFLICT

**Impacto:** MEDIO para `pncp_raw_bids` (200K registros). BAIXO para volume atual, mas pode ser gargalo com crescimentos.

### 2.6 Anti-patterns

1. **GIN index em `objeto_contrato` ja existe** (diferente da auditoria anterior que reportava como ausente) — `idx_psc_objeto_trgm` esta presente no v2 baseline.
2. **Row-by-row upsert** — `upsert_pncp_raw_bids` e `upsert_pncp_supplier_contracts` usam loop PL/pgSQL em vez de set-based operation.
3. **Sem index ILIKE em `pncp_raw_bids.objeto_compra`** — fallback `ILIKE '%query%'` na `search_datalake` nao e coberto por index.
4. **Datas como DATE vs TIMESTAMPTZ** — `data_publicacao`, `data_abertura`, `data_encerramento` sao DATE em `pncp_raw_bids`, mas TIMESTAMPTZ no `search_datalake` e em funcoes de coverage. Consistencia e recomendavel.
5. **`pncp_raw_bids.content_hash` UNIQUE sem partial** — o UNIQUE constraint permite apenas um registro com determinado hash, mesmo que `is_active = false`. Se houver re-insercao de registros previamente deletados, o upsert falha (faz NOTHING).

---

## 3. Data Integrity Audit

### 3.1 Constraints Analysis

| Tabela | PK | FK | UNIQUE | CHECK | NOT NULL coverage |
|--------|----|----|--------|-------|-------------------|
| `sc_public_entities` | OK | 0 | 0 | 0 | razao_social, cnpj_8, is_active, raio_200km |
| `pncp_raw_bids` | OK | 1 (SET NULL) | 1 | 0 | is_active, source |
| `pncp_supplier_contracts` | OK | 0 | 1 | 0 | source |
| `enriched_entities` | OK | 0 | 0 | 0 | cnpj |
| `entity_coverage` | OK | 1 (CASCADE) | 0 | 0 | entity_id, source |
| `coverage_snapshots` | OK | 0 | 0 | 0 | snapshot_date, source |
| `ingestion_runs` | OK | 0 | 0 | 0 | source, status |
| `ingestion_checkpoints` | OK | 0 | 0 | 0 | source, scope_key |

**Observacoes:**

1. **Ausencia de CHECK constraints** — Nenhuma tabela tem CHECK constraints para validar dominio de dados. Exemplos:
   - `esfera_id` deveria ser restrito a 1,2,3,4 (ou NULL)
   - `source` deveria ter valores conhecidos (`pncp`, `dom_sc`, `pcp`, etc.)
   - `status` em `ingestion_runs` deveria ser `running`, `completed`, `failed`
   - `natureza_juridica` em `sc_public_entities` sem controle de dominio

2. **UNIQUE ausente em `sc_public_entities.cnpj_8`** — Ha index BTREE em `cnpj_8`, mas nao UNIQUE constraint. Isso permite duplicatas de CNPJ raiz, o que e indesejavel para matching de entidades.

3. **`pncp_raw_bids` com poucos NOT NULL** — Apenas `is_active`, `source`, `ingested_at`, `updated_at` sao NOT NULL. Colunas criticas como `objeto_compra`, `data_publicacao`, `uf` sao NULLABLE.

4. **`objeto_compra` NOT NULL nao e enforceado** — No schema real, `objeto_compra` aceita NULL. Se o upsert receber um registro sem `objeto_compra`, o `to_tsvector('portuguese', NULL)` retorna NULL, nao erro.

### 3.2 Orphaned Data Risks

| Relacao | Risco | Mitigacao |
|---------|-------|-----------|
| `entity_coverage.entity_id` -> `sc_public_entities.id` | BAIXO | ON DELETE CASCADE |
| `pncp_raw_bids.matched_entity_id` -> `sc_public_entities.id` | BAIXO | ON DELETE SET NULL |
| `pncp_raw_bids` sem FK para `sc_public_entities` alem de `matched_entity_id` | MEDIO | `orgao_cnpj` nao tem FK — se o CNPJ nao existir em `sc_public_entities`, a bid fica orfa |
| `pncp_supplier_contracts` sem FK para `pncp_raw_bids` ou `sc_public_entities` | MEDIO | Contracts sao independentes, sem cascata |

### 3.3 Coverage Data Quality

O sistema de coverage depende de:
1. Trigger `trg_bids_coverage` (AFTER INSERT em `pncp_raw_bids`)
2. Trigger `trg_bids_coverage_update` (AFTER UPDATE de `matched_entity_id`)
3. Funcao `generate_coverage_snapshot` (timer semanal)

**Problema:** Se houver bulk INSERT que nao passe pelos triggers (ex: `INSERT ... SELECT` direto, ou `COPY`), o `entity_coverage` NAO e atualizado. A funcao `upsert_pncp_raw_bids` passa pelos triggers corretamente.

**Recomendacao:** Adicionar job periodico de reconciliacao de coverage para capturar registros que possam ter bypassado os triggers.

---

## 4. Migration Health

### 4.1 Migration Track Analysis

| Track | Arquivos | Status | Problema |
|-------|----------|--------|----------|
| v1 (db/migrations/) | 001-014 | ARCHIVED | Totalmente divergente do schema real. DDL aplicado diretamente sem atualizar migrations. |
| v2 (supabase/migrations/) | _migrations, 001-v2 a 005-v2 | BASELINE | Representa o schema real capturado via pg_dump em 2026-07-11. Todos os objetos existentes estao cobertos. 002-005 adicionam coverage, views, snapshots, match_logging. |
| v3 (supabase/migrations/) | 006-v3 | PENDING | Consolidacao de tabelas faltantes dos v1 021-028. 10 novas tabelas, 11 novas colunas, 6 novas views, 4 novas funcoes. |

### 4.2 Migration Status (v2)

| Migration | Objetivo | Status no banco real |
|-----------|----------|---------------------|
| `_migrations.sql` | Tabela de tracking | Aplicada (presente no schema) |
| `001-v2_initial_schema.sql` | Baseline completo | Aplicada (base do schema) |
| `002-v2_entity_coverage.sql` | Coverage table + triggers | Aplicada (presente no schema) |
| `003-v2_coverage_views.sql` | Views de coverage | Aplicada (presente no schema) |
| `004-v2_coverage_snapshots.sql` | Snapshots + function | Aplicada (presente no schema) |
| `005-v2_match_logging.sql` | Colunas de match logging | **PARCIAL** — colunas `match_method`, `match_score`, `match_confidence` NAO estao no schema real (current-schema.sql nao as inclui) |

### 4.3 Migration Gaps

1. **005-v2 nao aplicada totalmente:** As colunas `match_method`, `match_score`, `match_confidence` nao estao no `current-schema.sql`. Possivelmente foram adicionadas depois ou a migration e posterior ao snapshot.

2. **006-v3 nao aplicada:** A migration unificada v3 (10 tabelas) nao foi aplicada ao banco real. Depende de verificacao manual.

3. **Ordem de dependencia v2:** A migration `003-v2` DEPENDE de `005-v2` (match_logging), mas a numeracao sequencial coloca 003 antes de 005. Isso e uma armadilha de aplicacao.

4. **Nao ha ordem de rollback documentada:** Apenas o checksum e a migration sao registrados, mas nao ha script de rollback alem do campo `rollback_sql` na tabela `_migrations`.

---

## 5. Technical Debt Inventory

| ID | Debito | Severidade | Objeto | Impacto | Esforco | Recomendacao |
|----|--------|------------|--------|---------|---------|-------------|
| DT-01 | Colunas match_logging (match_method, match_score, match_confidence) ausentes no schema real | **HIGH** | `pncp_raw_bids` | Match cascade nao registra qualidade dos matches. Sem audit trail de matching. Impossivel depurar falsos positivos. | BAIXO | Executar migration 005-v2 ou adicionar colunas manualmente |
| DT-02 | 10 tabelas v3 nao aplicadas ao banco | **HIGH** | Multiplas | Funcionalidades de oportunidade, engenharia e hierarquia ausentes. Oportunity intel pipeline bloqueado. | MEDIO | Aplicar migration 006-v3 apos validacao |
| DT-03 | Ordem de dependencia v2 incorreta (003 depende de 005) | **MEDIUM** | 003-v2, 005-v2 | Migration 003-v2 referencia match_method que so e criada em 005-v2. Aplicacao fora de ordem quebra. | BAIXO | Renumerar migrations para ordem topologica correta ou adicionar IF EXISTS nas views |
| DT-04 | upsert_pncp_raw_bids row-by-row | **MEDIUM** | Funcao | Performance subotima para grandes batches. Loop PL/pgSQL ~5-10x mais lento que set-based. | MEDIO | Re-escrever usando `jsonb_to_recordset()` + INSERT ... ON CONFLICT |
| DT-05 | upsert_pncp_supplier_contracts row-by-row | **MEDIUM** | Funcao | Mesmo problema do DT-04, aplicado a tabela de 3.7M registros. | MEDIO | Re-escrever usando `jsonb_to_recordset()` + INSERT ... ON CONFLICT |
| DT-06 | Sem UNIQUE constraint em `sc_public_entities.cnpj_8` | **MEDIUM** | `sc_public_entities` | Permite duplicatas de CNPJ raiz, comprometendo matching de entidades. | BAIXO | Adicionar UNIQUE INDEX ou UNIQUE constraint |
| DT-07 | Senha hardcoded em config/settings.py | **MEDIUM** | `config/settings.py` | Exposicao de credencial em texto puro versionada no git. | BAIXO | Migrar para `.env` ou `pg_service.conf` |
| DT-08 | Sem CHECK constraint para `esfera_id` | **LOW** | `pncp_raw_bids` | Dominio de 1,2,3,4 nao validado. Valores invalidos passam sem erro. | BAIXO | Adicionar CHECK (esfera_id IS NULL OR esfera_id IN (1,2,3,4)) |
| DT-09 | Sem CHECK constraint para `source` | **LOW** | Multiplas tabelas | Fontes invalidas (typos, valores inesperados) nao sao rejeitadas. | BAIXO | Adicionar CHECK em todas as tabelas com coluna source |
| DT-10 | Sem CHECK constraint para `status` em `ingestion_runs` | **LOW** | `ingestion_runs` | Status invalidos podem ser inseridos sem erro. | BAIXO | Adicionar CHECK (status IN ('running','completed','failed')) |
| DT-11 | Funcao `search_datalake` com fallback ILIKE sem index de trigram | **LOW** | `pncp_raw_bids` | Fallback ILIKE faz full table scan. Sem index GIN/GIST em `objeto_compra`. | BAIXO | Adicionar GIN trigram index se fallback for usado com frequencia |
| DT-12 | Data types inconsistentes (DATE vs TIMESTAMPTZ) | **LOW** | `pncp_raw_bids` | `data_publicacao`, `data_abertura`, `data_encerramento` sao DATE, mas algumas funcoes esperam TIMESTAMPTZ. | BAIXO | Consolidar para DATE (dados de licitacao nao tem componente de hora) |
| DT-13 | ingestion_checkpoints vazia e sem uso | **LOW** | `ingestion_checkpoints` | Estrutura existe mas nunca populada. Crawlers nao usam checkpoint. | BAIXO | Integrar checkpoints nos crawlers ou remover a tabela |
| DT-14 | Nao ha coverage reconciliation periodica | **MEDIUM** | `entity_coverage` | Bulk operations que bypassam triggers nao atualizam coverage. Dados ficam inconsistentes. | MEDIO | Adicionar job schedule que executa recalculacao de coverage |
| DT-15 | `pncp_raw_bids.content_hash` UNIQUE sem partial para `is_active` | **LOW** | `pncp_raw_bids` | Re-insercao de registro previamente soft-deletado falha (ON CONFLICT DO NOTHING). | BAIXO | Criar UNIQUE parcial `UNIQUE(content_hash) WHERE is_active = true` |
| DT-16 | GIN index `idx_psc_objeto_trgm` ausente no v2 baseline | **MEDIUM** | `pncp_supplier_contracts` | O index trigram existe no schema real, mas nao esta na migration v2 baseline. Divergencia entre migration e banco. | BAIXO | Adicionar criacao do index GIN na migration 001-v2 ou 005-v2 |
| DT-17 | Colunas `match_method`, `match_score`, `match_confidence` em 005-v2 mas ausentes no schema real | **HIGH** | 005-v2 migration | Migration define colunas que nao existem no banco. Ou a migration nunca foi aplicada, ou as colunas foram removidas. | BAIXO | Verificar estado real do banco e aplicar ou remover da migration |

---

## 6. Summary Dashboard

| Metrica | Valor |
|---------|-------|
| Tabelas (v2 baseline) | 8 |
| Tabelas (v3 pendente) | +10 (total 18) |
| Indexes | 40 (15 + 8 + 2 + 6 + 4 + 3 + 2 + 0) |
| Funcoes customizadas | 8 |
| Triggers | 3 |
| Views | 4 (v2) + 6 (v3) = 10 |
| RLS Policies | 0 |
| Roles de aplicacao | 1 (superuser) |
| Extensoes | 2 (pg_trgm, uuid-ossp) |
| FKs | 2 (v2) + 6 (v3) = 8 |
| Total debitos identificados | 17 |
| Debitos CRITICAL | 0 |
| Debitos HIGH | 3 (DT-01, DT-02, DT-17) |
| Debitos MEDIUM | 6 (DT-03, DT-04, DT-05, DT-06, DT-07, DT-14) |
| Debitos LOW | 8 |

---

## 7. Prioritized Recommendations

### Imediatas (Criticas / High)

1. **[HIGH] Verificar e aplicar migration 005-v2 (match_logging):** As colunas `match_method`, `match_score`, `match_confidence` sao necessarias para audit trail de matching. Verificar se ja existem no banco e aplicar se necessario.

2. **[HIGH] Aplicar migration 006-v3 (unified schema):** Desbloqueia as funcionalidades de opportunity intel, engenharia civil e coverage evidence. Exige validacao previa em ambiente de staging.

3. **[HIGH] Validar estado real das migrations v2:** Confirmar se 005-v2 foi aplicada ao banco ou se o snapshot current-schema.sql e anterior a ela.

### Curto Prazo (Medium)

4. Adicionar UNIQUE constraint em `sc_public_entities.cnpj_8` para prevenir duplicatas no matching.

5. Corrigir ordem de dependencia entre 003-v2 e 005-v2 na documentacao ou renumerar migrations.

6. Re-escrever `upsert_pncp_raw_bids` e `upsert_pncp_supplier_contracts` para set-based.

7. Adicionar job de reconciliacao de coverage periodico.

8. Migrar credencial do banco para `.env`.

### Medio Prazo (Low)

9. Adicionar CHECK constraints para dominios: `esfera_id`, `source`, `status`.

10. Consolidar tipos DATE vs TIMESTAMPTZ nas colunas de data.

11. Decidir destino de `ingestion_checkpoints`.

12. Adicionar GIN trigram index para fallback ILIKE em `objeto_compra`.

---

*Audit gerado em 2026-07-13. Schema snapshot de referencia: `supabase/current-schema.sql`. Migration tracks: v1 (archived), v2 (baseline), v3 (pending consolidation).*
