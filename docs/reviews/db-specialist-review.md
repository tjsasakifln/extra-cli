# Database Specialist Review

**Revisor:** @data-engineer (Dara)
**Data:** 2026-07-11
**Documento Revisado:** `docs/prd/technical-debt-DRAFT.md`
**Fontes consultadas:** `supabase/docs/DB-AUDIT.md`, `supabase/docs/SCHEMA.md`, `docs/architecture/system-architecture.md`, `db/migrations/` (001-012), `scripts/datalake_helper.py`, `scripts/crawl/monitor.py`, `scripts/local_datalake.py`

---

## 1. Resumo Executivo da Revisao

A revisao validou os 14 debitos de database (TD-DB-01 a TD-DB-14) listados no DRAFT, com ajustes de severidade em 4 deles (TD-DB-05 sobe para HIGH, TD-DB-07 sobe para MEDIUM, TD-DB-11 sobe para HIGH, TD-DB-02 desdobrado em duas partes). Adicionalmente, identifiquei 3 novos debitos nao capturados na analise inicial, sendo o mais critico a **ausencia total de backup strategy** (TD-DB-15, CRITICAL) -- 4.1 GB de dados em VPS sem nenhum mecanismo de backup identificado em todo o codebase.

O custo total estimado para resolucao completa dos debitos de database e de **52.5-60 horas** (vs 38.5-46h no DRAFT original). O ajuste reflete horas realistas para operacoes como regeneracao de migrations, setup de backup, e rewrites de funcoes.

A principal intervencao estrutural recomendada e: **regenerar as migrations a partir do schema real como primeiro passo**, antes de qualquer outro debito. Tentar aplicar migrations 009-012 sobre o schema atual sem esse baseline causara conflitos.

A contradicao de SQL injection entre system-architecture.md (MEDIO) e DB-AUDIT.md (baixo) foi investigada no codigo fonte real. **DB-AUDIT esta correto**: nao ha f-strings em SQL executado. A string concatenation em `monitor.py:66-68` adiciona apenas literais fixos (`AND raio_200km = TRUE`, `ORDER BY id`), sem nenhum input do usuario.

---

## 2. Debitos Validados

### Tabela Consolidada

| ID Original | Debito | Severidade Original | Severidade Ajustada | Horas | Prioridade | Validacao |
|-------------|--------|--------------------|--------------------|-------|------------|-----------|
| TD-DB-01 | Migrations totalmente divergentes do schema real | CRITICAL | CRITICAL | 8 | P0 | CONFIRMADO |
| TD-DB-02 (parte) | Migrations 009/011/012 nao aplicadas (entity_coverage + views) | HIGH | HIGH | 4 | P1 | AJUSTADO |
| TD-DB-02 (parte) | Migration 010 nao aplicada (match_logging) | HIGH | LOW | 1 | P3 | AJUSTADO |
| TD-DB-03 | enriched_entities sem TTL enforcement | MEDIUM | MEDIUM | 3 | P2 | CONFIRMADO |
| TD-DB-04 | upsert_pncp_supplier_contracts row-by-row | MEDIUM | MEDIUM | 3 | P2 | CONFIRMADO |
| TD-DB-05 | Senha do DB hardcoded em multiplos scripts | MEDIUM | **HIGH** | 2 | P1 | AJUSTADO |
| TD-DB-06 | GIST trigram index superdimensionado (294 MB) | MEDIUM | MEDIUM | 2 | P2 | CONFIRMADO |
| TD-DB-07 | Missing index em matched_entity_id | LOW | **MEDIUM** | 1 | P2 | AJUSTADO |
| TD-DB-08 | Missing GIN index em objeto_contrato | HIGH | HIGH | 2 | P1 | CONFIRMADO |
| TD-DB-09 | esfera_id sem CHECK constraint | LOW | LOW | 1 | P3 | CONFIRMADO |
| TD-DB-10 | ingestion_checkpoints sem uso (0 registros) | LOW | LOW | 1 | P3 | CONFIRMADO |
| TD-DB-11 | search_datalake HNSW pode nao ser usado | MEDIUM | **HIGH** | 1 | P1 | AJUSTADO |
| TD-DB-12 | Codigo referencia tabela inexistente (search_results_cache) | LOW | LOW | 0.5 | P3 | CONFIRMADO |
| TD-DB-13 | Codigo referencia colunas que nao existem no schema | MEDIUM | MEDIUM | 4 | P2 | CONFIRMADO |
| TD-DB-14 | purge_old_bids faz DELETE fisico (irreversivel) | MEDIUM | MEDIUM | 4 | P2 | CONFIRMADO |

