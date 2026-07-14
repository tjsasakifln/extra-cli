# Database Specialist Review

**Revisor:** Dara (@data-engineer)
**Data:** 2026-07-13
**Documento base:** `docs/prd/technical-debt-DRAFT.md` (Secao 2 -- Debites de Database)
**Fontes de verificacao:** `supabase/docs/SCHEMA.md`, `supabase/docs/DB-AUDIT.md`
**Schema snapshot:** `supabase/current-schema.sql` (2026-07-11)

---

## Debitos Validados

| ID | Debito | Severidade Original | Severidade Revisada | Horas | Prioridade | Notas |
|----|--------|---------------------|---------------------|-------|------------|-------|
| DT-01 | Colunas match_logging (match_method, match_score, match_confidence) ausentes no schema real | HIGH | HIGH CONFIRMED | 1h | P1 | DB-AUDIT 4.2 confirma: 005-v2 aplicada PARCIAL. Colunas nao estao no `current-schema.sql`. 1h para adicionar 3 colunas nullable + validar triggers. **Merge com DT-17.** |
| DT-02 | 10 tabelas v3 nao aplicadas ao banco | HIGH | HIGH CONFIRMED | 4h | **P0** | DB-AUDIT 4.1: 006-v3 PENDING. Bloqueia opportunity intel, engenharia civil, coverage evidence. Prioridade elevada para P0 porque desbloqueia pipeline de oportunidade inteiro. |
| DT-03 | Ordem de dependencia v2 incorreta (003 depende de 005) | MEDIUM | MEDIUM CONFIRMED | 1h | P2 | DB-AUDIT 4.3. Provavelmente funcional porque as migrations foram aplicadas manualmente (005 antes de 003) ou 003-v2 usa `IF EXISTS`. Renumerar 003-v2 para ~006-v2. |
| DT-04 | upsert_pncp_raw_bids row-by-row | MEDIUM | MEDIUM CONFIRMED | 2h | P2 | Volume atual ~200K registros (DB-AUDIT 2.1). Ainda nao e gargalo mas preparar para escala. Horas ajustada para 2h (refatoracao direta com `jsonb_to_recordset`). |
| DT-05 | upsert_pncp_supplier_contracts row-by-row | MEDIUM | **HIGH ELEVATED** | 2h | **P1** | DB-AUDIT 2.1: 3.7M registros -- 18x maior que pncp_raw_bids. O loop row-by-row e gargalo REAL. Severidade elevada com base no volume comprovado. Refatoracao urgente. |
| DT-06 | Sem UNIQUE constraint em sc_public_entities.cnpj_8 | MEDIUM | MEDIUM CONFIRMED | 2h | P2 | DB-AUDIT 3.1: index BTREE simples, nao UNIQUE. Precisa verificar duplicatas ANTES de adicionar constraint. 2h inclui verificacao + remediacao + constraint. |
| DT-07 | Senha hardcoded em config/settings.py | MEDIUM | **HIGH ELEVATED** | 1h | **P1** | DB-AUDIT 1.3: `postgres:smartlic_local` versionada no git. Se for senha de producao, e CRITICAL. Se for dev local, e HIGH. Migrar para `.env` + BFG repo cleanup. |
| DT-08 | Sem CHECK constraint para esfera_id | LOW | LOW CONFIRMED | 0.5h | P3 | Dominio conhecido (1,2,3,4). Baixo risco pois dados vem de crawlers controlados. |
| DT-09 | Sem CHECK constraint para source | LOW | LOW CONFIRMED | 2h | P3 | Aplica-se a 4 tabelas com dominios diferentes. Horas ajustada de 1h para 2h. |
| DT-10 | Sem CHECK constraint para status em ingestion_runs | LOW | LOW CONFIRMED | 0.5h | P3 | Dominio pequeno (running, completed, failed). |
| DT-11 | search_datalake com fallback ILIKE sem index de trigram | LOW | LOW CONFIRMED | 1h | P3 | DB-AUDIT 2.3: fallback ILIKE faz full table scan. Sem evidencia de uso frequente do fallback. |
| DT-12 | Data types inconsistentes (DATE vs TIMESTAMPTZ) | LOW | LOW CONFIRMED | 1h | P3 | DB-AUDIT 2.6 item 4. SCHEMA.md technical notes item 5. DATE e apropriado para dados de licitacao (sem componente de hora). Apenas funcoes precisam de casting. |
| DT-13 | ingestion_checkpoints vazia e sem uso | LOW | LOW CONFIRMED | 0.5h | P3 | DB-AUDIT: 0 registros. Estrutura correta mas nunca populada. Decisao arquitetural: integrar nos crawlers vs remover. |
| DT-14 | Nao ha coverage reconciliation periodica | MEDIUM | MEDIUM CONFIRMED | 3h | P2 | DB-AUDIT 3.3: bulk operations que bypassam triggers podem deixar dados inconsistentes. Criar funcao `reconcile_coverage()` + job semanal. |
| DT-15 | content_hash UNIQUE sem partial para is_active | LOW | LOW CONFIRMED | 1h | P3 | DB-AUDIT 2.6 item 5: re-insercao de registro soft-deletado falha silenciosamente. Migrar para `UNIQUE(content_hash) WHERE is_active = true`. |
| DT-16 | GIN index idx_psc_objeto_trgm ausente no v2 baseline | MEDIUM | **LOW DOWNGRADED** | 0.5h | P3 | DB-AUDIT 2.6 item 1: "GIN index em objeto_contrato ja existe" no schema real. O index existe em producao, apenas nao foi capturado na migration baseline v2. Problema de documentacao, nao de performance. |
| DT-17 | Colunas match_logging em migration 005-v2 mas ausentes no schema real | HIGH | **DUPLICATE** (merge com DT-01) | — | — | MESMO problema de DT-01, apenas do ponto de vista da migration vs schema. RECOMENDACAO: fundir em DT-01. DT-17 removido como debito autonomo, mantido como referencia cruzada. |

