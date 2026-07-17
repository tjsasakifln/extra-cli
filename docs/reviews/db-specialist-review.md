# Database Specialist Review

**Versão:** 3.0  
**Data:** 2026-07-17  
**Revisor:** Dara (@data-engineer)  
**Documento base:** `docs/prd/technical-debt-DRAFT.md` v3.0 DRAFT (Seção 2 — Débitos de Database)  
**Fontes de verificação:**  
- `supabase/docs/DB-AUDIT.md` v3.0  
- `supabase/docs/SCHEMA.md` v3.0  
- `db/migrations/` 001–054 (59 arquivos)  
- `db/current-schema.sql` (timestamp 2026-07-14 19:50)  
- `scripts/schema/diagnostics.py`, `scripts/schema/audit_sql_references.py`  
- `db/setup_db.sh`, `scripts/apply-migrations.sh`, `deploy/systemd/*`  
- Review anterior: `docs/reviews/db-specialist-review.md` (2026-07-13)

⚠️ **Risco residual de verificação:** Live DB **indisponível** em 2026-07-17 (timeout `127.0.0.1:54399` e `:5433`). Contagens de linhas, `_migrations` real e `VALIDATE CONSTRAINT` **não** foram revalidados ao vivo. Status RESOLVED baseia-se em dump + DDL de migrations + código — **não** em `SELECT` de produção/local.

---

## Débitos Validados