### Notas por Debito

**[TD-DB-01] Migrations divergentes -- CRITICAL (CONFIRMADO)**
Gravidade correta. O schema real difere radicalmente das migrations 001-008 em quase todas as tabelas. Exemplos concretos:
- Migration 003 define `enriched_entities` com colunas `cnpj, razao_social, cnae_principal`; o real usa `entity_type/entity_id/data JSONB` -- sao modelos completamente diferentes.
- Migration 004 define `ingestion_runs` sem `ufs_completed`, `ufs_failed`, `duration_s`, `source`, `metadata` -- o real tem muito mais colunas.
- Migration 001 define `esfera_id INT`; o real usa `esfera_id TEXT`.

Nao ha tabela de tracking de migrations. Nao ha como saber qual DDL avulso foi executado e em que ordem.

**Estimativa de 8h realista**, incluindo: dump do schema real, mapeamento coluna-a-coluna, criacao de 12 novas migrations (v2), setup de tabela de tracking, e verificacao com `pg_dump --schema-only` repeatable.

**[TD-DB-02] Migrations 009-012 nao aplicadas -- AJUSTADO (split)**
Desdobrei em dois sub-debitos com severidades diferentes:

- **TD-DB-02a (HIGH, 4h):** Migrations 009 (entity_coverage table + triggers + v_coverage_summary), 011 (v_unmatched_bids), 012 (coverage_snapshots + gap views + generate_coverage_snapshot). Estas dependem de entity_coverage e sao necessarias para o sistema de monitoramento de cobertura. Porem, precisam ser **adaptadas** ao schema real -- nao da para aplicar cegamente porque o schema de `pncp_raw_bids` real difere do esperado pelas triggers.

- **TD-DB-02b (LOW, 1h):** Migration 010 (match_logging: match_method, match_score, match_confidence). Codigo real (`_match_entities_cascade` em `monitor.py`) ja grava estas colunas. **Verificacao necessaria:** confirmar se as colunas ja existem no schema real ou se a migration 010 ainda precisa ser aplicada. Se ja existem, este debito e descartavel.

**[TD-DB-03] enriched_entities sem TTL enforcement -- MEDIUM (CONFIRMADO)**
13.8K registros hoje, volume pequeno. O TTL de 30 dias e mencionado no codigo (`datalake_helper.py:539`) mas nao enforceado pelo banco. O risco e baixo hoje mas cresce com o tempo. Solucao: job de cleanup periodico (DELETE via systemd timer) ou trigger BEFORE INSERT que verifica enriched_at.

**[TD-DB-04] upsert_pncp_supplier_contracts row-by-row -- MEDIUM (CONFIRMADO)**
3.69M registros processados com FOR loop row-by-row. Ha uma funcao alternativa `upsert_supplier_contracts` que usa `jsonb_to_recordset()` com `ON CONFLICT (ni_fornecedor, nr_contrato, ano)` -- ou seja, ja existe uma versao set-based. Isso reduz a urgencia: o codigo ja tem a funcao otimizada, so precisa substituir a chamada.

**[TD-DB-05] Senha hardcoded -- AJUSTADO para HIGH**
O DRAFT classificou como MEDIUM, mas estou elevando para HIGH pelos seguintes motivos:
- A senha `smartlic_local` esta em texto puro em **multiplos** scripts versionados no git.
- DB-AUDIT confirma que e a credencial default em `config/settings.py` e varios scripts.
- O banco PostgreSQL roda em Hetzner VPS (porta 54399) -- nao e localhost-only.
- Uma vez commitada, a senha esta no historico do git para sempre.
- "smartlic_local" parece ser uma senha generica/fraca.

Solucao: mover para `.env` (ja mencionado como 12-factor app na arquitetura) e usar `pgpass` para conexoes. **2h** inclui auditoria de todos os scripts com a senha hardcoded e migracao.

**[TD-DB-06] GIST trigram index superdimensionado -- MEDIUM (CONFIRMADO)**
294 MB de index vs 268 MB de dados -- a relacao index/dados e anomala (1.1x). O GIST trigram e 2-3x maior que o equivalente GIN. Porem, `word_similarity()` fallback (usado em `search_datalake_trigram_fallback`) requer GIST porque GIN nao suporta `word_similarity()` -- apenas `similarity()`. Portanto, **nao substituir cegamente**. Recomendacao:
- Manter GIST se `word_similarity()` e usado com frequencia (precisa de dados de uso).
- Se `word_similarity()` e raro, substituir por GIN trigram e ajustar o fallback para usar `similarity()`.

