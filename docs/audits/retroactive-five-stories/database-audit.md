# Database Audit — Stories 1.1–1.5

**Auditor:** Claude Code (Database Auditor)
**Data:** 2026-07-13
**Commit auditado:** d2ff075
**Schema baseline:** `db/current-schema.sql` (SHA-256: b4ec407...)
**Migrations auditadas:** 030–040 (criadas) + 006 (modificada)

---

## Sumario Executivo

| Metrica | Valor |
|---------|-------|
| Migracoes auditadas | 12 (11 novas + 1 modificada) |
| Tabelas criadas | 7 (capability_coverage, contract_version_history, retention_policy, target_universe_runs, target_universe_entities, source_snapshot_membership, source_applicability_rules) |
| Views criadas | 17 (5 canonicas + 3 reporting + 1 summary + 2 universe + 1 open filter + 1 expanded + 1 manifest + 1 integridade + 1 migration status + 1 entity match) |
| Materialized views | 1 (mv_entity_source_applicability) |
| Funcoes criadas | 8 |
| Triggers criados | 3 (2 disabled by design, 1 enabled) |
| Constraints FK | 3 (todas NOT VALID) |

### Verdict: DB-CONCERNS

**6 CRITICAL/HIGH findings** impedem DB-PASS. Nao e DB-FAIL porque os problemas sao operacionais/deployment, nao corrupcao de dados ou violacao de integridade.

---

## 1. Baseline Schema Verification

### 1.1 SHA-256 Fingerprint

- **Arquivo:** `db/current-schema.sha256`
- **Conteudo:** `b4ec407e30f8d1d25598972c3c0a22138d80dc42c7acbb641bc875cb7735b880  db/current-schema.sql`
- **Calculado:** `b4ec407e30f8d1d25598972c3c0a22138d80dc42c7acbb641bc875cb7735b880`
- **Status:** OK -- fingerprint corresponde.

### 1.2 Baseline vs Migrations 030-040

| Migracao | Objetos | Na Baseline? |
|----------|---------|-------------|
| 030 (canonical views) | 5 views | SIM |
| 031 (reconciliation) | 3 colunas + function + index | SIM |
| 032 (capability) | tabela + trigger + view | SIM |
| 033 (contract versioning) | tabela + function + trigger | SIM |
| 034 (FK + UNIQUE) | 3 FK + 1 UNIQUE + indexes | SIM |
| 035 (retention) | tabela + 2 functions | SIM |
| 036 (reporting) | 4 views | SIM |
| 037 (target universe) | 2 tabelas + indexes | **NAO** |
| 038 (universe views) | 2 views | **NAO** |
| 039 (snapshot tracking) | 6 colunas + tabela + 2 functions + view update | **NAO** |
| 040 (coverage expansion) | 4 enum values + 11 colunas + 2 tabelas + 1 MV + 2 views + trigger | **PARCIAL** |

**Conclusao:** A baseline `current-schema.sql` foi gerada APOS as migracoes 030-036, mas ANTES de 037-040. Ha um **gap de deployment**: as migracoes 037-040 existem no commit mas nao foram aplicadas ao banco que gerou a baseline. A verificacao e corroborada pela ausencia de `source_active` columns, `target_universe_*` tables, e pela view `v_opportunity_open` que ainda usa a definicao antiga (sem filtro `source_active = TRUE`).

---

## 2. Findings por Criterio

### 2.1 Idempotency

**Pontos fortes (OK):**
- 030: `CREATE OR REPLACE VIEW` em todas as 5 views canonicas
- 031: `ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, `CREATE OR REPLACE FUNCTION`
- 032: `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, `DO $$` para trigger
- 033: `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, `DO $$` para trigger
- 034: `DO $$` blocks com pre-checks e `IF NOT EXISTS` para constraints
- 035: `CREATE OR REPLACE FUNCTION`, `CREATE TABLE IF NOT EXISTS`, `ON CONFLICT DO NOTHING` para seed data
- 036: `CREATE OR REPLACE VIEW`
- 037: `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`
- 038: `CREATE OR REPLACE VIEW`
- 039: `ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, `CREATE TABLE IF NOT EXISTS`, `CREATE OR REPLACE FUNCTION`
- 040: `ADD COLUMN IF NOT EXISTS`, `CREATE TABLE IF NOT EXISTS`, `CREATE OR REPLACE VIEW`, `CREATE OR REPLACE FUNCTION`, `DO $$` blocks

