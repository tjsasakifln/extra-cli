# Database Audit — Extra Consultoria

**Versão:** 3.0  
**Data:** 2026-07-17  
**Agente:** Dara (@data-engineer) — Brownfield Discovery Phase 2  
**Schema de referência:** `db/current-schema.sql` (2026-07-14, PG 16.14) + `db/migrations/` 001–054 (HEAD)  
**Dump fingerprint:** `85de867c8549e70a4b6dfe10a766e7bbe5b7c49cf737826caa1dc2862c7c6328`  
**Live DB 2026-07-17:** **indisponível** (timeout `127.0.0.1:54399` e `:5433`) — auditoria **sem contagens de linhas ao vivo**.

Cruzamento com auditoria anterior: `supabase/docs/DB-AUDIT.md` de **2026-07-13** (IDs DT-01…DT-17 e extensões da Story 1.2).

---

## 1. Security Audit

### 1.1 RLS Coverage

| Escopo | RLS | Policies | Risco | Notas |
|--------|-----|----------|-------|-------|
| Todas as tabelas (dump) | **NÃO** | 0 | **BAIXO** (hoje) | `SET row_security = off` no dump |
| Dados de negócio | — | — | BAIXO | Licitações/contratos públicos por lei |
| `ingestion_runs` / `dlq_entries` / error messages | — | — | **MÉDIO** se exposto | Podem conter stack/URLs internas |
| `enriched_entities` (email/telefone) | — | — | **MÉDIO** se multi-user | PII leve de pessoa jurídica |

**Avaliação honesta:** RLS é **N/A para o modo atual** (single-user / role de serviço `postgres` ou app local).  
Se o banco for exposto via Supabase REST, PostgREST ou rede multi-tenant, RLS passa a **obrigatório** antes de exposição.

### 1.2 Access Patterns

| Item | Estado 2026-07-17 |
|------|-------------------|
| Driver | `psycopg2` raw (sem ORM) |
| DSN | `LOCAL_DATALAKE_DSN` / `DATABASE_URL` em env (`config/settings.py`) |
| Default local | `postgresql://postgres:@127.0.0.1:54399/postgres` (sem senha no default atual) |
| Pooler | Não observado |
| Superuser app | Sim (padrão dev) |

### 1.3 Secrets Management

| Risco | Severidade | Status vs Jul/13 |
|-------|------------|-----------------|
| Senha `smartlic_local` hardcoded | era **MEDIUM** | **MELHORADO** — default atual sem senha; DSN via env. Ainda há risco se `.env`/históricos git tiverem secrets |
| Credencial em git | MEDIUM residual | Revisar histórico e scripts legados |

### 1.4 SQL Injection

- **Baixo:** queries parametrizadas nos helpers principais (`datalake_helper`, `local_datalake`, RPCs PL/pgSQL).
- **Atenção:** qualquer SQL dinâmico em scripts ad-hoc deve continuar com placeholders.

---

## 2. Performance Audit

### 2.1 Sizing

> Contagens **não** revalidadas em 2026-07-17 (sem DB). Estimativas históricas da auditoria 07-13:

| Tabela | Estimativa legada | Índices (ordem) | Notas |
|--------|-------------------|-----------------|-------|
| `pncp_supplier_contracts` | ~3.7M | alto | maior volume |
| `pncp_raw_bids` | ~200K | ~15+ | FTS + trigram |
| `opportunity_intel` | variável | muitos | Story 1.4 colunas extras |
| `sc_public_entities` | ~1–2K | 6 | universo SC |
| `target_universe_entities` | ~1K/run | partial included | append-only snapshots |
| `coverage_evidence` | cresce com runs | partial unique | ledger |

### 2.2 Index Coverage — melhorias desde 07-13

| Item | Status |
|------|--------|
| GIN trigram `objeto_compra` | **RESOLVIDO** — `idx_bids_objeto_compra_gin` (partial active) |
| GIN trigram contracts | **OK** — `idx_psc_objeto_trgm` + partial active |
| Match logging indexes | **OK** — `idx_bids_match_method`, coverage |
| Universe run filters | **OK** — partial `radius_decision = included` |
| FTS `tsv` | **OK** |

### 2.3 Upserts