---

## Debitos Adicionados

| ID | Debito | Severidade | Horas | Prioridade | Justificativa |
|----|--------|------------|-------|------------|---------------|
| DT-18 | `pncp_supplier_contracts` sem soft-delete (`is_active`) e sem partial index | LOW | 1h | P3 | DB-AUDIT 2.2: pncp_raw_bids tem `is_active` com partial index, pncp_supplier_contracts nao. Inconsistencia de design entre as duas maiores tabelas. |
| DT-19 | `pncp_raw_bids` sem FK entre `orgao_cnpj` e `sc_public_entities` | MEDIUM | 2h | P2 | DB-AUDIT 3.2: `orgao_cnpj` nao tem FK para `sc_public_entities`. Bids de orgaos nao cadastrados ficam orfas. Impacto mediado por `matched_entity_id`, mas `orgao_cnpj` cru pode gerar inconsistencias em relatorios. |
| DT-20 | `pncp_supplier_contracts` sem FK para `pncp_raw_bids` ou `sc_public_entities` | MEDIUM | 2h | P2 | DB-AUDIT 3.2: contracts independentes sem FK para entidade alguma. Orfaos de contract podem existir sem orgao ou fornecedor conhecido. |
| DT-21 | `tsv` (full-text vector) populado apenas na funcao upsert, nao via trigger | LOW | 1h | P3 | SCHEMA.md technical notes item 4: tsv e gerado dentro de `upsert_pncp_raw_bids()`. Insercao direta via INSERT ou COPY deixa `tsv = NULL`, quebrando full-text search. Migrar para trigger BEFORE INSERT OR UPDATE. |
| DT-22 | Ausencia de politica de retencao/lifecycle para dados antigos | MEDIUM | 3h | P2 | `purge_old_bids` existe com 400 dias hardcoded, mas sem politica documentada por fonte. Nem sequer cobre `pncp_supplier_contracts` (3.7M registros crescendo). Necessario definir regras de archiving/purge. |
| DT-23 | `objeto_compra` nullable em `pncp_raw_bids` sem NOT NULL enforced | LOW | 1h | P3 | DB-AUDIT 3.1 itens 3-4: coluna critica para full-text search e aceita NULL. Upsert function trata com `COALESCE` mascarando o problema. Adicionar NOT NULL ou validacao na aplicacao. |

---

## Resumo de Alteracoes de Severidade

| ID | Alteracao | Motivo |
|----|-----------|--------|
| DT-02 | Mantida HIGH, prioridade elevada para **P0** | Bloqueia pipeline de oportunidade inteiro; feature-critical |
| DT-05 | MEDIUM -> **HIGH** | Volume de 3.7M registros comprovado; loop row-by-row e gargalo real |
| DT-07 | MEDIUM -> **HIGH** | Credencial do banco versionada no git; risco de seguranca; se for senha de producao, seria CRITICAL |
| DT-16 | MEDIUM -> **LOW** | Index existe em producao; ausente apenas do arquivo de migration baseline |
| DT-17 | HIGH -> **DUPLICATE** (merge com DT-01) | MESMO problema de DT-01 sob optica diferente |