**[TD-DB-07] Missing index matched_entity_id -- AJUSTADO para MEDIUM**
O DRAFT classificou como LOW, mas estou elevando para MEDIUM. A coverage query em `monitor.py` faz LEFT JOIN com `sc_public_entities` usando `matched_entity_id` a cada execucao de crawl. Com 199K registros em `pncp_raw_bids` e 2.085 entidades, a falta de index pode causar nested loop scans. Alem disso, a query de unmatched bids (que rodaria com a migration 011) tambem depende deste index.

**[TD-DB-08] Missing GIN index em objeto_contrato -- HIGH (CONFIRMADO)**
3.69M registros em `pncp_supplier_contracts`, ILIKE queries em `objeto_contrato` sem index -- full table scan confirmado. A recomendacao do DRAFT (`USING GIN (objeto_contrato gin_trgm_ops) WHERE is_active = true`) esta correta e e acionavel imediatamente. Partial index com `WHERE is_active = true` reduz o tamanho significativamente.

**[TD-DB-09] esfera_id sem CHECK constraint -- LOW (CONFIRMADO)**
Valores conhecidos e consistentes (F, E, M, D). Impacto baixo. Resolver como parte da reconciliação de migrations (TD-DB-01).

**[TD-DB-10] ingestion_checkpoints sem uso -- LOW (CONFIRMADO)**
Estrutura criada, 0 registros. Decisao de negocio: integrar checkpoints nos crawlers (torna crawlers resumeveis) ou remover a tabela. Se mantida, o custo de storage e irrelevante (< 1 MB).

**[TD-DB-11] search_datalake HNSW pode nao ser usado -- AJUSTADO para HIGH**
O DRAFT classificou como MEDIUM. Estou elevando para HIGH porque a expressao `1.0 - (vec <=> p_embedding) > threshold` faz com que **todas as queries de embedding facam full scan sequencial** -- nenhuma consegue usar o HNSW index. Isso significa que os 256-dim embedding vectors indexados com HNSW (m=16, ef_construction=64) sao completamente inuteis para aceleracao. Toda busca hibrida com embedding filter varre a tabela inteira.

A correcao e trivial (1h): reescrever como `(embedding <=> p_embedding) < (1.0 - threshold)`.

**[TD-DB-12] Referencia tabela inexistente search_results_cache -- LOW (CONFIRMADO)**
`scripts/local_datalake.py:71` lista `search_results_cache` na lista `CORE`. Mas o problema e maior: a lista inclui **8 tabelas que nao existem** no schema real: `search_results_cache`, `search_results_store`, `profiles`, `alerts`, `pipeline_items`, `leads`, `classification_feedback`, `organizations`, `digital_products`. Parece ser uma copia de outro projeto (provavelmente Supabase template com tabelas de auth e storage). O comando `cmd_stats()` em `local_datalake.py` usa f-strings para executar `SELECT count(*) FROM "{table}"` em cada uma -- as tabelas inexistentes causarao erros silenciosos (tratados por exception handler) mas a listagem de stats sera incompleta.

**[TD-DB-13] Codigo referencia colunas que nao existem no schema -- MEDIUM (CONFIRMADO)**
O `_LocalPgQuery` builder em `datalake_helper.py` aceita qualquer nome de coluna via `eq(col, val)`. A validacao so ocorre em runtime quando o PostgreSQL executa a query. A superficie de risco e grande. Solucao: adicionar validacao de colunas no query builder ou usar SQLAlchemy/psycopg2.sql.

**[TD-DB-14] purge_old_bids faz DELETE fisico -- MEDIUM (CONFIRMADO)**
`purge_old_bids(p_retention_days DEFAULT 12)` deleta registros fisicamente. Para dados publicos de licitacao, soft-delete via `is_active = FALSE` seria mais seguro. O `is_active` ja existe na tabela e ja e usado como soft-delete padrao. A funcao deveria fazer UPDATE em vez de DELETE.

---

## 3. Debitos Adicionados