| ID | Débito | Severidade | Horas (DRAFT) | Horas (rev.) | Prioridade | Veredito | Notas |
|----|--------|------------|---------------|--------------|------------|----------|-------|
| **DT-01** | Colunas match_logging ausentes em bids | HIGH → — | — | **0** | — | **RESOLVIDO** | Dump: `match_method/score/confidence` presentes. Confirma audit trail v3. |
| **DT-02** | 10 tabelas v3 não aplicadas | HIGH → — | — | **0** | — | **RESOLVIDO** | Dump contém hierarchy, evidence, opportunity_*, eng, etc. |
| **DT-03** | Ordem 003-v2 depende de 005-v2 | MEDIUM | 1h | **0** (disciplina) | P3 residual | **ACEITO** | Track `db/` é canônico. Residual: `scripts/apply-migrations.sh` ainda aponta `supabase/migrations/` — coberto por **DT-23**. |
| **DT-04** | upsert_pncp_raw_bids row-by-row | MEDIUM → — | — | **0** | — | **RESOLVIDO** | Dump: set-based CTE + ON CONFLICT. |
| **DT-05** | upsert contracts row-by-row | MEDIUM/HIGH → — | — | **0** | — | **RESOLVIDO** | Set-based + 044 DISTINCT ON + 050 OUT-column fix. |
| **DT-06** | Sem UNIQUE `cnpj_8` | MEDIUM → — | — | **0** | — | **RESOLVIDO** | `uq_spe_cnpj_8` no dump. |
| **DT-07** | Senha hardcoded settings | MEDIUM | residual | **2h residual** | P1 residual | **AJUSTADO** | Default em `settings.py` **RESOLVIDO**. Residual **pior que o DRAFT admite**: `deploy/install.sh`, `deploy/provision-vps.sh`, `db/seed/*` ainda usam fallback `smartlic_local`. Não é só histórico git. |
| **DT-08** | Sem CHECK esfera_id | LOW → — | — | **0** | — | **RESOLVIDO** | `chk_pncp_raw_bids_esfera_id` no dump. |
| **DT-09** | Sem CHECK `source` | LOW | 2h | **2h** | P2 | **CONFIRMADO** | TEXT livre em várias tabelas. Domínios por tabela diferem — 2h realistas se mapa de domínio já existir; senão **3h**. |
| **DT-10** | Sem CHECK status `ingestion_runs` | LOW | 0.5h | **0.5h** | P2 | **CONFIRMADO** | Domínio pequeno. Pode batch com DT-09. |
| **DT-11** | ILIKE sem trigram objeto_compra | LOW → — | — | **0** | — | **RESOLVIDO** | `idx_bids_objeto_compra_gin` partial active. |
| **DT-12** | DATE vs TIMESTAMPTZ inconsistente | LOW | 2h | **2h** | P2 | **CONFIRMADO** | bids DATE; opportunity TIMESTAMPTZ; cast em search. **Não** migrar colunas de bids sem story HIGH-RISK — preferir casts nas RPCs. |
| **DT-13** | `ingestion_checkpoints` sem uso | LOW | 2h | **1h** | P3 | **AJUSTADO** | Watermarks 046 + pipeline_runs 047 supersedem parcialmente. Esforço residual: documentar “legado / não popular” **ou** remover em sprint de housekeeping. Integrar crawlers **não** é P2. |
| **DT-14** | Sem reconciliação periódica coverage | MEDIUM | 3h | **3h** | **P1** | **CONFIRMADO** (PARTIAL) | Fns 1.4/1.5 existem. Timer `coverage-report` roda **snapshot/export**, **não** `fn_reconcile_*` / rebuild de `entity_coverage`. Gap operacional real. |
| **DT-15** | content_hash UNIQUE sem partial `is_active` | LOW | 1h | **1.5h** | P2 | **AJUSTADO** | 1h subestima pre-check de colisões soft-delete + swap de índice em tabela grande. **1.5h**. |
| **DT-16** | GIN contracts ausente v2 | MEDIUM → — | — | **0** | — | **RESOLVIDO** | Presente no dump e migrações. |
| **DT-17** | match cols 005-v2 vs schema | HIGH → — | — | **0** | — | **RESOLVIDO** / **FUSÃO** | Mesmo que DT-01; manter só como cross-ref. |
| **DT-18** | Soft-delete contracts | LOW → — | — | **0** | — | **RESOLVIDO** | `is_active` em contracts no dump. |
| **DT-19** | FK órgão em bids | MEDIUM | residual | **0.5h residual** | P2 residual | **AJUSTADO** | FK `orgao_cnpj_8` via 041a **existe**. Residual: confirmar se ainda NOT VALID (042) quando DB up. Não reabrir como OPEN pleno. |
| **DT-20** | FK contracts → entities | MEDIUM | — | **0** (trade-off) | — | **ACEITO** | Criado 034/041a; **DROP em 050** (pilot nacional). Decisão consciente. Mitigação = **DT-27**. |
| **DT-22** | Política de retenção | MEDIUM | 3h | **2h residual** | P2 | **AJUSTADO** | `retention_policy` + `fn_purge_old_data` no schema. Falta: cron/systemd + política documentada por tabela. Função já existe → residual **2h**, não 3h greenfield. |
| **DT-23** | Dual migration track | **HIGH** | 4h | **6h** | **P0** | **AJUSTADO** | **CONFIRMADO** como débito. 4h subestima: README/Makefile/CI, deprecar `scripts/apply-migrations.sh`, alinhar `deploy/*`, ARCHIVED.md invertido (supabase acha que *é* canônico), testes de fresh-install. **6h**. |
| **DT-24** | `db/current-schema.sql` desatualizado | **HIGH** | 1h | **1.5h** | **P0** | **CONFIRMADO** / **FUSÃO** c/ DT-33 | Dump 07-14: **zero** tabelas pós-042 (`dlq_entries`, `entity_aliases`, `official_acts*`, watermarks, etc.). Regenerar dump + SHA + atualizar fingerprint em SCHEMA/DB-AUDIT. |
| **DT-25** | Live DB offline / sem smoke schema CI | MEDIUM | 2h | **3h** | **P1** | **AJUSTADO** | Compose + job condicional + `diagnostics.py` no CI. 2h só se compose já existir e estável; realisticamente **3h** com flakiness. |
| **DT-26** | CHECK constraints NOT VALID | MEDIUM | 2h | **2h** | P1 | **CONFIRMADO** | Dump: `chk_ee_cnpj_not_empty`, `chk_ee_enriched_at_not_future`, `chk_ee_enriched_source_not_empty`, `ck_ce_success_zero_scope` — todos **NOT VALID**. VALIDATE em janela; ver respostas. |
| **DT-27** | FKs contracts dropadas sem view de orfandade | MEDIUM | 3h | **3h** | P1 | **CONFIRMADO** | View/métrica `% contracts com órgão no universe` + alerta. **Não** reintroduzir FK em pilot nacional. |
| **DT-28** | `diagnostics.py` EXPECTED_* incompleto | MEDIUM | 2h | **2.5h** | **P1** | **AJUSTADO** | EXPECTED_TABLES para em `source_snapshot_membership` — falta 043–054. **Pior:** `PENDING_FK_VALIDATION` ainda exige `fk_contracts_*` **dropados em 050** → falso crítico se DB=HEAD. Incluir limpeza FKs no mesmo PR. **2.5h**. |
| **DT-29** | `audit_sql_references.KNOWN_*` defasado | MEDIUM | 2h | **2h** | P1 | **CONFIRMADO** | KNOWN_TABLES sem `dlq_entries`, `official_acts*`, `entity_aliases`, `pipeline_*`, `entity_source_registry`, etc. |
| **DT-30** | Enum `evidence_state` duplicidade semântica | LOW | 3h | **3h** | P2 | **CONFIRMADO** | Não migrar enum em hot-path pré-VPS. Documentar mapa de estados primeiro (1h); rename/merge depois (2h+). |
| **DT-31** | pgvector sem uso garantido embedding | LOW | 2h | **2h** | P2 | **CONFIRMADO** | Extensão + `search_datalake` aceitam embedding; coluna/uso operacional não garantidos. Decisão: keep for hybrid search futuro vs strip em envs mínimos. |
| **DT-32** | Rollback unificado 043–054 ausente | MEDIUM | 4h | **5h** | P2 | **AJUSTADO** | Ordem FK/view/enum (049 DROP VIEW pattern) + testes. 4h apertado; **5h** com script `db/rollback/head-to-042.sql` + dry-run doc. |
| **DT-33** | Apply 043–054 local **não verificado** | **HIGH** | 1h | **1h** | **P0** | **CONFIRMADO** / **FUSÃO** c/ DT-24 | Quando DB up: `SELECT version FROM _migrations ORDER BY 1` + `diagnostics.py`. Bloqueador de confiança, não de DDL em si. |