| Função | Jul/13 | 2026-07-17 |
|--------|-------|------------|
| `upsert_pncp_raw_bids` | row-by-row (DT-04) | **Set-based** CTE + ON CONFLICT (`pncp_id`) no dump |
| `upsert_pncp_supplier_contracts` | row-by-row (DT-05) | **Set-based**; 044 DISTINCT ON; 050 fix OUT column ambiguity |

**Residual:** batches com `pncp_id`/`contrato_id` duplicados ainda exigem DISTINCT (044); monitorar erros ON CONFLICT.

### 2.4 Coverage triggers

Triggers em INSERT/UPDATE de `matched_entity_id` em bids permanecem.  
Bulk `COPY` / bypass de triggers ainda pode dessincronizar `entity_coverage` (DT-14 parcial).

### 2.5 Anti-patterns / riscos de performance

1. **Dois runners de migration** (`db/setup_db.sh` vs `scripts/apply-migrations.sh`) — risco de ambientes incompletos.  
2. **Dump desatualizado** (07-14 vs migrations 043–054) — diagnostics pode reportar “missing” se DB não aplicou HEAD.  
3. **FKs contracts → SC universe** (antes 050) matavam ingest nacional; 050 remove — trade-off integridade vs throughput.  
4. **`search_datalake` com embedding** — extensão `vector` presente; se coluna embedding ausente/null, path HNSW pode ser dead code.  
5. **~122 índices** — custo de escrita em contracts/bids; aceitável para analytics-heavy, revisar se ingest saturar.

---

## 3. Data Integrity Audit

### 3.1 Constraints — estado atual (dump + HEAD)

| Tema | Estado |
|------|--------|
| UNIQUE `sc_public_entities.cnpj_8` | **RESOLVIDO** (`uq_spe_cnpj_8`) |
| Match logging em bids | **RESOLVIDO** |
| CHECK `esfera_id` | **RESOLVIDO** |
| CHECK opportunity status/ranking | **OK** |
| CHECK coverage applicability/freshness | **OK** |
| CHECK `success_zero` completeness | Presente, **NOT VALID** no dump |
| CHECKs enriched_entities | Presentes, **NOT VALID** no dump |
| FK bids `orgao_cnpj_8` | Presente no dump (041a); validação 042 |
| FK contracts → entities | Presentes no dump; **DROP em migration 050** |
| CHECK genérico `source` / `ingestion_runs.status` | Ainda fraco (DT-09/10 OPEN) |

### 3.2 Orphan / reconcile risks

| Risco | Severidade | Mitigação |
|-------|------------|-----------|
| Bids com CNPJ fora de `sc_public_entities` | MÉDIO | FK `orgao_cnpj_8` (pode falhar inserts se orgao não SC) |
| Contracts nacionais sem FK | MÉDIO (intencional pós-050) | Aceito para pilot; orphans por design |
| Coverage vs evidence dessincronizados | MÉDIO | `coverage_evidence` + `fn_reconcile_*` Story 1.4/1.5 |
| Universe snapshot vs `raio_200km` divergente | MÉDIO se queries misturarem | Preferir `v_target_universe_active` |
| Snapshot membership keys erradas | era CRÍTICO | **RESOLVIDO** 041b (alinhamento Python keys) |
| Soft-delete + UNIQUE content_hash global | BAIXO | DT-15 ainda OPEN |

### 3.3 Coverage model (Story 1.5)

- Evidence ledger expandido com capability, applicability, pages_*, freshness.  
- Enum com estados `pending/running/blocked/stale`.  
- `success_zero` exige escopo + paginação (CHECK).  
- **054** adiciona `satisfactory` + `provenance` (se aplicada) — contrato de resiliência local.

### 3.4 Open tenders reconciliation (Story 1.4)

- Colunas `source_active*` em `opportunity_intel`.  
- `source_snapshot_membership` + `fn_reconcile_source_snapshot`.  
- Risco residual: runs parciais marcando inativos demais se membership incompleta — monitorar `fn_reconciliation_summary`.

---

## 4. Migration Hygiene

### 4.1 Dual track (dívida estrutural)