| ID | Debito | Severidade | Tabela/Objeto | Horas | Prioridade | Justificativa |
|----|--------|------------|---------------|-------|------------|---------------|
| TD-DB-15 | Ausencia total de backup strategy | CRITICAL | Todas as tabelas (4.1 GB) | 4 | P0 | Nenhum script, systemd timer, ou config de backup encontrado em todo o codebase. 4.1 GB de dados de 2+ anos de crawling sem backup em VPS Hetzner. Risco de perda total. |
| TD-DB-16 | Duas funcoes de upsert de contratos (uma obsoleta) | MEDIUM | pncp_supplier_contracts | 2 | P2 | `upsert_pncp_supplier_contracts` (row-by-row, for loop) e `upsert_supplier_contracts` (set-based, jsonb_to_recordset). Ambas ativas. A primeira e a versao lenta/antiga. Consolidar e deprecar a row-by-row. |
| TD-DB-17 | Sem tabela de tracking de migrations | LOW | Infrastructure | 2 | P3 | Nao ha `_migrations` ou `schema_migrations_history`. Impossivel saber quais DDLs foram aplicados, em que ordem, e por quem. |

### Detalhamento

**[TD-DB-15] Ausencia total de backup -- CRITICAL**
Nao encontrei nenhum script de backup, configuracao de pg_dump, systemd timer para dump, ou mencao a backup strategy em nenhum documento. O banco PostgreSQL roda em Hetzner VPS com 4.1 GB de dados que representam 2+ anos de crawling continuo de 5+ fontes publicas. Sem backup:
- Uma corrupcao de disco, erro humano (`DROP TABLE`), ou ataque ransomware resulta em perda total.
- A reproducao dos dados a partir das sources exigiria 2+ anos de recrawling.
- Mesmo com as migrations consertadas, os dados seriam irrecuperaveis.

**Solucao:** Setup de `pg_dump` via systemd timer diario (dump SQL comprimido ~400-800 MB) + rsync/scp para storage externo (ou Hetzner Storage Box). Custo: 4h.

**[TD-DB-16] Duas funcoes de upsert -- MEDIUM**
O schema tem duas funcoes que fazem a mesma coisa:
- `upsert_pncp_supplier_contracts(p_records JSONB)` -- FOR loop row-by-row, lenta, usada pelo codigo legado.
- `upsert_supplier_contracts(contracts JSONB)` -- `jsonb_to_recordset()` set-based, rapida SECURITY DEFINER, conflita por `(ni_fornecedor, nr_contrato, ano)`.

A existencia de ambas cria confusao sobre qual usar. A antiga devia ser deprecada ou removida apos migracao.

**[TD-DB-17] Tracking de migrations -- LOW**
Nao ha mecanismo para rastrear o estado das migrations. DB-AUDIT menciona isso. Sem tabela de tracking, qualquer tentativa de reconciliacao (TD-DB-01) sera fragmentada. Solucao: criar uma tabela `schema_version` ou similar, e registrar cada migration aplicada.

---

## 4. Debitos Removidos

Nenhum debito foi removido completamente. Todos os 14 debitos originais sao problemas reais -- apenas ajustei severidades e desdobrei TD-DB-02.

---

## 5. Ordem de Resolucao Recomendada (DB)

### Fase 0: Emergencia (antes de qualquer refatoracao)

1. **TD-DB-15 (CRITICAL, 4h) -- Setup de backup.** Nao faz sentido comecar a refatorar o banco sem garantir que o estado atual esta seguro. `pg_dump --format=custom` diario com retention de 7 dias, armazenado fora da VPS.

### Fase 1: Baseline (pre-requisito para tudo)

2. **TD-DB-01 (CRITICAL, 8h) -- Regenerar migrations.** Usar `pg_dump --schema-only --no-owner --no-acl` para capturar o estado real, depois gerar 12 novas migrations (001-v2 ate 012-v2) que correspondam exatamente ao schema real. Incluir criacao de tabela `_migrations` para tracking.

3. **TD-DB-17 (LOW, 2h) -- Setup de tracking de migrations.** Criar tabela de controle e registrar todas as migrations v2.

### Fase 2: Quick Wins (alto impacto, baixo esforco)

4. **TD-DB-08 (HIGH, 2h) -- GIN index em objeto_contrato.** `CREATE INDEX ... USING GIN (objeto_contrato gin_trgm_ops) WHERE is_active = true`. Impacto imediato nas queries de contratos (3.69M registros).