### Continuidade v2 (fora do inventário v3 DRAFT)

| ID | Débito | Severidade | Horas | Prioridade | Veredito | Notas |
|----|--------|------------|-------|------------|----------|-------|
| **DT-21** | `tsv` só populado no upsert, sem trigger | LOW | 1h | P3 | **CONFIRMADO** (re-adicionado) | Review 07-13; dump/migrations: tsv preenchido em `upsert_pncp_raw_bids`, **sem** trigger BEFORE INSERT. COPY/INSERT direto deixa FTS NULL. DRAFT v3 omitiu — **não removido por evidência**. |
| **DT-23 (v2)** | `objeto_compra` nullable | LOW | 1h | P3 | **ACEITO** / **REMOVIDO** como ID | Não reintroduzir ID colidindo com DT-23 NEW. Tratar como nota de qualidade em DT-09/ingestão se necessário. |

---

## Débitos Adicionados

| ID | Débito | Severidade | Horas | Prioridade | Justificativa |
|----|--------|------------|-------|------------|---------------|
| **DT-34** | `diagnostics.PENDING_FK_VALIDATION` lista FKs de contracts removidas em 050 | **MEDIUM** | 0.5h | **P1** | Subconjunto/clarificação de DT-28; se separado, fix trivial. Se fundido em DT-28, não duplicar horas (já embutido nos +0.5h de DT-28). |
| **DT-35** | Defaults `smartlic_local` em `deploy/install.sh`, `provision-vps.sh`, `db/seed/*` | **MEDIUM** | 1.5h | **P1** | Residual de DT-07 além de git history. Scripts de **provisionamento VPS** ainda embutem senha fraca como default — risco pré-VPS real. |
| **DT-21** | (re-adicionado, ver tabela acima) | LOW | 1h | P3 | Omissão no inventário v3. |

> **Contagem:** se DT-34 for **FUSÃO** em DT-28 e DT-35 for residual de DT-07, **novos IDs líquidos = 1** (DT-21 reintroduzido) + opcional DT-35 se quiser tracking separado de secrets em deploy.

### Recomendações de fusão (IDs)

| Grupo | IDs | Ação |
|-------|-----|------|
| Schema truth | **DT-24 + DT-33** | Tratar como **uma story P0**: “verify HEAD + regenerate dump”. Horas combinadas **2–2.5h**, não 1+1 isolados. |
| Tooling schema | **DT-28 + DT-29 + DT-34** | Um PR: sincronizar EXPECTED_/KNOWN_* + limpar FKs fantasmas. **4–5h** total (não 2+2+0.5 sequenciais sem overlap). |
| Secrets residual | **DT-07 residual + DT-35** | Uma story de higiene de DSN defaults. |

---

## Respostas ao Architect