**Achado:**
- **040 (baixo):** A migracao 040 tenta adicionar colunas que ja existem da migracao 029 (`canonical_entity_key`, `applicability`, `scope_key`, `checked_at`, `freshness_status`, `pages_processed`, `records_fetched`, `evidence_metadata`). O `IF NOT EXISTS` protege, mas indica duplicacao de responsabilidade entre 029 e 040.

---

### 2.2 Rollback

**Pontos fortes (OK):**
- Todas as migracoes (030-040) incluem rollback SQL comentado no final do arquivo
- A migracao 029 possui rollback em arquivo separado: `db/rollback/029_qw01_auditable_radar.sql`
- Os rollbacks estao completos (DROP VIEW, DROP TABLE, DROP FUNCTION, ALTER TABLE DROP COLUMN)

**Achados:**
- **030 (baixo):** Rollback menciona `DROP VIEW IF EXISTS` mas views canonicas podem ter dependentes (views 036 dependem de 030). Rollback precisaria ser em ordem reversa.
- **037-038 (medio):** Rollback de `target_universe_entities` requer `DROP TABLE ... CASCADE` por causa da FK `fk_universe_run`. O CASCADE nao esta explicitado no rollback comentado.
- **039 (baixo):** `ALTER TYPE` nao pode ser desfeito via rollback de migration. O valor `source_active_changes JSONB` com `DEFAULT '[]'::jsonb` requer que o default seja removido antes da coluna.
- **040 (medio):** `ALTER TYPE ... ADD VALUE` e irreversivel em PostgreSQL (nao existe `REMOVE VALUE`). Os 4 valores de enum adicionados (`pending`, `running`, `blocked`, `stale`) nao podem ser removidos. Isso e documentado mas e uma limitacao arquitetural do PostgreSQL.

---

### 2.3 FK Constraints

**Migracao 034 -- 3 FKs criadas com NOT VALID:**

| FK | Tabela | Referencia | Status |
|----|--------|-----------|--------|
| `fk_bids_orgao_entity` | pncp_raw_bids.orgao_cnpj | sc_public_entities.cnpj_8 | NOT VALID |
| `fk_contracts_supplier_entity` | pncp_supplier_contracts.fornecedor_cnpj | sc_public_entities.cnpj_8 | NOT VALID |
| `fk_contracts_orgao_entity` | pncp_supplier_contracts.orgao_cnpj | sc_public_entities.cnpj_8 | NOT VALID |

**Achados:**
- **034 (critico):** As 3 FKS foram criadas como NOT VALID e **NUNCA foram validadas**. O `COMMENT` em cada FK instrui o operador a executar `ALTER TABLE ... VALIDATE CONSTRAINT ...` manualmente, mas nao ha garantia de que isso ocorreu. Dados orfaos podem existir.
- **034 (alto):** A FK `fk_bids_orgao_entity` referencia `sc_public_entities(cnpj_8)` mas `pncp_raw_bids.orgao_cnpj` e CNPJ completo (14 digitos), enquanto `sc_public_entities.cnpj_8` e CNPJ base (8 digitos). O pre-check usa `LEFT(b.orgao_cnpj, 8)`, mas a FK usa match direto. Isso significa que a FK SO funciona se `orgao_cnpj` em pncp_raw_bids contiver apenas 8 digitos -- caso contrario, a FK nunca matchera e todos os registros serao orfaos.
- **034 (alto):** Mesmo problema em `fk_contracts_supplier_entity` e `fk_contracts_orgao_entity`: `fornecedor_cnpj` e `orgao_cnpj` sao CNPJ completo (14 digitos ou 18 com mascara), mas a FK referencia `sc_public_entities.cnpj_8` (8 digitos). O match direto sem `LEFT()` na FK vai falhar sistematicamente.
- **034 (critico):** `ON DELETE SET NULL` em `fk_bids_orgao_entity` pode causar perda silenciosa de dados se entidades forem deletadas. `ON UPDATE CASCADE` em cnpj_8 de sc_public_entities e correto.