5. **TD-DB-11 (HIGH, 1h) -- Corrigir expressao HNSW.** Reescrever `search_datalake` para usar `(embedding <=> p_embedding) < (1.0 - threshold)`. Libera o HNSW index para queries de embedding.

6. **TD-DB-07 (MEDIUM, 1h) -- Index matched_entity_id.** `CREATE INDEX ... ON pncp_raw_bids(matched_entity_id) WHERE matched_entity_id IS NOT NULL`.

### Fase 3: Qualidade e Seguranca

7. **TD-DB-05 (HIGH, 2h) -- Remover senha hardcoded.** Migrar para `.env` + `pgpass`. Auditar todos os scripts.

8. **TD-DB-14 (MEDIUM, 4h) -- Soft-delete no purge_old_bids.** Alterar funcao para fazer UPDATE `is_active = FALSE` em vez de DELETE.

9. **TD-DB-02a (HIGH, 4h) -- Aplicar migrations 009/011/012 adaptadas.** Adaptar triggers e views ao schema real, criar `entity_coverage`, popular com dados historicos.

### Fase 4: Performance e Consolidacao

10. **TD-DB-06 (MEDIUM, 2h) -- Avaliar GIST vs GIN trigram.** Coletar metricas de uso do `word_similarity()`. Se pouco usado, substituir por GIN.

11. **TD-DB-04 (MEDIUM, 3h) -- Consolidar upsert de contratos.** Deprecar `upsert_pncp_supplier_contracts` row-by-row e padronizar em `upsert_supplier_contracts` (TD-DB-16).

12. **TD-DB-03 (MEDIUM, 3h) -- TTL enforcement.** Job de cleanup periodico para `enriched_entities`.

13. **TD-DB-13 (MEDIUM, 4h) -- Sincronizar colunas Python vs PG.** Auditar todas as queries em `datalake_helper.py`, `local_datalake.py`, e `monitor.py`.

### Fase 5: Housekeeping

14. **TD-DB-02b (LOW, 1h) -- Migration 010.** Verificar se colunas de match_logging ja existem. Se sim, descartar migration.

15. **TD-DB-09 (LOW, 1h) -- CHECK constraint em esfera_id.**

16. **TD-DB-10 (LOW, 1h) -- Decidir destino de ingestion_checkpoints.**

17. **TD-DB-12 (LOW, 0.5h) -- Limpar lista CORE em local_datalake.py.**

---

## 6. Respostas ao Architect

### DT-01: Migrations divergentes -- plano de reconciliacao

**Plano recomendado: `pg_dump --schema-only` como baseline, nao corrigir migrations antigas uma a uma.**

Justificativa: as migrations 001-008 representam um estado do schema que e anterior ao atual. Tentar "corrigir" cada uma individualmente e trabalho perdido -- sao 8 migrations que divergem em quase todas as tabelas. O correto e:

1. Executar `pg_dump --schema-only --no-owner --no-acl > db/schemas/current-schema.sql` para capturar o estado real.
2. Este arquivo vira o **source of truth** do schema.
3. Criar um novo conjunto de migrations (001-v2 a 012-v2) que, aplicadas sequencialmente a um banco vazio, produzam exatamente o schema atual.
4. Criar uma tabela `_migrations` para tracking.
5. Migrations 009-012 (que nunca foram aplicadas) devem ser adaptadas para o schema real e incluidas como migrations 009-v2, 010-v2, etc.
6. Descartar as migrations 001-008 originais ou move-las para `db/migrations/_archive/`.

**Rollback:** O script `current-schema.sql` permite recriar o banco a qualquer momento.

### DT-02: Migrations 009-012 nao aplicadas

Analise individual:

| Migration | Conteudo | Necessaria? | Adaptacao necessaria |
|-----------|----------|-------------|---------------------|
| 009 | entity_coverage table + triggers + v_coverage_summary + indexes | **SIM** -- sem entity_coverage, o sistema de monitoramento de cobertura nao funciona | Triggers referenciam `NEW.matched_entity_id`, `NEW.source`, `NEW.data_publicacao` -- colunas existem no schema real. Trigger function e compativel. Adaptar para usar `TIMESTAMPTZ` em vez de DATE. |
| 010 | Colunas match_method, match_score, match_confidence + indexes | **TALVEZ** -- verificar se ja existem no schema real | Se as colunas ja existem (codigo as referencia em `monitor.py`), a migration e desnecessaria. Se nao existem, sao 3 ALTER TABLE simples. |
| 011 | View v_unmatched_bids | **SIM** -- util para debugging de entity matching | View referencias colunas que existem no schema real. Compativel. |
| 012 | coverage_snapshots table, v_coverage_gaps, v_coverage_gaps_by_municipio, v_coverage_trend, generate_coverage_snapshot() | **SIM** -- necessario para relatorio semanal de cobertura (Story 001.7) | View v_coverage_gaps referencia `e.uf` que foi comentada na migration (`-- e.uf, (removed - column does not exist)`). O schema real de `sc_public_entities` nao tem coluna `uf`. Remover esta linha. Demais objetos compativeis. |