### 1. DT-33: `_migrations` chega a 054? Gap dump vs HEAD?

**Resposta:** **Não verificado ao vivo** (DB offline 2026-07-17).

**Evidência estática forte de gap dump ↔ HEAD:**

| Fonte | Estado |
|-------|--------|
| `db/migrations/` | **043–054 presentes** (entity_aliases, dlq, watermarks, pipeline_runs, record_hashes, resumable backfill, drop FKs contracts, date semantics, official_acts, ESR, local resilience) |
| `db/current-schema.sql` (2026-07-14) | **Nenhuma** `CREATE TABLE` para `dlq_entries`, `official_acts*`, `entity_aliases`, `pipeline_watermarks`, `entity_source_registry` |
| Fingerprint DB-AUDIT | Dump SHA documentado; **não** reflete HEAD 043–054 |

**Conclusão:** Há **gap estrutural comprovado** entre dump 07-14 e migrations HEAD. O gap no **banco local real** (`_migrations`) é **hipótese HIGH confidence** até `SELECT version FROM _migrations ORDER BY 1` rodar.

**Ação:** Story P0: subir Postgres → `bash db/setup_db.sh` (ou apply pendentes) → listar `_migrations` → regenerar dump (DT-24) → `diagnostics.py` exit 0.

---

### 2. DT-23: Política canônica — só `db/setup_db.sh` / `db/migrations`?

**Resposta: SIM — CONFIRMADO.**

| Path | Papel recomendado |
|------|-------------------|
| **`db/migrations/` + `db/setup_db.sh`** | **ÚNICA linha canônica** de apply (fresh + upgrade) |
| **`scripts/apply-migrations.sh`** | **Deprecated** — aplica apenas `supabase/migrations/` (v2/v3 subset, **sem** 030–054) |
| **`supabase/migrations/`** | **Baseline histórico** + `ARCHIVED.md` (conteúdo desatualizado: ainda diz que v2 é o futuro) |
| **`scripts/ops/apply_migrations.py`** | Verificar se aponta `db/` — se não, alinhar ou marcar helper de dev |

**Política escrita proposta (DoD):**

1. Docs/README/Makefile: `db/setup_db.sh` only.  
2. `scripts/apply-migrations.sh`: header DEPRECATION + exit 1 se `ALLOW_LEGACY_SUPABASE_MIG=1` não setado (fail-closed).  
3. Fresh install test usa **somente** `db/`.  
4. Proibido `supabase db push` como path de prod neste monólito (não é Supabase-hosted app multi-tenant hoje).

---

### 3. DT-24: Quem regenera `db/current-schema.sql` + SHA?

**Resposta — ownership:**

| Papel | Responsabilidade |
|-------|------------------|
| **@data-engineer (Dara)** | Define procedimento, valida dump vs EXPECTED_*, atualiza SCHEMA.md / DB-AUDIT fingerprint |
| **@dev** na story de migration | **Executa** regen no DoD da story que aplica 043–054 (ou story dedicada P0) |
| **@devops** | Garante job/CI opcional e que provision VPS usa `setup_db.sh`, não dump como apply path |
| **Ninguém** | Dump **não** é fonte de verdade para apply — é **snapshot de documentação/repro** |

**Procedimento canônico:**

```bash
# Após _migrations == HEAD e diagnostics green:
pg_dump "$LOCAL_DATALAKE_DSN" --schema=public --no-owner --no-acl \
  > db/current-schema.sql
sha256sum db/current-schema.sql  # atualizar DB-AUDIT + SCHEMA.md
```

**DoD de qualquer migration ≥ 055:** se alterar objetos públicos, dump + SHA no mesmo PR **ou** ticket explícito “dump lag accepted” com data.

---

### 4. DT-20 ACCEPTED: orfandade pós-050; DT-27 antes de VPS?

**Resposta:**

- **Pilot nacional:** drop de FK contracts → SC universe é **aceitável** (throughput > integridade rígida). **ACEITO mantido.**
- **DT-27 antes de VPS?**  
  - **Must-fix pré-VPS:** **NÃO** (não bloqueia provisionamento se writer único e health honestos).  
  - **Should-have Onda 0/1:** **SIM** — sem métrica de orfandade, M2/cobertura comercial pode mentir silenciosamente sobre contratos “sem órgão no universo”.  
  - Prioridade: **P1 pós SYS-001/002**, não na frente de split-brain.