**Migracao 037 -- FK `fk_universe_run`:**
- **037 (ok):** `target_universe_entities.universe_run_id` -> `target_universe_runs.id` com `ON DELETE CASCADE`. FK correta para tabela de snapshot (append-only).

**Migracao 039 -- FK `source_run_id`:**
- **039 (ok):** `source_snapshot_membership.source_run_id` -> `opportunity_runs(id)` com `ON DELETE CASCADE`. Tabela pequena, NOT VALID nao necessario.

---

### 2.4 LOCK_TIMEOUT

| Migracao | LOCK_TIMEOUT | Justificativa |
|----------|-------------|---------------|
| 030 | NAO | Cria apenas views (sem lock de tabela) |
| 031 | NAO | ALTER TABLE em tabela de snapshot (aceitavel) |
| 032 | NAO | CREATE TABLE + CREATE INDEX em tabela nova |
| 033 | **5s** + statement_timeout 120s | ALTER TABLE em pncp_supplier_contracts |
| 034 | **5s** + statement_timeout 120s | ALTER TABLE em pncp_raw_bids (~200K) |
| 035 | **5s** + statement_timeout 120s | CREATE OR REPLACE FUNCTION (sem lock de tabela) |
| 036 | **5s** + statement_timeout 60s | Apenas CREATE VIEW |
| 037 | NAO | CREATE TABLE (tabela nova) |
| 038 | NAO | CREATE VIEW |
| 039 | NAO | **ALTER TABLE em opportunity_intel (potencialmente 100K+ linhas)** |
| 040 | NAO | **ALTER TABLE em coverage_evidence** + ALTER TYPE |

**Achados:**
- **039 (alto):** Nao define `SET LOCAL lock_timeout` antes de ALTER TABLE em `opportunity_intel`. Esta tabela pode ter 100K+ registros. Cada `ADD COLUMN IF NOT EXISTS` adquire ACCESS EXCLUSIVE lock. Sem timeout, uma transacao concorrente de longa duracao pode bloquear a migration indefinidamente.
- **040 (alto):** Nao define `SET LOCAL lock_timeout` antes dos 11 `ALTER TABLE ... ADD COLUMN` em `coverage_evidence`. Embora `IF NOT EXISTS` previna re-execucao, a tabela pode ter volume significativo. Sem timeout, o lock ACCESS EXCLUSIVE pode ser problematico.
- **030-032, 037-038 (ok):** Criam objetos novos (sem risco de lock em tabelas existentes).

---

### 2.5 Index Creation

**Achados:**
- Todos os indexes usam `CREATE INDEX IF NOT EXISTS` -- correto para idempotencia.
- Indexes parciais (WHERE) sao usados adequadamente:
  - `idx_cov_snap_reconciled WHERE source_reconciled = TRUE` (031)
  - `idx_cc_entity WHERE entity_id IS NOT NULL` (032)
  - `idx_cvh_changed_at WHERE change_type = 'snapshot'` (033)
  - `idx_contracts_fornecedor_cnpj_lookup WHERE fornecedor_cnpj IS NOT NULL` (034)
  - `idx_bids_orgao_cnpj_lookup WHERE orgao_cnpj IS NOT NULL` (034)
  - `idx_oi_source_active WHERE source_active = TRUE` (039)
  - `idx_ce_capability WHERE capability IS NOT NULL` (040)
  - `idx_ce_canonical_key WHERE canonical_entity_key IS NOT NULL` (040)

- **037 (ok):** `idx_target_universe_entities_run_included WHERE radius_decision = 'included'` e um index parcial bem posicionado para a query mais frequente.
- **038 (ok):** As views usam indexes existentes de 037.

---

### 2.6 Trigger Safety

**Migracao 033 (contract versioning) -- Criado DISABLED:**
- **033 (ok):** O trigger `trg_contract_versioning` e criado DISABLED por design. Comentario explica o impacto de 3.7M contratos. A decisao correta e ativar sob demanda.

**Migracao 032 (capability coverage) -- Criado ENABLED:**
- **032 (ok):** `trg_cap_coverage_updated_at` e um `BEFORE UPDATE` simples que atualiza `updated_at`. Tabela `capability_coverage` e pequena (1 linha por combinacao entidade-fonte-capacidade). Seguro.