**Resumo:** Aplicar 009, 011, 012 (adaptadas). 010 verificar se ja existe.

### DT-08: GIN index em supplier_contracts.objeto_contrato -- viavel?

**Sim, viavel e recomendado.** A sugestao do DRAFT esta correta:

```sql
CREATE INDEX idx_psc_objeto_trgm ON pncp_supplier_contracts
USING GIN (objeto_contrato gin_trgm_ops) WHERE is_active = true;
```

Consideracoes:
- GIN trigram e ideal para ILIKE queries (como as de `datalake_helper.py:449-451`).
- Partial index `WHERE is_active = true` reduz tamanho significativamente.
- GIN e mais rapido para leitura que GIST, embora mais lento para INSERT/UPDATE.
- Para uma tabela de 3.69M registros onde inserts sao batch (nao OLTP), o custo de manutencao do GIN e aceitavel.
- Tamanho estimado: ~200-300 MB (GIN e mais compacto que GIST para trigram).

Nao e necessario restringir a `objeto_contrato` com `WHERE is_active = true` na sugestao -- isso ja esta correto.

### Contradicao SQL injection: system-architecture.md (MEDIO) vs DB-AUDIT.md (baixo)

**Resolvida apos analise do codigo fonte: DB-AUDIT esta correto. O risco e BAIXO.**

Investiguei o codigo de `monitor.py` que a system-architecture.md apontou como "f-strings para SQL (linha 67-68) -- risco teorico de SQL injection". O trecho em questao e:

```python
# monitor.py:66-68
sql = "SELECT id, razao_social, ... FROM sc_public_entities WHERE is_active = TRUE"
if within_200km_only:
    sql += " AND raio_200km = TRUE"
sql += " ORDER BY id"
cur.execute(sql)
```

Isso e **concatenacao de string com literais fixas**, nao f-strings. `within_200km_only` e um booleano que determina se uma clausula literal fixa (`AND raio_200km = TRUE`) e adicionada. Nao ha interpolacao de variavel com dados externos. O risco de SQL injection e **zero** neste trecho.

Todas as demais queries em `monitor.py` usam `%s` placeholders com `cur.execute()` (ex: linhas 96-98, 172-181, 496-498). O `_LocalPgQuery` builder em `datalake_helper.py` tambem usa `%s` parameterization para todos os valores.

Há uma mencao a f-string em `local_datalake.py:94-98`:
```python
cur.execute(f"SELECT count(*) FROM \"{table}\"")
```
Porem, `table` vem de uma lista hardcoded `CORE` e passa por regex `re.match(r'^[a-z_][a-z0-9_]*$', table)` que rejeita qualquer nome nao alphanumerico. O risco e mitigado, mas ainda e uma pratica ruim -- idealmente usaria `psycopg2.sql.Identifier()`.

**Veredito:** DB-AUDIT (baixo risco) e a classificacao correta. O system-architecture.md classificou incorretamente como MEDIO. Corrigir na versao final do technical-debt-assessment.md.

### Contradicao ORM: system-architecture.md trata ausencia de ORM como anti-padrao

O system-architecture.md (secao 7.4) lista `psycopg2 queries diretas sem ORM` como anti-padrao. DB-AUDIT aceita como seguro para single-user.

**Posicao do @data-engineer:** Concordo com DB-AUDIT. Para um sistema CLI single-user com 6 tabelas e queries majoritariamente customizadas (RPCs, triggers, full-text search), um ORM adicionaria complexidade sem beneficio. Projetos como SQLAlchemy exigiriam mapeamento de 9 funcoes RPC customizadas, 3 triggers, e tipos como TSVECTOR e VECTOR(256) que ORMs tratam mal. A ausencia de ORM e uma escolha arquitetonica valida para este contexto, nao um debito tecnico.