**Mínimo viável DT-27:** view `v_contracts_orphan_orgao` + % no health report (não precisa recriar FK).

---

### 5. DT-14 PARTIAL: timer de reconciliação coverage/evidence?

**Resposta: só funções + report de coverage — não reconcile de integridade.**

| Artefato | Existe? | O que faz |
|----------|---------|-----------|
| `fn_reconcile_source_snapshot` / related 1.4 | SQL sim | Reconcile open tenders / membership |
| coverage model 1.5 / evidence | SQL sim | Ledger de evidência |
| `deploy/systemd/coverage-report.service` | sim | `monitor --report-coverage` + `local_datalake coverage --snapshot` |
| Timer que chama `fn_reconcile_*` ou rebuild `entity_coverage` | **NÃO encontrado** | Gap |

**Conclusão:** produção planejada tem **report/snapshot**, não **reconciliação periódica de drift trigger-bypass**. PARTIAL **CONFIRMADO**.  
**Pré-VPS must-fix?** Não se bulk COPY for raro. **P1** assim que backfill/resumable (049) rodar em volume.

---

### 6. DT-26: Quais CHECKs NOT VALID e janela segura?

**Confirmados no dump `db/current-schema.sql`:**

| Constraint | Tabela | Risco VALIDATE |
|------------|--------|----------------|
| `chk_ee_cnpj_not_empty` | `enriched_entities` | Baixo se dados limpos |
| `chk_ee_enriched_at_not_future` | `enriched_entities` | Médio se clock skew histórico |
| `chk_ee_enriched_source_not_empty` | `enriched_entities` | Baixo |
| `ck_ce_success_zero_scope` | `coverage_evidence` | **Médio-alto** — pode falhar em evidence legada `success_zero` incompleta |

**Janela segura:**

1. Off-peak (ex.: domingo 03:00, sem crawl full).  
2. Pre-check:

```sql
-- enriched_entities
SELECT count(*) FROM enriched_entities WHERE cnpj = '' OR enriched_source = '';
SELECT count(*) FROM enriched_entities WHERE enriched_at > now() + interval '1 hour';

-- coverage_evidence success_zero incompleto
SELECT count(*) FROM coverage_evidence
WHERE state = 'success_zero'
  AND (queried_start IS NULL OR queried_end IS NULL OR scope_key IS NULL OR pages_processed <= 0);
```

3. Se count > 0: limpar/backfill **antes** de VALIDATE (senão VALIDATE bloqueia e trava writes que violem).  
4. `ALTER TABLE ... VALIDATE CONSTRAINT ...` **um por vez**, com `lock_timeout` definido.  
5. FKs em `PENDING_FK_VALIDATION` de contracts: **não validar** — foram **dropadas** (050); limpar lista (DT-28/34).

---

### 7. DT-07 residual: `smartlic_local` no git / BFG?

**Resposta: residual ATIVO no working tree — não só history.**

| Local | Status 2026-07-17 |
|-------|-------------------|
| `config/settings.py` default | **Corrigido** (env) |
| `deploy/install.sh` | **Ainda** default `smartlic_local` |
| `deploy/provision-vps.sh` | **Ainda** default |
| `db/seed/*.py` | **Ainda** fallback |
| Histórico git | Assumir **ainda presente** (BFG não evidenciado nesta sessão) |
| Docs/audits | Referências históricas OK |