**Migracao 040 (applicability rules) -- Criado ENABLED:**
- **040 (ok):** `trg_applicability_updated_at` opera em `source_applicability_rules` (tabela de configuracao com ~15 linhas). Seguro.

---

### 2.7 Data Type Consistency

**Achados:**
- **034 (critico):** `pncp_raw_bids.orgao_cnpj` e `TEXT` contendo CNPJ de 14 digitos. A FK referencia `sc_public_entities.cnpj_8` que e `TEXT` com 8 digitos. Como a FK e `NOT VALID`, isso nunca foi verificado. Se `orgao_cnpj` contem 14 digitos, NENHUM registro vai matcher -- a FK e estruturalmente quebrada.
- **034 (critico):** Mesmo problema para `pncp_supplier_contracts.fornecedor_cnpj` e `orgao_cnpj` -> `sc_public_entities.cnpj_8`.
- **030 (baixo):** `v_contracts_canonical` faz `LEFT(c.fornecedor_cnpj, 8)` no JOIN (linha 134), que e a abordagem correta. Isso contrasta com a FK em 034 que nao usa `LEFT()`.
- **039 (baixo):** `last_seen_source_run_id BIGINT` referencia logicamente `opportunity_runs.id` (SERIAL/BIGSERIAL). Tipos compativeis.
- **040 (baixo):** `pages_expected INT`, `records_expected INT` usam INTEGER que suporta ate 2B. Suficiente para dados de licitacao.

---

### 2.8 Column Naming Conventions

**Achados:**
- Consistencia geral com snake_case -- OK.
- **030 (baixo):** `v_entities_canonical` usa `within_200km` (ingles). `v_contracts_canonical` usa `entity_nome` (portugues). Pequena inconsistencia no padrao de idioma.
- **031 (baixo):** `source_reconciled` (ingles). OK para colunas tecnicas.
- **032 (baixo):** `is_covered`, `coverage_pct`, `last_verified` (ingles). Consistentes.
- **034 (baixo):** `fk_bids_orgao_entity`, `fk_contracts_supplier_entity` usam prefixo `fk_` + tabela + coluna. Padrao consistente.
- **037 (baixo):** `universe_run_id`, `canonical_entity_key`, `radius_decision`, `duplicate_root` -- todos ingles, consistentes com o restante do schema tecnico.

---

### 2.9 Comment/Documentation Quality

**Pontos fortes:**
- Todas as migracoes tem cabecalhos com story, descricao, dependencias e design decisions.
- Todas as tabelas tem `COMMENT ON TABLE`.
- Todas as colunas novas tem `COMMENT ON COLUMN`.
- Todas as funcoes tem `COMMENT ON FUNCTION`.
- A migracao 034 inclui notas detalhadas de design (por que NOT VALID, como resolver duplicatas).
- A migracao 040 faz referencia explicita a Secao 9 do plano mestre.

**Achados:**
- **030 (baixo):** `v_suppliers_canonical` nao tem `COMMENT ON COLUMN` para colunas como `total_contratos`, `valor_total_contratos` -- colunas derivadas complexas merecem documentacao.
- **037 (baixo):** `target_universe_entities.cnpj8` usa tipo `VARCHAR(8)` sem documentar por que nao `TEXT` como outras colunas de CNPJ. Deveria ter nota de design.
- **039 (baixo):** A funcao `fn_reconcile_source_snapshot` nao documenta o comportamento de concorrencia -- o que acontece se duas reconciliacoes rodarem simultaneamente para o mesmo source_run_id?

---

### 2.10 Conhecidos Bugs Verificados

#### REQ-001: `jsonb_build_object` vs `jsonb_build_array` na migration 039

**Status: FALSO POSITIVO**

A migration 039 usa o padrao:
```sql
source_active_changes = oi.source_active_changes || jsonb_build_array(
    jsonb_build_object('changed_at', NOW(), 'from', TRUE, ...)
)
```