| Track | Problema | Recomendação |
|-------|----------|--------------|
| `db/migrations` 001–054 | Canônico operacional | **Usar sempre** para fresh/upgrade |
| `supabase/migrations` v2/v3 | Subconjunto; 006-v3 ≠ 030–054 | Marcar como baseline histórico; não aplicar sozinho em prod |
| `db/current-schema.sql` | Congelado em 07-14 | Regenerar após aplicar 043–054 |
| Story 1.2 DoD | `supabase/current-schema` histórico | Confirmar archive flag |

### 4.2 Dependências e ordem

- 003-v2 vs 005-v2 (supabase) permanece armadilha se alguém usar só track supabase (DT-03 ACCEPTED residual).  
- `db/migrations` usa nomes 021a/b/c, 041a/b — ordem lexical **ok** com zeros.  
- 040 altera enum **fora** de multi-statement transaction (comentário B2G-FIX-04) — correto.  
- 049 DROP VIEW antes de ALTER TYPE em bids — necessário; recria views.

### 4.3 Rollback

- Vários arquivos documentam rollback SQL em comentários / campo `rollback_sql`.  
- Rollback completo 043–054 **não** unificado em um único script — risco HIGH se precisar reverter official_acts + backfill.

### 4.4 Testes relacionados

| Teste / script | Escopo |
|----------------|--------|
| `tests/test_migration_052_official_acts.py` | Official acts |
| `tests/test_coverage_*` | Modelo coverage 1.5 |
| `tests/test_consulting_readiness.py` | Universe + open tenders |
| `scripts/schema/diagnostics.py` | Alinhamento live vs expected |
| `scripts/schema/audit_sql_references.py` | SQL embutido vs KNOWN_* |
| Integration schema tests (Story 1.2) | `test_all_sql_references` (se presente em `tests/integration/`) |

---

## 5. Inventário de débitos de dados (DT-xxx)

### 5.1 Débitos da auditoria 2026-07-13 — status

| ID | Descrição | Sev. | Esforço | Status 2026-07-17 | Evidência |
|----|-----------|------|---------|-------------------|-----------|
| **DT-01** | Colunas match_logging ausentes em bids | HIGH | 1h | **RESOLVED** | Dump: `match_method/score/confidence`; mig 005-v2 / 010 |
| **DT-02** | 10 tabelas v3 não aplicadas | HIGH | 4h | **RESOLVED** | Dump contém hierarchy, evidence, opportunity_*, eng, etc. |
| **DT-03** | Ordem 003-v2 depende de 005-v2 | MEDIUM | 1h | **ACCEPTED** | Track `db/` é canônico; supabase track residual |
| **DT-04** | upsert_pncp_raw_bids row-by-row | MEDIUM | 2h | **RESOLVED** | Dump: set-based CTE |
| **DT-05** | upsert contracts row-by-row | MEDIUM | 2h | **RESOLVED** | Set-based + 044/050 |
| **DT-06** | Sem UNIQUE `cnpj_8` | MEDIUM | 2h | **RESOLVED** | `uq_spe_cnpj_8` |
| **DT-07** | Senha hardcoded settings | MEDIUM | 1h | **RESOLVED*** | Default sem senha + env; *residual: secrets em histórico git* |
| **DT-08** | Sem CHECK esfera_id | LOW | 0.5h | **RESOLVED** | `chk_pncp_raw_bids_esfera_id` |
| **DT-09** | Sem CHECK `source` | LOW | 2h | **OPEN** | Ainda TEXT livre em várias tabelas |
| **DT-10** | Sem CHECK status ingestion_runs | LOW | 0.5h | **OPEN** | — |
| **DT-11** | ILIKE sem trigram em objeto_compra | LOW | 1h | **RESOLVED** | `idx_bids_objeto_compra_gin` |
| **DT-12** | DATE vs TIMESTAMPTZ inconsistente | LOW | 2h | **OPEN** | bids DATE; opportunity TIMESTAMPTZ; search cast |
| **DT-13** | ingestion_checkpoints sem uso | LOW | 2h | **OPEN** | Supersedido em parte por watermarks 046 (se aplicado) |
| **DT-14** | Sem reconciliação periódica coverage | MEDIUM | 3h | **PARTIAL** | Funções 1.4/1.5 existem; job schedule periódico não auditado |
| **DT-15** | content_hash UNIQUE sem partial active | LOW | 1h | **OPEN** | — |
| **DT-16** | GIN contracts ausente na mig v2 | MEDIUM | 0.5h | **RESOLVED** | Presente no dump e em migrações |
| **DT-17** | match cols 005-v2 vs schema real | HIGH | 1h | **RESOLVED** | Mesmo que DT-01 |