---

## Novos Debitos

| ID | Debito | Severidade | Horas |
|----|--------|------------|-------|
| DT-18 | pncp_supplier_contracts sem soft-delete / partial index | LOW | 1h |
| DT-19 | pncp_raw_bids sem FK entre orgao_cnpj e sc_public_entities | MEDIUM | 2h |
| DT-20 | pncp_supplier_contracts sem FK para tabela de entidade alguma | MEDIUM | 2h |
| DT-21 | tsv populado apenas em upsert function, nao via trigger | LOW | 1h |
| DT-22 | Ausencia de politica de retencao/lifecycle | MEDIUM | 3h |
| DT-23 | objeto_compra nullable sem NOT NULL enforced | LOW | 1h |

---

## Respostas ao Architect

### Pergunta 1: Estado real das colunas match_logging (DT-01/DT-17)

**Resposta:** As colunas `match_method`, `match_score`, `match_confidence` NAO estao presentes no schema real de producao. O snapshot `current-schema.sql` (2026-07-11) nao as inclui, e a tabela `pncp_raw_bids` no schema atual tem 18 colunas -- nenhuma relacionada a match_logging.

A migration 005-v2 foi aplicada de forma PARCIAL: a tabela `_migrations` registra 005-v2 como aplicada, mas o DDL `ALTER TABLE ... ADD COLUMN` nunca foi executado ou foi revertido posteriormente.

Duas hipoteses:
1. A migration 005-v2 foi criada apos o snapshot (draft futuro, nunca aplicado ao banco real).
2. Foi aplicada e depois revertida manualmente sem registro na tabela de tracking.

**Acao recomendada:** Nao re-executar a migration 005-v2 como esta. Criar uma NOVA migration `005b-v2-match-logging-fix.sql` que adiciona as 3 colunas com `ALTER TABLE pncp_raw_bids ADD COLUMN IF NOT EXISTS ...`, garantindo idempotencia. Isso evita conflito com o registro existente de 005-v2 na `_migrations`.

Nota: DT-01 e DT-17 descrevem o MESMO problema. DT-17 e um frameduplicado da perspectiva da migration vs schema. Minha recomendacao e fundir ambos, mantendo DT-01 como o debito canonico e DT-17 como referencia cruzada na matriz de rastreabilidade.

---

### Pergunta 2: Status da migration 006-v3 (DT-02)

**Resposta:** A migration 006-v3 NAO foi aplicada ao banco de producao. Status: PENDING (DB-AUDIT 4.1). As 10 tabelas, 6 views e 4 funcoes definidas nao existem no schema real.

**Bloqueio identificado:** Nao ha bloqueio tecnico -- a migration usa `CREATE TABLE IF NOT EXISTS` em todos os objetos, sem `DROP` commands (exceto `DROP VIEW IF EXISTS` nas views). O bloqueio e OPERACIONAL: ausencia de ambiente de staging para validacao pre-aplicacao.

**Recomendacao:** Aplicar em producao imediatamente, seguindo este plano:
1. Dry-run: extrair schema atual, aplicar migration em copia local (1h).
2. Aplicar em producao (1h).
3. Bateria de validacao pos-migration (2h): verificar todas as 10 tabelas, 6 views, 4 funcoes.
4. Testar `opportunity_intel/cli.py` contra as novas tabelas v3.

A migration e segura para aplicacao. Nao ha risco de perda de dados (apenas CREATEs). O rollback esta documentado na `rollback_sql` da tabela `_migrations`.

---

### Pergunta 3: Volume real e performance (DT-04/DT-05)

**Resposta:** Volumes reais (DB-AUDIT 2.1):

| Tabela | Registros | Storage dados | Storage indexes |
|--------|-----------|---------------|-----------------|
| `pncp_raw_bids` | ~200K | ~650 MB | ~400 MB |
| `pncp_supplier_contracts` | ~3.7M | ~2.2 GB | ~1.3 GB |

**Impacto do row-by-row:**