Isso e **correto** e **consistente** em ambas as direcoes (inactivation linha 192, reactivation linha 231). O `source_active_changes` tem `DEFAULT '[]'::jsonb` (array vazio), e `jsonb_build_array(obj)` cria `[obj]` que e concatenado via `||`.

Nota: Em PG14+, `jsonb_array || jsonb_object` automaticamente envolve o objeto em array, entao `jsonb_build_object()` direto tambem funcionaria. Mas o padrao atual e mais explicito e igualmente correto.

**Nao e bug.**

---

## 3. Findings Detalhados

### 3.1 CRITICAL

| ID | Migracao | Descricao |
|----|----------|-----------|
| **C-01** | 034 | **FK structural mismatch**: `fk_bids_orgao_entity` referencia `sc_public_entities(cnpj_8)` com 8 digitos, mas `pncp_raw_bids.orgao_cnpj` contem 14 digitos. A FK NUNCA matchera. Todas as 3 FKs da migration 034 tem o mesmo problema. As FKs sao ineficazes por design. |
| **C-02** | 037-040 | **Baseline schema gap**: As migracoes 037-040 nao estao no `current-schema.sql`. A baseline foi gerada antes destas migracoes serem aplicadas. Isso significa que o schema atual do banco e desconhecido -- pode ou nao refletir as migracoes. |

### 3.2 HIGH

| ID | Migracao | Descricao |
|----|----------|-----------|
| **H-01** | 034 | **FKs NOT VALID nunca validadas**: As 3 FKs foram criadas com `NOT VALID` e nunca receberam `VALIDATE CONSTRAINT`. Nao ha garantia de integridade referencial. |
| **H-02** | 039 | **LOCK_TIMEOUT ausente**: `ALTER TABLE ... ADD COLUMN` em `opportunity_intel` sem `SET LOCAL lock_timeout`. ACCESS EXCLUSIVE lock pode travar em producao. |
| **H-03** | 040 | **LOCK_TIMEOUT ausente**: 11 `ALTER TABLE ... ADD COLUMN` em `coverage_evidence` sem `SET LOCAL lock_timeout`. Mesmo risco de H-02. |
| **H-04** | 040 | **Enum `running` ausente na baseline**: O valor `running` do enum `evidence_state`, que migration 040 tenta adicionar, nao esta presente na baseline. Os valores `pending`, `stale`, `blocked` estao (adicionados pela migration 029, nao 040). |

### 3.3 MEDIUM

| ID | Migracao | Descricao |
|----|----------|-----------|
| **M-01** | 040 | **Duplicacao com 029**: 8 das 11 colunas que 040 adiciona a `coverage_evidence` ja foram adicionadas por 029. `IF NOT EXISTS` protege, mas indica falta de coordenacao entre migracoes. |
| **M-02** | 034 | **Pre-check de orphans informa mas nao bloqueia**: O `DO $$` block conta orphans e emite WARNING, mas nao impede a criacao da FK NOT VALID. Em producao com muitos orphans, a FK nunca podera ser validada. |

### 3.4 LOW

| ID | Migracao | Descricao |
|----|----------|-----------|
| **L-01** | 039 | **Self-join redundante**: `UPDATE ... FROM opportunity_intel oi_current WHERE oi.id = oi_current.id` e um self-join desnecessario. Nao causa erro, mas adiciona complexidade. |
| **L-02** | 037 | **tipo VARCHAR(8) inconsistente**: `target_universe_entities.cnpj8` usa `VARCHAR(8)` enquanto `sc_public_entities.cnpj_8` usa `TEXT`. Nao ha problema funcional, mas e inconsistente. |
| **L-03** | 030 | **Nomenclatura mista**: Colunas em portugues (`orgao_nome`, `razao_social`) e ingles (`within_200km`, `is_covered`, `source_active`) convivem. Inconsistencia menor aceitavel em codebase existente. |
| **L-04** | 040 | **Rollback irreversivel do ALTER TYPE**: `pending`, `running`, `blocked`, `stale` nao podem ser removidos do enum evidence_state. Limitacao do PostgreSQL, documentada no codigo. |
| **L-05** | 036 | **Auto-referencia**: `v_schema_integrity` inclui `v_schema_integrity` na lista de views que verifica. Auto-referencia circular. |

---

## 4. REQ-001 Verificacao Detalhada