### 5.2 Débitos Story 1.2 (extensão 07-13 / plano mestre)

| ID | Descrição | Sev. | Esforço | Status |
|----|-----------|------|---------|--------|
| **DT-18** | Soft-delete contracts | LOW | 1h | **RESOLVED** | `is_active` em contracts no dump |
| **DT-19** | FK orgao em bids | MEDIUM | 2h | **RESOLVED*** | via `orgao_cnpj_8` (041a); *validar NOT VALID* |
| **DT-20** | FK contracts → entities | MEDIUM | 2h | **ACCEPTED** | Criado 034/041a; **removido 050** (pilot nacional) — decisão consciente |
| **DT-22** | Política de retenção | MEDIUM | 3h | **PARTIAL** | `retention_policy` + `fn_purge_old_data` existem; operação/cron não verificada |

### 5.3 Débitos NOVOS (2026-07-17)

| ID | Descrição | Sev. | Esforço | Prioridade | Recomendação |
|----|-----------|------|---------|------------|--------------|
| **DT-23** | Dual migration track (`db/` vs `supabase/`) sem política única | **HIGH** | 4h | P0 | Documentar “só `db/setup_db.sh`”; arquivar supabase track ou gerar espelho |
| **DT-24** | `db/current-schema.sql` desatualizado (falta 043–054) | **HIGH** | 1h | P0 | Regenerar dump + SHA após apply HEAD |
| **DT-25** | Live DB offline / sem smoke schema em CI local | **MEDIUM** | 2h | P1 | Container compose + `diagnostics.py` no CI |
| **DT-26** | CHECK constraints NOT VALID (ee, success_zero) | **MEDIUM** | 2h | P1 | `VALIDATE CONSTRAINT` em janela de manutenção |
| **DT-27** | FKs contracts dropadas (050) sem view de qualidade de orfaos | **MEDIUM** | 3h | P1 | Métrica % contracts com orgao em universe; alerta |
| **DT-28** | `diagnostics.py` EXPECTED_* incompleto vs 052–054 | **MEDIUM** | 2h | P1 | Atualizar EXPECTED_TABLES/VIEWS/FUNCTIONS |
| **DT-29** | `audit_sql_references.KNOWN_*` defasado (faltam official_acts, dlq, etc.) | **MEDIUM** | 2h | P1 | Sincronizar KNOWN_TABLES com HEAD |
| **DT-30** | Enum `evidence_state` com valores legados + novos (duplicidade semântica success/error) | **LOW** | 3h | P2 | Documentar mapa de estados; evitar novos aliases |
| **DT-31** | pgvector instalado sem garantia de coluna/uso embedding | **LOW** | 2h | P2 | Confirmar uso ou remover extensão em ambientes mínimos |
| **DT-32** | Rollback unificado 043–054 ausente | **MEDIUM** | 4h | P2 | Script `db/rollback/head-to-042.sql` com ordem FK |
| **DT-33** | Aplicação de 043–054 no ambiente local **não verificada** | **HIGH** | 1h | P0 | Quando DB up: `SELECT version FROM _migrations ORDER BY 1` |

---

## 6. Summary Dashboard

| Métrica | 2026-07-13 | 2026-07-17 |
|---------|------------|------------|
| Fonte schema | supabase v2 + v3 pending | **db/ 001–054** + dump 07-14 |
| Tabelas (dump) | 8 (+10 v3 pending) | **26** no dump |
| Tabelas teóricas HEAD | — | **~42** |
| Views (dump) | 4–10 | **32** |
| Funções (dump) | ~8 | **24** |
| Triggers (dump) | 3 | **9** |
| Índices (dump) | ~40 | **~122** |
| FKs (dump) | 2–8 | **13** (2 contracts dropados em 050 se HEAD) |
| RLS policies | 0 | **0** |
| Extensões | 2 | **3** (+vector) |
| Live row counts | estimados | **N/A** (DB offline) |
| Débitos RESOLVED (DT-01…22) | 0 | **13+** (ver §5) |
| Débitos OPEN/PARTIAL/ACCEPTED legados | 17 | **6 OPEN + 2 PARTIAL + 2 ACCEPTED** |
| Débitos NEW | — | **11 (DT-23…33)** |