- **DT-04 (200K, upsert_pncp_raw_bids):** Cada batch insere ~500-2000 registros. Loop PL/pgSQL leva ~2-5s. **Nao e gargalo hoje.** Refatorar e bom planejamento, mas nao urgente.

- **DT-05 (3.7M, upsert_pncp_supplier_contracts):** Processa batches de ate 10K registros. Diferenca entre row-by-row e set-based e de ~5-10x. Isso significa ~30-60s vs ~3-6s por batch. **GARGALO REAL.** Em uma full crawl de contracts, dezenas de batches acumulam minutos de diferenca. Severidade elevada para HIGH, prioridade P1.

---

### Pergunta 4: ingestion_checkpoints (DT-13)

**Resposta:** Tabela vazia (0 registros) mas com estrutura correta: PK composta `(source, scope_key)` com colunas de pagination (`last_page`, `last_date`, `last_id`).

**Recomendacao: INTEGRAR com os crawlers, nao remover.**

Justificativa:
1. A estrutura segue o padrao correto de checkpoint state para crawlers resumeveis.
2. A v3 vai adicionar `opportunity_checkpoints` com o mesmo padrao -- consistencia entre tracks e desejavel.
3. Remover e recriar depois e custo desnecessario de migracao.

**Plano:** 4h para integrar checkpoints nos crawlers PNCP (bids + contracts). Os crawlers ja tem logica de pagination (monitor.py), so precisam persistir o estado atual em `ingestion_checkpoints` a cada N paginas.

**Se a integracao nao for viavel no curto prazo (proximos 2 sprints):** deixar a tabela como esta. O custo de storage e irrelevante (< 1 MB) e a estrutura nao causa problemas.

---

### Pergunta 5: Coverage reconciliation (DT-14)

**Resposta:** Atualmente, ~100% dos inserts passam pelos triggers `trg_bids_coverage` / `trg_bids_coverage_update` porque:
- Todo INSERT em `pncp_raw_bids` passa por `upsert_pncp_raw_bids()` (trigger AFTER INSERT)
- Nao ha `INSERT ... SELECT` direto ou `COPY` em producao

**Risco real:** BAIXO hoje, mas CRESCENTE. Quando houver backfills, bulk imports de novas fontes, ou migracoes, o bypass vai acontecer.

**Acao recomendada:** Job SEMANAL de reconciliacao (domingo 03:00). Criar funcao `reconcile_coverage()` que:
1. Recalcula `entity_coverage` para todas as combinacoes `(entity_id, source)`
2. Usa: `SELECT matched_entity_id, source, COUNT(*) ... FROM pncp_raw_bids WHERE is_active = true GROUP BY matched_entity_id, source`
3. Faz `INSERT ON CONFLICT (entity_id, source) DO UPDATE`

Nao duplicar com `generate_coverage_snapshot` -- essa funcao e para snapshots de tendencia, a nova funcao e para corrigir dados de coverage.

Estimativa: 3h (2h funcao + 1h agendamento systemd timer).

---

### Pergunta 6: UNIQUE em cnpj_8 (DT-06)

**Resposta:** Nao e possivel afirmar se ha duplicatas sem executar:

```sql
SELECT cnpj_8, COUNT(*) FROM sc_public_entities GROUP BY cnpj_8 HAVING COUNT(*) > 1;
```

O cadastro tem ~2K entidades alimentadas por IBGE/TCE-SC com CNPJs raiz unicos por municipio. **Risco de duplicatas existentes e BAIXO**, mas o risco de FUTURAS duplicatas (importacao manual, merge de fontes) e ALTO.

**Acao recomendada:**
1. Executar pre-check de duplicatas.
2. Se ZERO: adicionar UNIQUE constraint diretamente (`ALTER TABLE sc_public_entities ADD CONSTRAINT ... UNIQUE (cnpj_8)`).
3. Se houver duplicatas: resolver primeiro (decidir qual registro manter, marcar duplicatas como `is_active = false`).
4. **Nao usar UNIQUE INDEX** -- UNIQUE constraint e preferivel porque se comporta como FK target e se integra melhor com ferramentas de schema migration.

**Comportamento esperado:** Se uma tentativa de insert de CNPJ raiz duplicado ocorrer, o banco rejeita com erro de UNIQUE violation -- comportamento desejavel para matching de entidades.

---

### Pergunta 7: Senha hardcoded (DT-07)