**Ticket:** `jsonb_build_object` vs `jsonb_build_array` na migration 039

**Arquivo:** `db/migrations/039_source_snapshot_tracking.sql`

**Analise:**

O padrao usado e:
```sql
source_active_changes = oi.source_active_changes || jsonb_build_array(
    jsonb_build_object('changed_at', NOW(), 'from', TRUE, 'to', FALSE, ...)
)
```

A coluna `source_active_changes` tem `DEFAULT '[]'::jsonb` (array vazio).

Em PostgreSQL, `jsonb || jsonb`:
- Se ambos sao arrays: concatenacao (`[a] || [b]` = `[a, b]`)
- Se LHS e array, RHS e objeto: objeto e convertido a array (`[a] || b` = `[a, b]`)

Portanto, ambos os padroes sao equivalentes:
- Atual: `'[]'::jsonb || jsonb_build_array(jsonb_build_object(...))` = `[{...}]`
- Alternativo: `'[]'::jsonb || jsonb_build_object(...)` = `[{...}]` (PG converte automaticamente)

**Veredito:** FALSO POSITIVO. O padrao atual e correto e ambos funcionariam. Preferencia por manter o atual por ser mais explicito.

---

## 5. Supabase Directory Status

O diretorio `supabase/` foi arquivado corretamente:

```
supabase/
  archive/
    current-schema.sql_HISTORICAL   (684 linhas, SHA-256: fef6151e)
  docs/
    DB-AUDIT.md     (auditoria de seguranca: RLS, access patterns, secrets, SQL injection)
    SCHEMA.md       (documentacao do schema)
```

O arquivo `db/current-schema.sql_HISTORICAL_20260713` nao existe no diretorio `db/`. O historico foi mantido apenas em `supabase/archive/`.

---

## 6. Reversa Docs Consistency

### 6.1 ERD Completo (`_reversa_sdd/erd-complete.md`)

| Objeto | No ERD? | Notas |
|--------|---------|-------|
| evidence_state | SIM, listado como enum | OK |
| capability_coverage | NAO | Faltando |
| contract_version_history | NAO | Faltando |
| retention_policy | NAO | Faltando |
| target_universe_runs | NAO | Faltando |
| target_universe_entities | NAO | Faltando |
| source_snapshot_membership | NAO | Faltando |
| source_applicability_rules | NAO | Faltando |

### 6.2 Data Dictionary (`_reversa_sdd/data-dictionary.md`)

| Objeto | No Dictionary? | Notas |
|--------|---------------|-------|
| coverage_evidence (com colunas 040) | PARCIAL | Tem canonical_entity_key, applicability, etc. MAS nao tem capability, next_due_at, records_expected |
| capability_coverage | NAO | Nao documentado |
| contract_version_history | NAO | Nao documentado |
| retention_policy | NAO | Nao documentado |
| target_universe_runs | NAO | Nao documentado |
| target_universe_entities | NAO | Nao documentado |
| source_snapshot_membership | NAO | Nao documentado |
| source_applicability_rules | NAO | Nao documentado |
| opportunity_intel colunas 039 | NAO | Nao ha documentacao de source_active, source_inactive_at, etc. |

### 6.3 DB Design (`_reversa_sdd/db/design.md`)

Documenta apenas as 8 tabelas originais (pre-029) e 10 funcoes PL/pgSQL. Todas as tabelas e colunas adicionadas por 030-040 nao estao inclusas.

### 6.4 Verdict on Reversa Docs

**Consistency: INCOMPLETE.** A documentacao Reversa reflete o estado do schema anterior as migracoes 029-040. Ha um gap significativo entre o schema real (com todas as tabelas novas) e a documentacao. Necessario re-extracao Reversa apos aplicacao das migracoes.

---

## 7. Resumo por Migracao