**BFG:** se senha nunca foi de produção cloud, BFG é **nice-to-have**.  
**Obrigatório pré-VPS:** remover defaults de **deploy/** (DT-35) e exigir `${PG_PASSWORD:?}` / DSN fail-closed.  
Re-scan: `git log -S'smartlic_local' --oneline | head` + `git grep smartlic_local` no HEAD.

---

### 8. SYS-001 (projeção DB): (A) resilient grava PG / (B) monitor único writer / (C) dual-write?

**Resposta — preferência @data-engineer: (B), com caminho de transição curto se necessário.**

| Opção | Veredito DB | Motivo |
|-------|-------------|--------|
| **(A)** resilient_cycle grava Postgres via loader canônico | Aceitável **só se** loader = **mesmo** caminho de upsert/RPC que monitor (`upsert_pncp_*`, evidence, watermarks) | Dois writers sem contrato compartilhado = dual schema path |
| **(B)** monitor consome FetchResult e permanece **único writer** | **PREFERIDO** | Um writer ⇒ uma semântica de `_migrations`-aligned upserts, coverage triggers, match_logging, DLQ. Menor risco de partial writes e drift de colunas |
| **(C)** dual-write + checksum | **Só temporário ≤ 1 sprint**, com checksum obrigatório e kill-switch | Dual-write em 3.7M contracts é caro e fácil de “ficar pra sempre” |

**Recomendação formal:**  
1. **Target:** (B) — resilient produz artefato/FS; **um** ingest path aplica no PG.  
2. Se (A) for escolhido por latência: **obrigatório** reutilizar funções SQL canônicas (não INSERT ad-hoc).  
3. **Rejeitar (C)** como estado estável pré-VPS multi-timer.

Alinha com SYS-001/002: sem writer único, DT-14/coverage e health continuam mentirosos.

---

## Recomendações

### Ordem de resolução (perspectiva DB)

```
P0-DB-1  DT-33 + DT-24     Verify _migrations + regen dump/SHA
P0-DB-2  DT-23             Política única migrations (fail-closed legacy)
P1-DB-1  DT-28+29+34       diagnostics/KNOWN_* + FKs fantasmas
P1-DB-2  DT-35 / DT-07res  Defaults deploy/seed sem smartlic_local
P1-DB-3  DT-25             Smoke schema no CI (service Postgres)
P1-DB-4  DT-26             Pre-check + VALIDATE CONSTRAINT
P1-DB-5  DT-14             Job reconcile (não só coverage-report)
P1-DB-6  DT-27             View orfandade contracts (pós writer único)
P2-DB    DT-09,10,12,15,22,32,30,31,21,13
```

**Dependência crítica com Sistema:** P0-DB pode rodar **em paralelo** a SYS-001/002, mas **não** habilitar timers resilientes na VPS até writer único **e** schema HEAD verificado.

### Pré-VPS must-fix vs depois

| Must-fix pré-VPS (DB) | Pode esperar (pós Onda 0 / P2) |
|------------------------|--------------------------------|
| DT-33 + DT-24 (verdade de schema) | DT-09, DT-10, DT-12, DT-15 |
| DT-23 (um apply path) | DT-30, DT-31, DT-21, DT-13 |
| DT-35 / defaults deploy DSN | DT-32 rollback pack (importante, não gate de boot) |
| DT-28 (sem falso vermelho/verde em diagnostics) | DT-27 (should-have cedo, não blocker boot) |
| — | DT-26 VALIDATE (janela; não bloqueia boot se NOT VALID já conhecido) |
| — | DT-14 cron reconcile (P1 ops, não boot) |
| — | DT-25 CI Postgres (P1 qualidade; ideal pré-VPS se barato) |

### Política dual-track de migrations (recomendação formal)

```
CANÔNICO:     db/migrations/*  aplicado por db/setup_db.sh
HISTÓRICO:    supabase/migrations/*  (somente leitura / arqueologia)
PROIBIDO:     apply-migrations.sh em qualquer host/CI sem ALLOW_LEGACY=1
DOCUMENTAÇÃO: ARCHIVED.md em supabase/ deve declarar "não use para prod"
DoD story:    migration nova só em db/migrations/ com número sequencial;
              dump regen se objetos públicos mudarem
```

---

## Estimativa consolidada

### Horas — débitos DB **abertos** (após revisão)

| Classe | IDs | Horas revisadas |
|--------|-----|-----------------|
| **P0 OPEN** | DT-23 (6) + DT-24/33 fusão (2.5) | **8.5h** |
| **P1 OPEN** | DT-25 (3) + DT-26 (2) + DT-27 (3) + DT-28/34 (2.5) + DT-29 (2) + DT-14 (3) + DT-35 (1.5) | **17h** |
| **P2 OPEN** | DT-09 (2) + DT-10 (0.5) + DT-12 (2) + DT-15 (1.5) + DT-22 (2) + DT-32 (5) + DT-30 (3) | **16h** |
| **P3 OPEN** | DT-13 (1) + DT-31 (2) + DT-21 (1) + DT-19 residual (0.5) | **4.5h** |
| **ACEITO (sem horas ativas)** | DT-03, DT-20 | **0h** (disciplina) |
| **RESOLVIDO** | 12 IDs core | **0h** |

| Métrica | Valor |
|---------|-------|
| **Total aberto revisado** | **≈ 46h** |
| DRAFT open-ish (18 × médias) | ~30–35h implícitas |
| **Delta vs DRAFT** | **+~11–16h** (rigor em DT-23/25/28/32 + residual secrets + DT-21) |
| Horas **must-fix pré-VPS DB** | **≈ 12–14h** (P0 + DT-35 + fatia DT-28) |
| Horas **P1 completo DB** | **≈ 25.5h** (P0+P1) |

### Contagem de status (pós-review)

| Veredito | N (aprox.) |
|----------|------------|
| RESOLVIDO | 12 (+ DT-17 fusão) |
| ACEITO | 2 (DT-03, DT-20) + nota objeto_compra |
| CONFIRMADO OPEN/PARTIAL | maioria DT-09…15,14,22,23–33 |
| AJUSTADO (sev/horas/escopo) | DT-07,13,15,19,22,23,25,28,32 |
| ADICIONADO | DT-21 reintroduzido; DT-34/35 propostos |
| REMOVIDO como ID autônomo | DT-17 (já fusão); objeto_compra v2-DT-23 |

---

## Desafios ao DRAFT (rigor)

1. **DT-07 “RESOLVED*”** subestima residual de **deploy** — não fechar como audit trail limpo.  
2. **DT-23 = 4h** é **otimista** — política + fail-closed + docs + ARCHIVED.md + CI = **6h**.  
3. **DT-24 e DT-33** devem ser **uma** unidade de trabalho; somar 1+1 sem overlap infla tracking.  
4. **DT-28** é mais grave que “EXPECTED incompleto”: diagnostics pode **exigir FKs mortas** e **ignorar tabelas vivas** → ferramenta mentirosa (mesmo tema de SYS-003).  
5. **DT-14**: presença de `coverage-report.timer` **não** fecha PARTIAL — escopo diferente de reconcile.  
6. **DT-21 omitido** no inventário v3 sem evidência de resolução.  
7. **Horas totais DB abertas ~46h**, não ~30h — Architect deve refletir no assessment FINAL.  
8. **Live offline:** qualquer RESOLVED de integridade de **dados** (não só DDL) carrega **risco residual** até smoke local.

---

## Nota RLS / segurança DB

**RLS continua N/A** no modo single-user/service role.  
**Não** abrir débito RLS pré-VPS.  
Quando houver PostgREST/multi-user: roles `app_readonly` / `app_ingest` + RLS mínima em `dlq_entries`, `ingestion_runs`, PII leve de `enriched_entities`.

---

## Referências cruzadas

| Artefato | Uso nesta review |
|----------|------------------|
| DB-AUDIT v3.0 §5–7 | Inventário DT-01…33 e prioridades |
| technical-debt-DRAFT §2, §9.1, §11 | Escopo de validação + perguntas |
| Review 2026-07-13 | Continuidade de estilo e DT-18…23 v2 |
| Stories 1.2–1.5 | Contexto de resoluções schema |

---

## Resumo executivo

O DRAFT v3 acerta o **audit trail** das resoluções grandes (match_logging, v3 tables, set-based upserts, UNIQUE cnpj_8, soft-delete, GIN). Os **novos P0 (DT-23/24/33)** são reais e bem priorizados.

O que a revisão **endurece**:

1. **Schema truth gap** dump↔HEAD é **fato de arquivo**, não só suspeita.  
2. **Dual track** precisa fail-closed, não só documentação.  
3. **Secrets residual em deploy** reabre risco pré-VPS.  
4. **diagnostics desatualizado** é débito de **honestidade operacional**, não cosmético.  
5. Preferência SYS-001: **writer único (B)**.  
6. Estimativa aberta consolidada **≈ 46h** DB; must-fix pré-VPS DB **≈ 12–14h**.

**Veredito da fase 5 (DB):** inventário **APROVADO COM AJUSTES** — Architect deve incorporar fusões DT-24/33, horas revisadas, DT-21/35 e respostas SYS-001 no assessment FINAL.

---

*Revisão gerada por Dara (@data-engineer) em 2026-07-17.*  
*Fontes: technical-debt-DRAFT.md v3.0 · DB-AUDIT.md v3.0 · SCHEMA.md v3.0 · db/migrations 001–054 · db/current-schema.sql (2026-07-14) · scripts/schema/\* · deploy/systemd · review 2026-07-13.*  
*Live DB offline — verificação residual obrigatória ao subir Postgres.*