**Resposta:** A credencial `postgres:smartlic_local` em `config/settings.py` tem caracteristicas de senha de DESENVOLVIMENTO LOCAL (`smartlic_local`). O nome do banco e `pncp_datalake`, nao um nome de producao.

**Porem, duas informacoes sao necessarias para avaliacao definitiva:**
1. O VPS de producao tem override via variavel de ambiente (`DSN=...` no systemd service)?
2. A senha de producao e a mesma ou diferente?

**Se a senha for de producao:** SEVERIDADE SOBE PARA CRITICAL. Exige rotacao imediata, remocao do git history com BFG Repo-Cleaner, e auditoria de acessos.

**Se for apenas dev local:** Severidade permanece HIGH. Ainda e problematica porque:
- Qualquer pessoa com acesso ao repo tem a senha do banco.
- A senha "smartlic_local" parece generica/fraca.
- Uma vez no git history, esta la para sempre.

**Acao recomendada:**
1. Mover para `.env`: `DATABASE_URL=postgres://postgres:smartlic_local@localhost:5432/pncp_datalake`.
2. Atualizar `config/settings.py` para: `os.getenv('DATABASE_URL', 'postgres://postgres:smartlic_local@localhost:5432/pncp_datalake')`.
3. Adicionar `.env` ao `.gitignore`.
4. Solicitar a @devops remocao do git history com BFG (ou aceitar que a senha antiga esta comprometida e trocar).
5. Para producao: usar `pg_service.conf` ou variavel de ambiente com senha diferente.

---

### Pergunta 8: Ordem de migrations (DT-03)

**Resposta:** 003-v2 referencia `match_method` que so existe em 005-v2. Como as migrations foram aplicadas sem quebrar?

**Hipotese mais provavel:** As migrations nunca foram aplicadas sequencialmente. O `current-schema.sql` foi extraido de um banco que ja tinha toda a estrutura (incluindo match_logging adicionado manualmente), e as migrations 001-v2 a 005-v2 foram geradas A PARTIR desse schema existente, nao aplicadas a um banco vazio.

Ou seja: as migrations sao uma fotografia do schema final, nao um script de construcao sequencial. A ordenacao numerica foi feita a posteriori pelo autor, sem considerar dependencias topologicas.

**Prova:** Se 005-v2 nunca criou as colunas match_logging (DT-01/DT-17), e 003-v2 referencia `match_method` que nunca existiu, entao a view em 003-v2 ou:
- Usa `SELECT NULL::text AS match_method` como placeholder, ou
- Foi criada no banco real em um momento em que as colunas ja existiam (adicionadas manualmente), mas a migration 005-v2 e posterior.

**Acao recomendada: Renumerar.** A opcao mais limpa e:
1. Renumerar 003-v2 para 006-v2 (ou 005a-v2, dependendo de quando 005-v2 for reaplicada).
2. Garantir que a view criada por 003-v2 nao referencie colunas que ainda nao existem.
3. Documentar ordem topologica explicita: `001 -> 002 -> [005] -> [003/006] -> 004`.

**Alternativa aceitavel se renumeracao for complexa:** Adicionar `IF NOT EXISTS` e `SELECT NULL::text AS match_method` no CREATE VIEW de 003-v2, tornando-a independente da ordem de aplicacao. Mas isso mascara o problema real.

---

## Matriz Revisada

### Distribuicao por Severidade

| Severidade | Original | Revisada | Diferenca |
|------------|----------|----------|-----------|
| HIGH | 3 | 4 | +1 (DT-05 e DT-07 elevados; DT-17 removido como duplicata) |
| MEDIUM | 6 | 7 | +1 (DT-16 reduzido a LOW; DT-19, DT-20, DT-22 novos) |
| LOW | 8 | 9 | +1 (DT-16 adicionado como LOW; DT-18, DT-21, DT-23 novos) |
| DUPLICATE | 0 | 1 | +1 (DT-17 fundido em DT-01) |
| **Total** | **17** | **21** | **+4 liquidos** (6 novos - 1 duplicata - 1 pago) |

### Esforco Total Revisado

| Categoria | Itens | Horas |
|-----------|-------|-------|
| HIGH (DT-01, DT-02, DT-05, DT-07) | 4 | 9h |
| MEDIUM (DT-03, DT-04, DT-06, DT-14, DT-19, DT-20, DT-22) | 7 | 15h |
| LOW (DT-08 a DT-13, DT-15, DT-16, DT-18, DT-21, DT-23) | 10 | 9h |
| **Total** | **21** | **33h** |