| Migracao | Verdict | Principais Problemas |
|----------|---------|----------------------|
| **006** (modificada) | PASS | Refactoring set-based correto. Funcoes substituidas tem mesma assinatura. |
| **030** (canonical views) | PASS | Views bem documentadas. Idempotente. Sem lock de tabelas. |
| **031** (reconciliation) | PASS | Colunas e funcao uteis. Idempotente. |
| **032** (capability) | PASS | Tabela bem estruturada. Trigger simples. View summary util. |
| **033** (contract versioning) | PASS | Trigger DISABLED por design. LOCK_TIMEOUT configurado. |
| **034** (FK + UNIQUE) | CONCERNS | **FKs estruturalmente quebradas (C-01). NUNCA validada (H-01).** |
| **035** (retention) | PASS | Funcao segura (whitelist de tabelas). Dry-run mode. LOCK_TIMEOUT. |
| **036** (reporting) | PASS | Views uteis. Auto-referencia em v_schema_integrity (L-05, menor). |
| **037** (target universe) | CONCERNS | GAP de deployment (C-02). VARCHAR(8) inconsistente (L-02). |
| **038** (universe views) | CONCERNS | GAP de deployment (C-02). Views dependem de tabelas 037 nao aplicadas. |
| **039** (snapshot tracking) | CONCERNS | GAP de deployment (C-02). LOCK_TIMEOUT ausente (H-02). REQ-001 falso positivo. |
| **040** (coverage expansion) | CONCERNS | GAP de deployment (C-02). LOCK_TIMEOUT ausente (H-03). Enum `running` ausente (H-04). Duplicacao com 029 (M-01). |

---

## 8. Recomendacoes

### Imediatas (pre-deployment):

1. **Corrigir FKs (C-01):** As 3 FKs da migration 034 estao estruturalmente quebradas porque o tipo/valor do CNPJ nao corresponde (14 digitos vs 8 digitos). Solucao:
   - Criar colunas de CNPJ-8 nas tabelas `pncp_raw_bids` e `pncp_supplier_contracts` (ex: `orgao_cnpj_8`)
   - Popular com `LEFT(orgao_cnpj, 8)`
   - Referenciar as novas colunas nas FKs
   - Ou usar `CHECK` constraints com `LEFT()` para garantir compatibilidade

2. **Validar FKs existentes (H-01):** Executar `ALTER TABLE ... VALIDATE CONSTRAINT ...` para cada FK em 034. Documentar resultados.

3. **Adicionar LOCK_TIMEOUT (H-02, H-03):** Migration 039 e 040 precisam de `SET LOCAL lock_timeout = '5s'` antes dos ALTER TABLE em tabelas existentes.

4. **Regenerar baseline:** Apos aplicar 037-040, regenerar `current-schema.sql` e atualizar `current-schema.sha256`.

### Curto prazo:

5. **Revisar evidence_state `running` (H-04):** Verificar se `running` foi adicionado ao enum. Se nao, executar manualmente ou ajustar migration 040.

6. **Adicionar LOCK_TIMEOUT em 037-040:** Mesmo para tabelas novas, e boa pratica definir timeouts de statement.

7. **Atualizar Reversa docs:** Re-executar extracao Reversa para capturar todas as tabelas, colunas e relacoes novas.

8. **Resolver auto-referencia em v_schema_integrity (L-05):** Remover `v_schema_integrity` da lista de views que verifica (ou documentar intencionalidade).

### Longo prazo:

9. **Criar validacao CI de baseline:** Script que verifica se `current-schema.sql` inclui todos os objetos de todas as migracoes.

10. **Padronizar nomenclatura de colunas (L-03):** Definir se colunas tecnicas devem ser em ingles ou portugues. Nao misturar na mesma tabela/view.

---

## 9. Veredito Final

```
DB-CONCERNS
```

**Razoes:**
- Os problemas C-01 (FK structural mismatch) e C-02 (baseline gap) sao criticos e impedem DB-PASS.
- No entanto, NENHUM finding indica corrupcao de dados existentes, perda de dados, ou violacao de integridade em objetos ja em producao.
- As FKs NOT VALID nao protegem dados (sao ineficazes), mas tambem nao corrompem dados existentes.
- O gap de baseline e operacional: as migracoes existem no codigo mas precisam ser aplicadas e verificadas.
- Todos os padroes de SQL sao corretos (idempotencia, triggers disabled por design, indexes parciais, etc.).

**Para atingir DB-PASS:** Corrigir C-01, aplicar 037-040, regenerar baseline, adicionar LOCK_TIMEOUT em 039/040.