### Contagem para YAML de saída

| Classe | IDs | N |
|--------|-----|---|
| **RESOLVED** | DT-01,02,04,05,06,07*,08,11,16,17,18,19* | **12** (com ressalvas *) |
| **ACCEPTED** | DT-03, DT-20 | **2** |
| **PARTIAL** | DT-14, DT-22 | **2** |
| **OPEN** (legado) | DT-09,10,12,13,15 | **5** |
| **NEW OPEN** | DT-23…33 | **11** |
| **OPEN total** (legado OPEN + NEW + PARTIAL contados como open-ish) | | **debts_open ≈ 18** se PARTIAL conta; **16** se só OPEN+NEW |

Definição usada no step_output:

- `debts_resolved` = 12  
- `debts_open` = 5 (legado OPEN) + 11 (NEW) = **16**  
- `debts_new` = **11**  
- PARTIAL/ACCEPTED reportados no texto, não no contador open puro.

---

## 7. Prioritized Recommendations

### P0 — Imediato

1. **[DT-33/DT-24]** Subir DB local e aplicar/verificar `_migrations` até 054; regenerar `db/current-schema.sql` + SHA.  
2. **[DT-23]** Política única: `db/setup_db.sh` é a única linha de apply em docs/Makefile; `apply-migrations.sh` (supabase) marcado deprecated/baseline.  
3. **[DT-25]** Smoke: `python scripts/schema/diagnostics.py` no pipeline quando DSN disponível.

### P1 — Curto prazo

4. **[DT-26]** VALIDATE CONSTRAINT nos CHECKs NOT VALID.  
5. **[DT-27]** Dashboard de orfandade de contracts pós-remoção de FK.  
6. **[DT-28/29]** Atualizar `diagnostics.py` e `audit_sql_references.py` para 043–054.  
7. **[DT-14]** Job periódico de reconciliação coverage/evidence (cron/systemd).

### P2 — Médio prazo

8. **[DT-09/10]** CHECKs de domínio `source` e `status`.  
9. **[DT-12/15]** Consolidar tipos de data; UNIQUE parcial content_hash.  
10. **[DT-32]** Rollback pack documentado.  
11. **[DT-30/31]** Limpeza semântica enum + decisão vector.

### Segurança (quando multi-user)

12. Introduzir roles `app_readonly` / `app_ingest` + RLS mínima.  
13. Rotacionar quaisquer secrets legados no histórico git.

---

## 8. Cross-check Stories 1.2–1.5

| Story | Schema impact | Status schema (código/migrations) |
|-------|---------------|-------------------------------------|
| **1.2 Unify schema** | Views canônicas 030–036, UNIQUE cnpj_8, FKs, set-based upserts, retention | **Done** no SQL; dump 07-14 reflete núcleo |
| **1.3 Universe authority** | `target_universe_*`, `v_target_universe_active` | **Done** no dump |
| **1.4 Reconcile open tenders** | `source_active*`, membership, reconcile fns | **Done** no dump (+041b fix) |
| **1.5 Coverage model** | Expand `coverage_evidence`, enum states, applicability | **Done** no dump (+054 colunas se aplicadas) |

---

## 9. Metodologia desta auditoria

1. Leitura de `SCHEMA.md` / `DB-AUDIT.md` 2026-07-13.  
2. Inventário DDL de `supabase/migrations/*` e **`db/migrations/*` (001–054)**.  
3. Parse de `db/current-schema.sql` (tabelas, views, FKs, funções, enums, índices).  
4. Cruzamento com `docs/architecture/schema-v3.md`, stories 1.2–1.5, `scripts/schema/*`.  
5. Tentativa de conexão read-only — **falhou** (timeout).  
6. Status de débitos DT-* por evidência em dump/migrations (sem inventar row counts).

---

*DB-AUDIT.md v3.0 — 2026-07-17. Factual; schema derived from migrations + dump + code.*