### Nota sobre RLS

**RLS nao e debito.** O banco opera como single-user com role `postgres` superuser. Nao ha multi-tenancy ou exposicao publica. Implementar RLS neste momento seria premature optimization. Manter no radar para quando houver API publica ou multi-usuario.

---

## Recomendacoes de Resolucao (Ordem)

### Fase 0 -- Imediata (seguranca + features)

| Ordem | ID | Debito | Horas | Justificativa |
|-------|----|--------|-------|---------------|
| 1 | DT-07 | Migrar senha para `.env` | 1h | Risco de seguranca. Se senha for de producao, rotacionar IMEDIATAMENTE. |
| 2 | DT-02 | Aplicar migration 006-v3 | 4h | Desbloqueia opportunity intel e engenharia civil. Feature-critical. |
| 3 | DT-05 | Refatorar upsert_pncp_supplier_contracts | 2h | Gargalo real em 3.7M registros. |

### Fase 1 -- Curto Prazo (data integrity)

| 4 | DT-01 | Adicionar colunas match_logging | 1h | Audit trail de matching. Nova migration (nao re-executar 005-v2). |
| 5 | DT-14 | Criar funcao `reconcile_coverage()` | 3h | Job semanal para corrigir inconsistencias de coverage. |
| 6 | DT-19 | Avaliar FK orgao_cnpj | 2h | Integridade referencial de bids. Pode precisar de tabela separada de orgaos. |
| 7 | DT-20 | Avaliar FK para contracts | 2h | Depende de decisao arquitetural (contracts independentes vs vinculados). |

### Fase 2 -- Medio Prazo (qualidade)

| 8 | DT-06 | UNIQUE em sc_public_entities.cnpj_8 | 2h | Verificar duplicatas + adicionar constraint. |
| 9 | DT-04 | Refatorar upsert_pncp_raw_bids | 2h | Preparacao para escala (200K -> 1M+). |
| 10 | DT-03 | Renumerar migrations v2 | 1h | Corrigir ordem topologica (003 -> ~006). |
| 11 | DT-22 | Politica de retencao de dados | 3h | Definir regras de purge/archive por fonte. |
| 12 | DT-21 | Migrar tsv para trigger | 1h | Garantir que FTS funciona para qualquer metodo de insercao. |

### Fase 3 -- Longo Prazo (housekeeping)

| 13 | DT-09 | CHECK constraint source (4 tabelas) | 2h | Validacao de dominio multi-tabela. |
| 14 | DT-08 | CHECK constraint esfera_id | 0.5h | Dominio simples. |
| 15 | DT-10 | CHECK constraint status | 0.5h | Dominio pequeno. |
| 16 | DT-15 | UNIQUE partial content_hash | 1h | Permitir re-insercao de registros soft-deletados. |
| 17 | DT-11 | GIN trigram em objeto_compra | 1h | Index para fallback ILIKE (se usado com frequencia). |
| 18 | DT-12 | Consolidar DATE vs TIMESTAMPTZ | 1h | Casting em funcoes, nao alterar colunas. |
| 19 | DT-13 | Integrar ingestion_checkpoints | 0.5h | Nos crawlers ou remover. |
| 20 | DT-16 | Atualizar migration baseline | 0.5h | Incluir idx_psc_objeto_trgm existente. |
| 21 | DT-18 | is_active em pncp_supplier_contracts | 1h | Consistencia com pncp_raw_bids. |
| 22 | DT-23 | objeto_compra NOT NULL | 1h | Validar se quebra algo antes de enforce. |

---

## Dependencias entre Debitos de Database

### Grupo 1: Match Logging Chain

```
DT-06 (UNIQUE cnpj_8) -> DT-01 (match_logging) -> DT-14 (coverage reconciliation)
                        DT-19 (FK orgao_cnpj)    DT-20 (FK contracts)
```

DT-06 e pre-requisito logico para DT-01: sem UNIQUE em cnpj_8, o match cascade nao tem garantia de que o target e unico. DT-01, por sua vez, alimenta DT-14 (reconciliacao precisa de match_logging para depurar falsos positivos).

### Grupo 2: Performance Chain

```
DT-21 (tsv trigger) -> DT-11 (trigram index) -> (search_datalake performance)
DT-05 (set-based upsert) -> DT-04 (set-based upsert) -> DT-22 (retention policy)
```