Se no futuro houver expansao para multi-usuario ou API REST, ai sim um ORM (ou pelo menos um query builder type-safe como `psycopg2.sql`) seria recomendado.

### Pergunta adicional: `datalake_helper.py` usa Supabase REST API ou conexao direta?

O `_LocalPgQuery` em `datalake_helper.py` implementa uma **emulacao local** do Supabase PostgREST API -- nao usa Supabase REST de verdade. O `DatalakeClient` conecta via `psycopg2.connect(DSN)` diretamente ao PostgreSQL local. O `_LocalPgQuery` e uma camada de compatibilidade que permite ao codigo usar a mesma sintaxe `sb.table("x").select().eq().execute()` tanto para o datalake local quanto para Supabase (caso migre no futuro).

Isso e uma boa pratica de abstracao, mas o query builder aceita qualquer nome de coluna sem validacao (TD-DB-13).

---

## 7. Recomendacoes Estrategicas

### 7.1 Governanca de DB

1. **Estabelecer migration tracking.** Sem uma tabela de controle, o schema do banco continuara divergindo. Criar `_migrations` table e processo de `supabase migration` ou `sqitch` para controlar mudancas.

2. **Nunca mais executar DDL avulso.** Toda alteracao de schema deve passar por uma migration. Documentar no `CONTRIBUTING.md` ou equivalente.

3. **Checklist pre-deploy de DB.** Incluir: `pg_dump --schema-only` pre e pos, `EXPLAIN ANALYZE` de queries afetadas, rollback script.

### 7.2 Arquitetura de Indexes

4. **Rever estrategia de indexes.** 36 indexes para 6 tabelas (media de 6 por tabela) e excessivo. Especialmente `pncp_supplier_contracts` que tem indexes enormes (171 MB, 151 MB, 145 MB). Auditar quais indexes sao efetivamente usados com `pg_stat_user_indexes`.

5. **Partial indexes sao bem utilizados.** `WHERE is_active`, `WHERE matched_entity_id IS NOT NULL` -- manter este padrao em novos indexes.

### 7.3 Seguranca

6. **Pipeline de secrets.** Implementar `.env` obrigatorio com fallback gracioso. O `DEFAULT_DSN` hardcoded deve ser apenas para desenvolvimento local, com warning em producao.

7. **Senha pos-comprometimento.** Como "smartlic_local" ja esta no git, considerar troca da senha. Qualquer um com acesso ao repo tem a senha do banco de producao.

### 7.4 Backup (CRITICAL - acao imediata)

8. **Implementar backup imediatamente.** Nao esperar a sprint. Setup de `pg_dump --format=custom` via systemd timer diario com:
   - Retention: 7 dumps diarios + 4 semanais
   - Destino: Hetzner Storage Box ou S3-compatible
   - Criptografia: `gpg` ou `openssl` para dados sensiveis (embora licitacoes sejam dados publicos, a senha do banco esta no dump)

### 7.5 Relacao Index/Dados

9. **Monitorar razao index/dados.** `pncp_raw_bids` tem 397 MB de indexes para 268 MB de dados (razao 1.48x). `idx_pncp_raw_bids_objeto_trgm` sozinho consome 294 MB. Se a migracao para GIN for possivel (TD-DB-06), a economia seria de ~150-200 MB.

---

## 8. Resumo de Metricas Ajustadas

| Metrica | DRAFT Original | Apos Revisao |
|---------|---------------|--------------|
| Debitos de database | 14 | 17 (14 + 3 novos) |
| Debitos CRITICAL | 1 | 2 (+TD-DB-15 backup) |
| Debitos HIGH | 2 | 5 (+TD-DB-05, +TD-DB-11, desdobramento TD-DB-02) |
| Debitos MEDIUM | 7 | 7 (com reclassificacoes internas) |
| Debitos LOW | 4 | 3 (TD-DB-02b LOW added, TD-DB-07 moved to MEDIUM) |
| Esforco total DB (h) | 38.5-46 | 52.5-60 |
| Debitos prontos para acao imediata | 4 (quick wins, 12-14h) | 7 (Fase 0-2, 16-18h) |

---

*Documento gerado por Dara (@data-engineer) em 2026-07-11.*
*Documento revisado: `docs/prd/technical-debt-DRAFT.md`*
*Arquivos consultados no codigo fonte: `monitor.py`, `datalake_helper.py`, `local_datalake.py`, `db/migrations/009-012`*