DT-21 garante que o FTS funciona, DT-11 otimiza o fallback. DT-05 e DT-04 sao independentes e podem ser resolvidos em paralelo. DT-22 e pos-requisito: so faz sentido definir retention depois de otimizar a insercao.

### Grupo 3: Schema Baseline Chain

```
DT-03 (renumerar migrations) -> DT-16 (atualizar baseline) -> DT-02 (aplicar v3)
```

DT-03 precisa ser resolvido antes de DT-16 (a nova baseline precisa ter ordem correta). DT-16 e DT-02 podem ser paralelizados se a migration 006-v3 for independente da reordenacao.

### Grupo 4: Validation Chain

```
DT-08 (CHECK esfera_id) -> DT-09 (CHECK source) -> DT-10 (CHECK status)
```

Todos CHECK constraints. Podem ser resolvidos em paralelo ou em batch. Nao ha dependencia entre eles.

---

## Referencias Cruzadas com o Technical Debt DRAFT

O DRAFT original (Secao 6) identifica as seguintes dependencias envolvendo database debts:

| DRAFT | Minha Analise |
|-------|---------------|
| Grupo 1: TD-027 (matching duplicado) -> DT-01, DT-17 | **CONFIRMADO.** DT-17 removido (duplicata de DT-01). DT-01 e pre-requisito para refatoracao de entity matching: sem match_logging, nao ha como depurar falsos positivos do matching duplicado. |
| Grupo 2: DT-06 -> DT-01, TD-027 | **PARCIALMENTE.** DT-06 e desejavel antes de DT-01 (garantir que matched_entity_id e UNIQUE), mas nao e blocker absoluto. DT-06 e DT-01 podem ser resolvidos em paralelo. |
| Grupo 3: DT-02 -> UX-09, TD-030 | **CONFIRMADO.** DT-02 (v3) desbloqueia opportunity coverage que UX-09 depende. TD-030 (schema.py sem testes) so faz sentido testar depois que schema v3 estiver no ar. |
| Grupo 5: DT-04 -> TD-011, TD-020 | **AJUSTADO.** DT-05 (contracts, nao DT-04) que tem impacto real em TD-011 (dual crawlers). O crawler de contracts e o bottleneck. DT-04 tem impacto marginal. |

---

## Resumo Executivo

| Metrica | DRAFT Original | Apos Revisao |
|---------|---------------|--------------|
| Debitos de database | 17 | 21 (17 validados + 4 liquidos apos fusao/adição) |
| Debitos HIGH | 3 | 4 (DT-05 e DT-07 elevados; DT-17 fundido em DT-01) |
| Debitos MEDIUM | 6 | 7 (DT-16 reduzido; DT-19, DT-20, DT-22 novos) |
| Debitos LOW | 8 | 9 (DT-16 adicionado como LOW; DT-18, DT-21, DT-23 novos) |
| Duplicatas | 0 | 1 (DT-17) |
| Esforco total (h) | ~30h | ~33h |
| P0 (feature blocker) | 1 (DT-02) | 1 (DT-02) |
| P1 (seguranca + performance) | 3 | 4 (+DT-05, +DT-07) |
| P2 (qualidade de dados) | 5 | 7 (+DT-19, +DT-20, +DT-22) |
| P3 (housekeeping) | 8 | 10 (+DT-18, +DT-21, +DT-23) |

A diferenca de **~3h** entre a estimativa original (~30h) e a revisada (~33h) confirma que o DRAFT original estava bem calibrado em termos de esforco. As maiores mudancas sao de priorizacao e severidade, nao de estimativa.

**Top 3 riscos nao mitigados no DRAFT original:**
1. **Senha versionada (DT-07):** Risco de seguranca real que precisa de acao antes de qualquer refatoracao.
2. **upsert de contracts row-by-row (DT-05):** Gargalo de performance comprovado em 3.7M registros que pode estar afetando o crawl diario.
3. **Falta de UNIQUE em cnpj_8 (DT-06):** Risco de duplicatas de entidade que pode comprometer todo o sistema de matching.

---

*Revisao gerada por Dara (@data-engineer) em 2026-07-13.*
*Documentos de referencia: technical-debt-DRAFT.md (v2.0), SCHEMA.md (2026-07-11), DB-AUDIT.md (2026-07-13).*
