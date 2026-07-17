# Technical Debt Assessment - FINAL

| Campo | Valor |
|-------|-------|
| **Projeto** | Extra Consultoria |
| **Versão** | **3.0 FINAL** |
| **Data** | **2026-07-17** |
| **Autores** | Aria (@architect) + Dara (@data-engineer) + Uma (@ux-design-expert) + Quinn (@qa) |
| **Origem** | Brownfield Discovery — Phase 8 (consolidação Phases 1–7) |
| **Baseline anterior** | v2.0 FINAL 2026-07-13 (**79 débitos**, ~353.5h) |
| **DRAFT predecessor** | `docs/prd/technical-debt-DRAFT.md` v3.0 |
| **Gate QA Phase 7** | **APPROVED WITH CONDITIONS** (`docs/reviews/qa-review.md` v3.0) |
| **Status operacional honesto** | **`LOCAL_RESILIENCE_READY`** · **NÃO `VPS_OPERATIONAL`** |

---

## Executive Summary

Este documento é a **fonte de planejamento definitiva** do Technical Debt Assessment v3.0 do projeto Extra Consultoria. Incorpora o DRAFT v3.0 (Aria), a revisão DB (Dara), a revisão UX (Uma) e o gate QA (Quinn — APPROVED WITH CONDITIONS C1–C6).

### Posição de verdade (não negociável)

| Claim | Status 2026-07-17 | Significado |
|-------|-------------------|-------------|
| **`LOCAL_RESILIENCE_READY`** | ✅ READY | Mecânica de resiliência local (fail-closed, chaos, health JSON, CI) existe e é auditável |
| **`VPS_OPERATIONAL`** | ❌ **NÃO** | Proibido enquanto **SYS-001/002 + TQ-07** (e Onda de verdade) permanecerem abertos |
| **M2 cobertura operacional** | **0/1.093 (0%)** | Honesto — meta 95% é **alvo**, não claim |
| **M1 sinal comercial** | **116/1.093 (10,61%)** | Ranking comercial — **≠** cobertura operacional |
| **SA JSON no tree** | ⚠ **PRESENTE** | `config/mides-bigquery-sa.json` (2370 bytes) — **SEC-02 P0 STILL OPEN** |
| **Live DB** | ⚠ **OFFLINE** | Timeout `127.0.0.1:54399` / `:5433` em 2026-07-17 — residual de verificação |

> **Regra de processo (C6):** nenhum enable de timers oficiais / claim `VPS_OPERATIONAL` até Onda de verdade (SYS-001…006 + SEC-02 + schema truth + TQ-07) com evidência. `LOCAL_RESILIENCE_READY` **nunca** implica cobertura 95% nem VPS pronta.

### Totais — inventário v3.0 FINAL

| Métrica | Valor |
|---------|-------|
| **IDs únicos rastreados (bruto, c/ aliases)** | **~140** |
| **IDs canônicos ativos (sem aliases duplos)** | **~118** |
| **Resolvidos / mitigados desde v2 (audit trail)** | **~22** |
| **Aceitos de fase (sem horas ativas)** | **4** (DT-03, DT-20, SEC-07, UX-01 DEFERRED) |
| **Novos desde v2** | **SYS-001…015 · DT-23…35 · UX-13…22 · TQ-06/07 · OBS · DEP · DOC/ENV** |
| **P0-class / CRITICAL-ops** | **~16** |
| **HIGH** | **~22** |
| **MEDIUM** | **~52** |
| **LOW** | **~28** |

### Distribuição por severidade (ativos canônicos)

| Severidade | Sistema | Database | Frontend/UX | Segurança | Testes | Obs | Deps | Docs/Env | **Total** |
|------------|---------|----------|-------------|-----------|--------|-----|------|----------|-----------|
| **CRITICAL / P0-class** | 6 (SYS-001…006) | 3* (DT-23,24/33) | 3** (UX-02,14,17) | 1 (SEC-02) | 2 (TQ-02,07) | 0† | 0 | 1 (ENV-02) | **~16** |
| **HIGH** | ~8 | 0 abertos HIGH além P0 | 2 (UX-01 DEF, UX-04) | 0 | 1 (TQ-04) | 1 (OBS-03) | 0 | 2 | **~14** |
| **MEDIUM** | ~16 | ~12 | 8 | 4 | 4 | 3 | 4 | 4 | **~55** |
| **LOW** | ~10 | 6 | 9 | 1 | 0 | 1 | 3 | 1 | **~31** |

\* DT-23 e DT-24/33 = HIGH com **prioridade P0**.  
\** UX-02 = **CRITICAL ops** (dual-label: classe UI HIGH / execução P0 CRITICAL). UX-14/17 = P0 ops.  
† OBS-01/02 são **aliases** de SYS-003/004 — não somam horas separadas.

### Esforço total estimado

| Escopo | Horas | Notas |
|--------|-------|-------|
| **Pre-VPS wave (must-fix + honesty pack)** | **~72–80h** | SYS-001…006 + SEC-02 + DT-23/24-33/35 + TQ-02/07 + UX-02/14/17/04/21 + fatia DT-28 |
| **Database aberto (revisão Dara)** | **≈ 46h** | Não ~30–35h do DRAFT implícito |
| **UX ativo sem UX-01 (revisão Uma)** | **≈ 101h** | Inclui UX-19…22 (+13h) |
| **Total ativo sem UX-01 e sem M2 40h+** | **≈ 310–360h** | Ordem de grandeza pós-ajustes especialistas |
| **Total com UX-01 (web DEFERRED)** | **≈ 390–440h** | Só pós-VPS + CLI estável |
| **SYS-008 M2 elevação (produto)** | **40h+** | Após writer único — **não** pré-VPS gate |

| Cenário | Horas | Custo (R$150/h) |
|---------|-------|-----------------|
| Pre-VPS only | ~76h | R$ 11.400 |
| Ativo sem Web UI / sem M2 full | ~335h | R$ 50.250 |
| + Web UI MVP (40h) | ~375h | R$ 56.250 |
| + Web UI completo (80h) | ~415h | R$ 62.250 |

### Distribuição por prioridade (canônico)

| Prioridade | Qtd aprox. | Horas aprox. | Ação |
|------------|------------|--------------|------|
| **P0** (pre-VPS + security + honesty) | ~16 | ~72–80h | Wave 1–3 (+ pack UX ops) |
| **P1** curto prazo | ~28 | ~95h | Waves 2–6 residual |
| **P2** médio prazo | ~40 | ~120h | Wave 4–7 |
| **P3** longo prazo / DEFERRED | ~34 | ~90h+ (c/ UX-01 80h+) | Wave 7 + backlog |

### O que mudou de verdade desde v2 (2026-07-13 → 2026-07-17)

| Eixo | v2 | v3 FINAL |
|------|----|----------|
| Escala | inventário 79 | ~118 canônicos / ~140 c/ aliases; **~131 commits** |
| CI/CD | ausente | **GitHub Actions fail-closed** (TD-028 RESOLVED) |
| Matching | duplicado | **unificado** (TD-027 RESOLVED) |
| Schema v3 | 10 tabelas ausentes (DT-02 P0) | **RESOLVED** no dump; gap novo = **043–054 vs dump 07-14** |
| P0 dominante | imports, senha, SA, v3 tables, monitor | **split-brain FS/DB, dual runtime, health mentiroso, schema truth, SEC-02 residual** |
| Segurança/Testes | gaps estruturais CRITICAL (NEEDS WORK) | categorias SEC/TQ/OBS/DEP/DOC **presentes** → gate **APPROVED WITH CONDITIONS** |
| Métricas | claims frágeis | **M2=0% honesto**; M1≠M2 trackeado |
| UX | 17 IDs | **22 IDs** (UX-19…22); CLI-first; Web **DEFERRED** |

### Top 5 recomendações (Architect)

1. **SEC-02 + DT-35** — remover SA JSON e defaults `smartlic_local` de deploy **antes** de qualquer provisionamento.  
2. **SYS-005/006 → SYS-003/004 → SYS-001/002** — truth chain: checkpoint/success honestos → health honesto → **um writer PostgreSQL** (preferência Dara **B**: monitor único writer).  
3. **DT-24+33 + DT-23** — schema HEAD verificado + dump/SHA + apply path único `db/setup_db.sh`.  
4. **TQ-07 fail-closed** — gate pré-VPS **FAIL** se SYS-001/002 abertos ao autorizar timers/claim VPS.  
5. **Só então** TD-010 (fatiar monitor), SYS-008 (M2) e UX-01 (web).

---

## Changelog vs v2 e condições do gate

### Condições C1–C6 — checklist FINAL

| # | Condição | Status neste FINAL | Evidência |
|---|----------|--------------------|-----------|
| **C1** | Incorporar ajustes Dara (DT-24+33 fusão, DT-23→6h, DT-21, DT-35, ~46h DB) | ✅ **FECHADO** | §2 Database + § horas |
| **C2** | Incorporar Uma (UX-02 CRITICAL ops, UX-04 HIGH, UX-19…22) | ✅ **FECHADO** | §3 Frontend/UX |
| **C3** | SEC-02 P0 até SA JSON ausente + gitignore + rotação | ✅ **FECHADO** (débito **permanece OPEN**) | §4 + verificação 2026-07-17: arquivo **presente** |
| **C4** | Dívida residual “DB offline 2026-07-17 verification” | ✅ **FECHADO** | § residual + ENV-01/DT-25/33 |
| **C5** | Respostas formais às 6 perguntas @qa | ✅ **FECHADO** | § Respostas QA |
| **C6** | Sem claim `VPS_OPERATIONAL` com SYS-001/002 + TQ-07 abertos | ✅ **FECHADO** | Executive Summary + Wave plan + CR-v3-001/007 |

### Dívida residual de verificação live (C4)

```text
RESIDUAL-VERIFY-2026-07-17:
  live_db: OFFLINE (127.0.0.1:54399 / :5433 timeout)
  implication:
    - RESOLVED de DDL/dump/código = confiança ALTA (estático)
    - integridade de DADOS e _migrations real = hipótese HIGH até smoke
    - perf live (OBS-05) = N/A
  mandatory_when_db_up:
    - SELECT version FROM _migrations ORDER BY 1  → max == HEAD (054+)
    - python -m scripts.schema.diagnostics → exit 0
    - regenerar db/current-schema.sql + SHA (DT-24)
    - revalidar NOT VALID / FK residual (DT-19, DT-26)
```

### IDs canônicos vs aliases (anti double-count — GAP-v3-002)

| Alias / work package | Canônico (horas contam aqui) | Não somar de novo |
|----------------------|------------------------------|-------------------|
| OBS-01 | SYS-003 | TD-015 PARTIAL (mesmo tema) |
| OBS-02 | SYS-004 | — |
| OBS-03 | UX-14 | — |
| OBS-04 | DT-14 | — |
| TQ-06 | DT-28 (+DT-34) | — |
| DOC-01 | DT-23 | — |
| DOC-02 / ENV-01 | DT-24+DT-33 (fusão) | — |
| TD-029 | SEC-02 | — |
| TD-016 residual | SEC-01 | — |
| TD-026 | TQ-02 | — |
| TD-024 | TQ-01 | — |
| TD-030 | TQ-03 | — |
| SYS-010 | DEP-01 / TD-023 | — |
| SYS-011 | DEP-02 | — |
| SYS-012 | DEP-03 | — |
| SYS-009 | DEP-04 | — |
| SYS-014 | DOC-03 | — |
| SYS-015 | DOC-04 | — |
| DT-07 residual | DT-35 (deploy defaults) | SEC-03 residual git |

---

## Inventário Completo

Legenda de status: **RESOLVED** · **STILL OPEN** · **OPEN** · **PARTIAL** · **NEW OPEN** · **ACCEPTED** · **DEFERRED** · **BLOCKED** · **MITIGATED**

---

### 1. Sistema

**Fonte:** `docs/architecture/system-architecture.md` v3.0 · PRE-VPS adversarial audit · Stories 1.1–1.5

#### 1.1 Pre-VPS blockers (NEW — 🔴 P0 CRITICAL)

| ID | Débito | Sev | Status | Horas | Prioridade | Evidência / DoD binário |
|----|--------|-----|--------|-------|------------|-------------------------|
| **SYS-001** | Split-brain: `resilient_cycle` grava FS, não PostgreSQL | CRITICAL | **NEW OPEN** | 12h | **P0** | Path oficial grava evidence/rows em PG; 0 success sem row esperada. **Target desenho: (B) monitor único writer** (Dara) |
| **SYS-002** | Dual systemd runtimes (`extra-crawl-*` FS vs `pncp-crawl-*` / monitor DB) | CRITICAL | **NEW OPEN** | 8h | **P0** | Uma família “oficial”; legados disabled/non-prod; health reporta runtime |
| **SYS-003** | Health “healthy” após fixtures (falso verde) | CRITICAL | **NEW OPEN** | 4h | **P0** | Fixture **nunca** overall=healthy com `claim=operational_live`; mode/environment/fixture flags |
| **SYS-004** | Freshness SLA hardcoded ≠ registry (ex. PNCP 24h vs 4h) | CRITICAL | **NEW OPEN** | 3h | **P0** | Thresholds de `coverage_slas.yaml` / registry; hardcoded removido ou fail-closed |
| **SYS-005** | Checkpoint schema engolido (`TypeError: pass`) | CRITICAL | **NEW OPEN** | 3h | **P0** | Schema inválido → erro; fail-closed |
| **SYS-006** | CIGA salva checkpoint success no adapter | CRITICAL | **NEW OPEN** | 3h | **P0** | Adapter **não** marca success de pipeline; só orquestrador/writer |

#### 1.2 Produto / ops (NEW)

| ID | Débito | Sev | Status | Horas | Prioridade | Evidência |
|----|--------|-----|--------|-------|------------|-----------|
| **SYS-007** | SC Compras bulk sem snapshot imutável (hash) | HIGH | **NEW OPEN** | 4h | P1 | Audit F7 |
| **SYS-008** | M2 operational coverage **0/1093** | HIGH | **NEW OPEN** | 40h+ | P1 *após SYS-001…006* | Meta 95% = alvo, não claim |
| **SYS-009** | Provedor cloud / VPS não definido | MEDIUM | **STILL OPEN** | 2h | P2 | ADR-007 (= DEP-04) |
| **SYS-010** | MIDES BigQuery sem conta GCP | LOW | **STILL OPEN** | — | P3 | gotcha (= DEP-01) |
| **SYS-011** | TCE-SC e-Sfinge inviável sem ICP-Brasil | MEDIUM | **STILL OPEN** | — | P3 | R$300–800/ano (= DEP-02) |
| **SYS-012** | DOM-SC API key / contrato CIGA | MEDIUM | **STILL OPEN** | 4h+ | P2 | comercial (= DEP-03) |
| **SYS-013** | Recall benchmark NOT_READY | MEDIUM | **STILL OPEN** | 8h | P2 | coverage contract |
| **SYS-014** | Preset AIOX `nextjs-react` ≠ stack real | LOW | **STILL OPEN** | 1h | P3 | confusão de agentes (= DOC-03) |
| **SYS-015** | Operational data accidental no git | MEDIUM | **STILL OPEN** | 2h | P1 | ADR-020 (= DOC-04) |

#### 1.3 Legado TD-* (v2 → v3)

| ID | Débito | Sev | Status | Horas | Prioridade | Evidência |
|----|--------|-----|--------|-------|------------|-----------|
| **TD-001** | Dual path PNCP async legado (`bids_crawler`) | HIGH | **STILL OPEN** *(reframe)* | 6h | P1 | Imports quebrados **RESOLVED** Story 1.1; dual path permanece |
| **TD-002** | DEFAULT_DSN duplicado settings vs CLIs | MEDIUM | **STILL OPEN** | 1h | P2 | |
| **TD-003** | Type hints / funções longas em monitor | MEDIUM | **STILL OPEN** | 4h | P2 | pós TD-010 |
| **TD-004** | Cache IBGE global mutável | MEDIUM | **STILL OPEN** | 2h | P2 | race potencial |
| **TD-010** | `monitor.py` god-module (~1581 LOC) | HIGH | **STILL OPEN** | **20h** | P1 *após unificar runtime* | Após SYS-001; **TQ-04 antes** |
| **TD-011** | Duas+ implementações PNCP | HIGH | **STILL OPEN** | 6h | P1 | adapter + bids_crawler + resilient |
| **TD-015** | Healthcheck unificado | MEDIUM | **PARTIAL** | 0h residual* | P1 | `ops/health.py` existe; honesty = SYS-003/004 |
| **TD-016** | SQL f-strings residual | HIGH | **STILL OPEN** residual | 0h* | P1 | horas em SEC-01 |
| **TD-017** | Scripts hyphen + underscore | MEDIUM | **STILL OPEN** | 4h | P2 | |
| **TD-018** | `backend/` duplica config | MEDIUM | **STILL OPEN** | 1h | P2 | |
| **TD-020** | Stubs ingestion transformer | LOW | **STILL OPEN** | 4h | P3 | |
| **TD-025** | Sem ORM / SQL espalhado | MEDIUM | **STILL OPEN** | 20h+ | P3 | só se multi-app/web |
| **TD-026** | Coverage CI 10% | MEDIUM | **STILL OPEN** | 0h* | **P0** | horas em TQ-02 |
| **TD-029** | SA JSON no repo | HIGH | **STILL OPEN** ⚠ | 0h* | **P0** | horas em SEC-02 |
| **TD-030** | Gaps teste schema/coverage | MEDIUM | **PARTIAL** | 0h* | P1 | horas em TQ-03 |
| **TD-031** | Docs desatualizadas (GAP-003 v2) | MEDIUM | **STILL OPEN** | 6h | P1 | runbooks/ADRs |
| **TD-032** | Observabilidade insuficiente (GAP-004 v2) | MEDIUM | **PARTIAL** | 4h residual | P1 | health existe; métricas P50/P95 ainda fracas |
| **TD-033** | Deps externas sem matriz de risco (GAP-005 v2) | MEDIUM | **PARTIAL** | 2h residual | P1 | DEP-* cobre; formalizar matriz |
| **TD-034** | Ambientes dev/staging/prod (GAP-006 v2) | MEDIUM | **STILL OPEN** | 4h | P2 | |

\* horas contadas no canônico (alias table).

#### 1.4 Cosmético / baixo (legado)

| ID | Débito | Sev | Status | Horas | Prioridade |
|----|--------|-----|--------|-------|------------|
| TD-005 | Subprocess sem output estruturado | LOW | **STILL OPEN** | 2h | P3 |
| TD-006 | ANSI manual com `rich` disponível | LOW | **STILL OPEN** | 1h | P3 |
| TD-007 | `import json` inline | LOW | **STILL OPEN** | 0.5h | P3 |
| TD-008 | Constantes espalhadas vs settings | MEDIUM | **STILL OPEN** | 3h | P2 |
| TD-009 | supabase_client inline | MEDIUM | **STILL OPEN** | 2h | P2 |
| TD-012 | Fallback silencioso rapidfuzz→difflib | LOW | **STILL OPEN** | 1h | P3 |
| TD-013 | Schema validation ausente em YAML | MEDIUM | **STILL OPEN** | 4h | P2 |
| TD-014 | Sem renovação automática de API keys | MEDIUM | **STILL OPEN** | 2h | P2 |
| TD-022 | Fallback DSN hardcoded em CLIs | MEDIUM | **STILL OPEN** | 2h | P2 |
| TD-023 | Mides BigQuery PULADO sem aviso | LOW | **STILL OPEN** | 0.5h | P3 |

#### Contagem Sistema

| Classe | N |
|--------|---|
| RESOLVED (audit) | **5** (TD-027,028,019,021 + import-break TD-001) |
| P0 NEW (SYS-001…006) | **6** |
| NEW ops (SYS-007…015) | **9** |
| STILL OPEN / PARTIAL legado TD | **~28** (c/ cosméticos; sem double-count de aliases) |
| Horas ativas canônicas (aprox.) | **~140h** (sem SYS-008 40h+ e sem aliases) |

---

### 2. Database

**Fonte:** `supabase/docs/DB-AUDIT.md` v3.0 · `docs/reviews/db-specialist-review.md` v3.0 (Dara)  
**Veredito Dara:** APROVADO COM AJUSTES · **Horas abertas ≈ 46h** · Must-fix pré-VPS DB ≈ **12–14h**

⚠️ **RESIDUAL-VERIFY-2026-07-17:** Live DB offline. RESOLVED abaixo = DDL/dump/código, **não** claim de dados de produção.

#### 2.1 RESOLVED desde v2 (audit trail)

| ID | Débito | Status | Evidência |
|----|--------|--------|-----------|
| **DT-01** / **DT-17** | match_logging em bids | **RESOLVED** (fusão) | dump: match_method/score/confidence |
| **DT-02** | 10 tabelas v3 | **RESOLVED** | hierarchy, evidence, opportunity_*, eng |
| **DT-04** | upsert bids row-by-row | **RESOLVED** | set-based CTE |
| **DT-05** | upsert contracts row-by-row | **RESOLVED** | set-based + 044/050 |
| **DT-06** | UNIQUE `cnpj_8` | **RESOLVED** | `uq_spe_cnpj_8` |
| **DT-08** | CHECK esfera_id | **RESOLVED** | chk no dump |
| **DT-11** | GIN trigram objeto_compra | **RESOLVED** | partial active |
| **DT-16** | GIN contracts | **RESOLVED** | presente |
| **DT-18** | Soft-delete contracts | **RESOLVED** | `is_active` |
| **DT-19** | FK órgão em bids | **RESOLVED*** | 041a; residual VALIDATE 0.5h se NOT VALID |

#### 2.2 ACCEPTED / PARTIAL

| ID | Débito | Sev | Status | Horas | Prioridade | Notas Dara |
|----|--------|-----|--------|-------|------------|------------|
| **DT-03** | Ordem 003-v2 / 005-v2 | MEDIUM | **ACCEPTED** | 0 | P3 disc. | track `db/` canônico; residual em DT-23 |
| **DT-07** | Senha hardcoded settings | MEDIUM | **PARTIAL** | 0* | P1 residual | default settings **ok**; residual **ativo** em deploy/seed → **DT-35** |
| **DT-14** | Reconciliação periódica coverage | MEDIUM | **PARTIAL** | **3h** | **P1** | timer coverage-report **≠** `fn_reconcile_*` |
| **DT-20** | FK contracts → entities | MEDIUM | **ACCEPTED** | 0 | — | DROP 050 pilot nacional; mitigação = DT-27 |
| **DT-22** | Política de retenção | MEDIUM | **PARTIAL** | **2h** | P2 | `fn_purge_old_data` existe; falta cron + doc |

#### 2.3 OPEN legado

| ID | Débito | Sev | Status | Horas | Prioridade | Notas |
|----|--------|-----|--------|-------|------------|-------|
| **DT-09** | Sem CHECK `source` | LOW | **OPEN** | 2h | P2 | |
| **DT-10** | Sem CHECK status ingestion_runs | LOW | **OPEN** | 0.5h | P2 | batch c/ DT-09 |
| **DT-12** | DATE vs TIMESTAMPTZ | LOW | **OPEN** | 2h | P2 | **não** migrar bids sem HIGH-RISK — casts em RPCs |
| **DT-13** | ingestion_checkpoints sem uso | LOW | **OPEN** | 1h | P3 | watermarks 046 supersedem |
| **DT-15** | content_hash UNIQUE sem partial is_active | LOW | **OPEN** | 1.5h | P2 | pre-check colisões |
| **DT-21** | `tsv` só no upsert, sem trigger | LOW | **OPEN** *(reintro)* | 1h | P3 | DRAFT v3 omitiu; Dara reintroduz |

#### 2.4 NEW + ajustes Dara (2026-07-17)

| ID | Débito | Sev | Status | Horas | Prioridade | Notas |
|----|--------|-----|--------|-------|------------|-------|
| **DT-23** | Dual migration track (`db/` vs `supabase/`) | **HIGH** | **NEW OPEN** | **6h** ↑ | **P0** | fail-closed legacy; ARCHIVED.md; CI; fresh-install |
| **DT-24 + DT-33** | Dump desatualizado + apply 043–054 **não verificado** | **HIGH** | **NEW OPEN** | **2.5h** *(fusão)* | **P0** | **Uma story:** verify `_migrations` + regen dump/SHA |
| **DT-25** | Live DB offline / smoke schema CI | MEDIUM | **NEW OPEN** | 3h | P1 | compose + diagnostics no CI |
| **DT-26** | CHECK constraints NOT VALID | MEDIUM | **NEW OPEN** | 2h | P1 | VALIDATE em janela off-peak |
| **DT-27** | FKs contracts dropadas sem view orfandade | MEDIUM | **NEW OPEN** | 3h | P1 | should-have cedo; **não** blocker boot VPS |
| **DT-28 + DT-34** | diagnostics EXPECTED_* incompleto + FKs fantasmas 050 | MEDIUM | **NEW OPEN** | **2.5h** *(fusão)* | **P1** | ferramenta mentirosa se exigir FKs dropadas |
| **DT-29** | `audit_sql_references.KNOWN_*` defasado | MEDIUM | **NEW OPEN** | 2h | P1 | PR conjunto c/ DT-28 (total tooling **4–5h**) |
| **DT-30** | Enum evidence_state duplicidade | LOW | **NEW OPEN** | 3h | P2 | doc mapa 1h; rename depois |
| **DT-31** | pgvector sem uso garantido | LOW | **NEW OPEN** | 2h | P2 | |
| **DT-32** | Rollback unificado 043–054 | MEDIUM | **NEW OPEN** | 5h | P2 | |
| **DT-35** | Defaults `smartlic_local` em deploy/seed | MEDIUM | **NEW OPEN** | **1.5h** | **P1 pré-VPS** | `install.sh`, `provision-vps.sh`, `db/seed/*` — fail-closed `${PG_PASSWORD:?}` |

**Política canônica de migrations (Dara — formal):**

```text
CANÔNICO:     db/migrations/*  via db/setup_db.sh
HISTÓRICO:    supabase/migrations/*  (somente leitura)
PROIBIDO:     scripts/apply-migrations.sh em host/CI sem ALLOW_LEGACY_SUPABASE_MIG=1
DoD ≥055:     dump regen + SHA se objetos públicos mudarem
```

**Preferência SYS-001 (DB):** **(B)** monitor único writer · (A) só se reutilizar RPCs canônicas · (C) dual-write ≤1 sprint com kill-switch.

#### Contagem Database

| Classe | N | Horas |
|--------|---|-------|
| RESOLVED | **12** (+ DT-17 fusão) | 0 |
| ACCEPTED | **2** (DT-03, DT-20) | 0 |
| PARTIAL | **3** (DT-07→35, DT-14, DT-22) | embutido |
| OPEN legado + reintro | **6** (09,10,12,13,15,21) | ~8h |
| NEW OPEN (c/ fusões) | **~12 work items** | — |
| **Total aberto revisado** | | **≈ 46h** |
| Must-fix pré-VPS DB | DT-23 + DT-24/33 + DT-35 + fatia DT-28 | **≈ 12–14h** |

---

### 3. Frontend/UX

**Fonte:** `docs/frontend/frontend-spec.md` v3.0 · `docs/reviews/ux-specialist-review.md` v3.0 (Uma)  
**Princípio:** *honesty UX* — fail-closed, sem verde falso, M1≠M2, CLI-first.  
**Web UI:** **DEFERRED** pós-VPS — **não** compete com truth gates.

#### 3.1 Catálogo validado + re-elevações Uma

| ID | Débito | Sev | Status | Horas | Prioridade | Veredito |
|----|--------|-----|--------|-------|------------|----------|
| **UX-01** | Web UI interativa | HIGH | **DEFERRED** | 80h+ (MVP ~40h) | **P3 pós-VPS** | Confirmado; stack candidata FastAPI+HTMX — **não** Next default |
| **UX-02** | Sem progress em comandos longos | **CRITICAL ops** | **OPEN** | 8h | **P0 ops** | Re-elevado; `rich.progress`; alvos: update/radar/crawl/PDF/golden_path |
| **UX-03** | Dual display rich vs print | MEDIUM | **PARTIAL** | 12h | P1 | `scripts/lib/display/` compartilhado |
| **UX-04** | Truncamento agressivo opp_intel (20c/10 cols) | **HIGH** ↑ | **OPEN** | 4h | **P1** | never-truncate: id, ranking, decisao, orgao_nome, status; max_col 60 |
| **UX-05** | Exit codes inconsistentes | LOW | **PARTIAL** | 2h | P2 | semântica documentada |
| **UX-06** | Flags `--format` vs `--json` | LOW | **OPEN** | 2h | P2 | |
| **UX-07** | Sem paginação interativa | LOW | **OPEN** | 6h | P3 | |
| **UX-08** | Erros silenciosos / pouca mensagem | MEDIUM | **PARTIAL** | 3h | P1 | `[ERROR]` + ação + `--debug` |
| **UX-09** | Coverage duplicado multi-CLI | MEDIUM | **PARTIAL** | 6h | P2 | |
| **UX-10** | Monólito generate-report-b2g (~7.4k LOC) | MEDIUM | **OPEN** | 16h | P2 | |
| **UX-11** | URLs não clicáveis | LOW | **OPEN** | 2h | P3 | |
| **UX-12** | Validação input pouco amigável | LOW→**MEDIUM impacto** | **OPEN** | 4h | P2 | PT-BR; choices argparse |
| **UX-13** | A11y incompleta charts HTML | LOW | **NEW** | 3h | P3 | |
| **UX-14** | Confusão cobertura vs sinal comercial | **HIGH** | **PARTIAL** | 3h | **P0 ops** | 2 seções M1/M2; disclaimer; GO color ≠ coverage |
| **UX-15** | Fragmentação de CLIs | MEDIUM | **PARTIAL** | 8h | P1 | workspace = facade **documentada**; legados power-user |
| **UX-16** | Mistura PT/EN em mensagens | LOW | **NEW** | 4h | P3 | PT-BR user-facing; EN em keys/IDs |
| **UX-17** | Ops health JSON-only | MEDIUM | **NEW** | 2h | **P0 ops** | `--human` ASCII; exit = JSON; **sem verde fixture** (dep. SYS-003/004) |
| **UX-18** | HTML comercial sem TOC sticky | LOW | **NEW** | 3h | P3 | |

#### 3.2 Adicionados Uma (continuidade v2 sem colidir IDs)

| ID | Débito | Sev | Status | Horas | Prioridade |
|----|--------|-----|--------|-------|------------|
| **UX-19** | Onboarding / help contextual (`--examples`) | MEDIUM | **OPEN** | 6h | P2 |
| **UX-20** | Sem confirmação antes de sobrescrever artefatos | LOW | **OPEN** | 2h | P3 |
| **UX-21** | Sumário human-readable pós-comando (radar/update) | MEDIUM | **OPEN** | 3h | **P1** / pack pré-VPS |
| **UX-22** | Tokens de marca PDF/HTML duplicados | LOW | **OPEN** | 2h | P3 |

**Nota de renumeração:** UX-13…17 do review **v2** ≠ IDs v3. Continuidades: v2-UX-13→**UX-19**, v2-UX-14→**UX-20**, v2-UX-17→**UX-21**.

#### 3.3 Pack pré-VPS UX (Onda honesty)

| # | ID | Horas | Critério honesty |
|---|----|-------|------------------|
| 1 | UX-02 | 8h | etapa + ETA; zero terminal morto |
| 2 | UX-17 | 2h | tabela humana + claim; exit = JSON |
| 3 | UX-14 | 3h | seções M1≠M2; disclaimer; GO ≠ coverage color |
| 4 | UX-04 | 4h | list legível sem `--json` |
| 5 | UX-21 | 3h | contagens + path + próximo passo |
| | **Total pack** | **~20h** | score UX alvo 7/10 |

#### Contagem Frontend/UX

| Status | N |
|--------|---|
| OPEN / NEW / PARTIAL | **21** |
| DEFERRED | **1** (UX-01) |
| RESOLVED 100% | **0** |
| **Total IDs** | **22** |
| Horas ativas (sem UX-01) | **≈ 101h** |
| Horas c/ UX-01 | **≈ 181h+** |

---

### 4. Segurança

**Fonte:** assessment v2 §4 · arch v3 · Story 1.1 · verificação 2026-07-17 · Dara DT-35

| ID | Débito | Sev | Status | Horas | Prioridade | Evidência |
|----|--------|-----|--------|-------|------------|-----------|
| **SEC-01** | SQL f-strings (injection teórico) | HIGH | **PARTIAL** | 2h residual | P1 | Story 1.1 caso principal; grep residual (= TD-016) |
| **SEC-02** | Service account JSON no repo | HIGH | **STILL OPEN** ⚠ **P0** | **1h** | **P0** | Story 1.1 Done **não** fecha; arquivo **presente** 2026-07-17. **Nova story HIGH-RISK** (não FAST): remove + `.gitignore` + rotação se exposto + `git grep` limpo |
| **SEC-03** | Senha hardcoded settings | HIGH | **PARTIAL** / residual | 0* | P1 residual | default settings ok; residual git + **DT-35** deploy |
| **SEC-04** | Dependências CVE | MEDIUM | **PARTIAL** | 2h | P1 | pip-audit + bandit no CI; processo contínuo |
| **SEC-05** | Estratégia secrets management | MEDIUM | **OPEN** | 3h | P2 | após SEC-02/DT-35 |
| **SEC-06** | Threat modeling | MEDIUM | **OPEN** | 4h | P2 | single-user SSH ok na fase; formalizar |
| **SEC-07** | Multi-tenant / RLS ausente | LOW | **ACCEPTED** (fase) | 0 | P3 | reabrir se multi-user |
| **SEC-08** | Headers sensíveis em raw crawl | MEDIUM | **MITIGATED** | 0 | — | resilience strip + ADR-020 |

| Status | N |
|--------|---|
| STILL OPEN P0 | **1** (SEC-02) ⚠ |
| PARTIAL | **3** (SEC-01,03,04) |
| OPEN | **2** (SEC-05,06) |
| ACCEPTED / MITIGATED | **2** |
| **Total IDs** | **8** |
| Horas ativas | **≈ 12h** (+ DT-35 1.5h no DB/deploy) |

---

### 5. Testes/QA

| ID | Débito | Sev | Status | Horas | Prioridade | Evidência |
|----|--------|-----|--------|-------|------------|-----------|
| **TQ-01** | Migrations silenciosas em test DB | MEDIUM | **OPEN** | 3h | P1 | conftest_db |
| **TQ-02** | Coverage threshold 10% (frouxo) | MEDIUM | **OPEN** | 2h | **P0 pré-VPS** | progressivo **10→30→45→60%**; denominator `scripts/` crítico; omit monólitos legados |
| **TQ-03** | Módulos críticos sem testes adequados | MEDIUM | **PARTIAL** | 4h | P1 | gaps contract/buyer_intel |
| **TQ-04** | Suite integração crawlers | HIGH | **PARTIAL** | 6h residual | **P1 blocker TD-010** | mín. PNCP + CIGA + suite verde **antes** de fatiar monitor |
| **TQ-05** | Métricas de qualidade dos testes | MEDIUM | **OPEN** | 4h | P2 | |
| **TQ-06** | Schema diagnostics defasados | MEDIUM | **NEW OPEN** | 0h* | P1 | = DT-28 |
| **TQ-07** | Live canary / truth gate não bloqueia claim VPS | HIGH | **NEW OPEN** | 4h | **P0 pré-VPS** | **FAIL** (não warn) se SYS-001/002 abertos ao autorizar VPS/timers; `ALLOW_PRE_VPS_WARN=1` só dev explícito |

| Status | N | Horas ativas |
|--------|---|--------------|
| OPEN / NEW / PARTIAL | **7** | **≈ 23h** (sem alias TQ-06) |

**Checklist adversarial F1–F7:** vira **gate de release pré-VPS** (subset CRITICAL = SYS-001…006), não só doc. Link: `PRE-VPS-FINAL-ADVERSARIAL-AUDIT.md` + TQ-07.

---

### 6. Observabilidade

| ID | Débito | Sev | Status | Horas | Prioridade | Canônico |
|----|--------|-----|--------|-------|------------|----------|
| **OBS-01** | Health sem mode/environment/fixture | HIGH | **OPEN** | 0* | **P0** | = SYS-003 |
| **OBS-02** | SLA freshness ≠ registry | HIGH | **OPEN** | 0* | **P0** | = SYS-004 |
| **OBS-03** | M1/M2 confundíveis em ops | HIGH | **PARTIAL** | 0* | P1 | = UX-14 |
| **OBS-04** | Sem job reconciliação coverage | MEDIUM | **PARTIAL** | 0* | P1 | = DT-14 |
| **OBS-05** | Perf live N/A (DB offline) | MEDIUM | **MITIGATED** (código) | 0 | — | upserts set-based; medir quando DB up |
| **OBS-06** | Checkpoint / DLQ obs incompleta | MEDIUM | **OPEN** | 4h | P1 | SYS-005/006 + mig 043+ |
| **OBS-07** | Logging estruturado inconsistente | LOW | **OPEN** | 2h | P3 | TD-005/006 |

| IDs | Horas canônicas extras | **≈ 6h** (OBS-06/07; resto alias) |

---

### 7. Dependências externas

| ID | Débito | Sev | Status | Horas | Prioridade |
|----|--------|-----|--------|-------|------------|
| **DEP-01** | MIDES BigQuery sem conta / SA | LOW | **OPEN** | — | P3 |
| **DEP-02** | TCE-SC e-Sfinge requer ICP-Brasil | MEDIUM | **BLOCKED** | — | P3 |
| **DEP-03** | DOM-SC / CIGA API key contratual | MEDIUM | **OPEN** | comercial | P2 |
| **DEP-04** | Provedor VPS/cloud TBD | MEDIUM | **OPEN** | 2h decisão | P2 |
| **DEP-05** | PNCP API v3 estabilidade / rate limits | MEDIUM | **OPEN** | contínuo | P2 |
| **DEP-06** | OpenAI quota / modelo | LOW | **OPEN** | — | P3 |
| **DEP-07** | CVE continuous audit (processo) | MEDIUM | **PARTIAL** | 0* | P1 | = SEC-04 |

---

### 8. Docs / Ambientes

| ID | Débito | Sev | Status | Horas | Prioridade | Canônico |
|----|--------|-----|--------|-------|------------|----------|
| **DOC-01** | Dual track migrations docs | HIGH | **OPEN** | 0* | **P0** | = DT-23 |
| **DOC-02** | `current-schema.sql` desatualizado | HIGH | **OPEN** | 0* | **P0** | = DT-24 |
| **DOC-03** | Preset AIOX nextjs ≠ Python | LOW | **OPEN** | 1h | P3 | |
| **DOC-04** | Operational data / fixtures no git | MEDIUM | **OPEN** | 0* | P1 | = SYS-015 |
| **DOC-05** | Workspace-guide vs CLIs legados | MEDIUM | **PARTIAL** | 3h | P1 | UX-15 |
| **ENV-01** | Apply 043–054 local não verificado | HIGH | **OPEN** | 0* | **P0** | = DT-33 (fusão 24) |
| **ENV-02** | VPS não provisionada; dual units no repo | HIGH | **OPEN** | 16h+ | **P0 pré-VPS** | **bloqueado** até SYS-001/002 + TQ-07 |
| **ENV-03** | Test DB / REQUIRE_TEST_DB não universal | MEDIUM | **OPEN** | 2h | P1 | DT-25 |
| **ENV-04** | Secrets em histórico git | MEDIUM | **PARTIAL** | 2h | P1 | SEC-03 residual |

---

### 9. Resolvidos desde v2 (audit trail — não silenciar)

| ID | Área | Resolução | Evidência |
|----|------|-----------|-----------|
| **TD-027** | Sistema | Matching unificado | `monitor.py` → `entity_matcher` |
| **TD-028** | Sistema | CI/CD fail-closed | `.github/workflows/ci.yml` |
| **TD-001** *(imports)* | Sistema | Package `ingestion/` | Story 1.1; dual path residual |
| **TD-019** | Sistema | Import `lib.cli_validation` | Story 1.1 |
| **TD-021** | Sistema | PNCP BASE_URL v3 | Story 1.1 + `.env.example` |
| **SEC-03** *(default)* | Segurança | Senha fora do default settings | env-only; residual deploy = DT-35 |
| **SEC-01** *(caso principal)* | Segurança | f-string SQL → `psycopg2.sql.Identifier` | Story 1.1; residual TD-016 |
| **SEC-08** | Segurança | Headers sensíveis stripped | resilience + ADR-020 |
| **DT-01…02,04…06,08,11,16…19** | Database | Schema/upserts/indexes v3 | dump + migs (DDL) |
| **SEC-04** *(parcial)* | Segurança | bandit + pip-audit no CI | processo contínuo ainda PARTIAL |
| **Stories 1.1–1.5** | Transversal | Segurança crítica, schema, universe, reconcile, coverage model | Done em `docs/stories/` |
| **Charts HTML executivo** | Frontend | real-vs-planned restaurados | commits docs 2026-07-17 (não fecha UX-xx CLI) |

**Nunca** listar SEC-02 como RESOLVED enquanto `config/mides-bigquery-sa.json` existir.

---

## Matriz de Priorização Final

### P0 — Pre-VPS + segurança + honesty (~16 itens, ~72–80h)

Ordem de execução recomendada (topológica):

| Ordem | ID | Débito | Área | Horas | Dependências |
|-------|-----|--------|------|-------|--------------|
| 1 | **SEC-02 / TD-029** | Remover SA JSON + gitignore + rotação | Segurança | 1h | — |
| 2 | **DT-35 / DT-07res** | Defaults deploy/seed fail-closed | DB / Sec | 1.5h | — |
| 3 | **SYS-005** | Checkpoint tipado fail-closed | Sistema | 3h | — |
| 4 | **SYS-006** | Adapter CIGA sem success de pipeline | Sistema | 3h | — |
| 5 | **SYS-003 / OBS-01** | Health honesty (mode/env/fixture) | Sistema | 4h | SYS-005/006 preferível antes |
| 6 | **SYS-004 / OBS-02** | SLA do registry | Sistema | 3h | — |
| 7 | **SYS-001** | Writer único PostgreSQL (B) | Sistema | 12h | 3–6 |
| 8 | **SYS-002** | Uma família systemd oficial | Sistema / Env | 8h | SYS-001 |
| 9 | **DT-24 + DT-33** | Verify HEAD + regen dump/SHA | Database | 2.5h | DB up |
| 10 | **DT-23 / DOC-01** | Política única migrations fail-closed | Database | 6h | — (∥ schema) |
| 11 | **DT-28 fatia** | diagnostics sem FKs fantasmas | Database | 2.5h | DT-24/33 |
| 12 | **TQ-02** | Coverage progressivo (→30% min) | Testes | 2h | baseline |
| 13 | **TQ-07** | Truth gate FAIL se dual runtime | Testes | 4h | SYS-001/002 |
| 14 | **UX-02** | Progress indicators | UX | 8h | — (∥ seguro) |
| 15 | **UX-17** | `ops/health --human` | UX | 2h | DoD honesty c/ SYS-003 |
| 16 | **UX-14** | Labels M1≠M2 no workspace | UX | 3h | — |
| — | **ENV-02** | Provision/timers oficiais | Env | 16h+ | **só após 1–13** |

**Saída P0:** evidência de **uma** verdade de persistência + health honesto + schema HEAD + secrets limpos + gate que **impede** claim VPS falso.

### P1 — Curto prazo (amostra, ~95h)

| ID | Área | Horas | Depende de |
|----|------|-------|------------|
| UX-04, UX-21 | UX pack residual | 7h | UX-02 |
| UX-03, UX-08, UX-15 | CLI consistency | 23h | — |
| SEC-01 residual | Seg | 2h | — |
| SEC-04 continuous | Seg | 2h | — |
| DT-28+29 tooling full | DB | 2h residual | DT-28 fatia |
| DT-25, DT-26, DT-27, DT-14 | DB | 11h | writer único p/ DT-27 ideal |
| TQ-01, TQ-03, TQ-04 | QA | 13h | TQ-04 **antes** TD-010 |
| TD-010 | Sistema | 20h | SYS-001 + TQ-04 |
| TD-011 / TD-001 | Sistema | 6–12h | SYS-001 |
| SYS-007 | Sistema | 4h | — |
| SYS-015 / DOC-04 | Ops data git | 2h | — |
| OBS-06 | Obs | 4h | SYS-005/006 |
| TD-031, TD-032 residual | Docs/Obs | 10h | — |
| DOC-05 | Docs | 3h | UX-15 |

### P2–P3 — resumo

| Prioridade | Exemplos | Horas aprox. |
|------------|----------|--------------|
| **P2** | TD-002…004,008,009,013,017,018,022,034; DT-09,10,12,15,22,32; UX-05,06,09,10,12,19; SEC-05,06; SYS-009,012,013; DEP-03…05; ENV-03 | **~120h** |
| **P3** | cosméticos TD; DT-13,21,30,31; UX-01,07,11,13,16,18,20,22; SYS-010,011,014; DEP-01,02,06; DOC-03; TD-025 ORM | **~90h+** (c/ UX-01 80h+) |
| **Produto pós-truth** | **SYS-008** M2 elevação | **40h+** |

---

## Plano de Resolução

Waves alinhadas à preferência **aiox-brownfield** (security → build/tests → architecture → coupling → performance → UX ops → non-critical), com dependências topográficas respeitadas.

### Wave 1 — Security + Integrity (~18h)

**Objetivo:** zero credenciais óbvias no tree; schema truth; apply path único.

| Ordem | IDs | Horas | Critério de sucesso |
|-------|-----|-------|---------------------|
| 1.1 | SEC-02 / TD-029 | 1h | `test ! -f config/mides-bigquery-sa.json`; pattern no `.gitignore`; rotação se chave commitada |
| 1.2 | DT-35 / DT-07 residual | 1.5h | zero default `smartlic_local` em deploy/seed; `${PG_PASSWORD:?}` / DSN fail-closed |
| 1.3 | DT-24 + DT-33 | 2.5h | `_migrations` == HEAD; dump contém 043–054; SHA em DB-AUDIT |
| 1.4 | DT-23 / DOC-01 | 6h | só `db/setup_db.sh`; legacy apply exit 1 sem ALLOW_LEGACY |
| 1.5 | DT-28 + DT-34 (+ início DT-29) | 2.5–4h | diagnostics exit 0 em HEAD; sem exigir FKs dropadas |
| 1.6 | SEC-01 residual / TD-016 | 2h | grep f-string SQL = 0 em paths quentes |
| 1.7 | ENV-04 / re-scan git | 2h | `git grep smartlic_local` + SA patterns documentados |

**Freeze:** não provisionar VPS com defaults fracos.

### Wave 2 — Build / Tests / Observability (~25h)

**Objetivo:** gates honestos; health não mente; coverage sobe sem cegar CI.

| Ordem | IDs | Horas | Critério de sucesso |
|-------|-----|-------|---------------------|
| 2.1 | SYS-005, SYS-006 | 6h | checkpoint tipado; adapter sem success pipeline |
| 2.2 | SYS-003/OBS-01, SYS-004/OBS-02 | 7h | fixture ≠ live healthy; SLA do registry |
| 2.3 | TQ-02 | 2h | threshold **30%** (passo 1); omit list documentada |
| 2.4 | TQ-07 + F1–F7 gate | 4h | FAIL se dual runtime ao claim VPS |
| 2.5 | TQ-01, TQ-06(=DT-28 done) | 3h | migrations test DB não silenciosas |
| 2.6 | OBS-06, TD-032 residual | 4h+ | DLQ/checkpoint observáveis |
| 2.7 | DT-25 / ENV-03 | 3h | smoke schema CI com Postgres service (ideal) |

### Wave 3 — Architecture frontiers: single runtime (~20h)

**Objetivo:** **uma** verdade de persistência — fim do split-brain.

| Ordem | IDs | Horas | Critério de sucesso |
|-------|-----|-------|---------------------|
| 3.1 | **SYS-001** (desenho B) | 12h | path oficial grava PG; resilient → FetchResult → monitor writer |
| 3.2 | **SYS-002** | 8h | uma família units oficiais; legados non-prod |
| 3.3 | TQ-07 revalidação | 0 (já Wave 2) | gate verde **somente** com writer único |
| 3.4 | Follow-up Reversa | — | recomendar re-extração crawl/resilience/ops **após Done** (não automático) |

**Bloqueio (C6):** `ENV-02` timers oficiais / `VPS_OPERATIONAL` **só depois** desta wave + evidência.

### Wave 4 — Coupling (~40h)

**Objetivo:** reduzir monólitos e dual paths **com rede de testes**.

| Ordem | IDs | Horas | Critério de sucesso |
|-------|-----|-------|---------------------|
| 4.1 | **TQ-04** residual | 6h | PNCP + CIGA contract + suite verde |
| 4.2 | **TD-010** fatiar monitor | 20h | monitor &lt; 1000 LOC; zero regressão crawl |
| 4.3 | **TD-011 / TD-001** unificar PNCP | 6–12h | um client path canônico |
| 4.4 | TD-003, TD-004 | 6h | types + cache IBGE seguro |
| 4.5 | SYS-007 | 4h | snapshot hash SC Compras bulk |

### Wave 5 — Performance & data integrity residual (~20h)

| Ordem | IDs | Horas | Critério de sucesso |
|-------|-----|-------|---------------------|
| 5.1 | DT-26 VALIDATE | 2h | pre-check + VALIDATE off-peak |
| 5.2 | DT-27 orfandade contracts | 3h | view % órfãos no health |
| 5.3 | DT-14 / OBS-04 job reconcile | 3h | timer chama reconcile, não só report |
| 5.4 | DT-22 retention cron | 2h | política documentada + job |
| 5.5 | DT-15, DT-09/10 batch | 4h | CHECKs / partial unique |
| 5.6 | DT-32 rollback pack | 5h | `head-to-042` dry-run doc |
| 5.7 | OBS-05 perf live | — | medir quando DB up (baseline) |

### Wave 6 — UX ops (CLI honesty, **não** web) (~45h pack+P1)

| Ordem | IDs | Horas | Critério de sucesso |
|-------|-----|-------|---------------------|
| 6.1 | **UX-02** (se não na Wave 1 paralela) | 8h | progress nos 4 alvos |
| 6.2 | **UX-17** | 2h | `--human` ASCII |
| 6.3 | **UX-14** | 3h | M1≠M2 visual + disclaimer |
| 6.4 | **UX-04** | 4h | never-truncate canônico |
| 6.5 | **UX-21** | 3h | sumário pós-comando |
| 6.6 | UX-03 + UX-08 + UX-15 | 23h | display lib + workspace home + erros |
| 6.7 | UX-19 | 6h | `--examples` / epilog help |

**Proibido nesta wave:** spike SPA/Next.js (UX-01).

### Wave 7 — Non-critical / estratégico (~90h+ + SYS-008 40h+)

| Bloco | IDs | Notas |
|-------|-----|-------|
| Produto cobertura | **SYS-008** | só com Onda truth fechada |
| Secrets/threat | SEC-05, SEC-06 | após SEC-02 limpo |
| UX polish | UX-05…13,16,18,20,22 | |
| Web UI | **UX-01** | pós VPS + CLI diário estável + demanda multi-user |
| DB housekeeping | DT-12,13,21,30,31 | |
| Sistema cosmético | TD-005…007,012,020,025 | |
| Deps externas | DEP-01…03, SYS-010…012 | contrato/orçamento |
| Docs preset | DOC-03 / SYS-014 | 1h |

### Dependências cruzadas (grupos)

```text
Grupo Security:
  SEC-02 ∥ DT-35 → SEC-05 → SEC-06
  SEC-01 residual ∥ SEC-04 continuous

Grupo Truth:
  SYS-005/006 → SYS-003/004 → SYS-001/002 → TQ-07 → ENV-02 (timers)

Grupo Schema:
  DT-33+24 → DT-23/DOC-01 → DT-28/29/34 → DT-25

Grupo Runtime unificado:
  SYS-001/002 → TQ-04 → TD-010 → TD-011/001 → SYS-008

Grupo UX ops:
  UX-02 ∥ (UX-17 após honesty health) ∥ UX-14 → UX-04 → UX-21 → UX-03/15 → UX-01 (último)

Grupo DB integrity:
  writer único → DT-27 → DT-14 cron → VALIDATE DT-26
```

**Ciclos:** nenhum. Topologia viável.

---

## Riscos e Mitigações (from QA)

| # | Risco | Áreas | Sev | Mitigação |
|---|-------|-------|-----|-----------|
| **CR-v3-001** | Split-brain FS vs PG + dual systemd | Sistema, DB, Obs, Deploy | **CRITICAL** | Wave 3 writer único (B); freeze timers; TQ-07 fail-closed |
| **CR-v3-002** | Health healthy com fixtures + SLA hardcoded + operador cego | Sistema, Obs, UX | **CRITICAL** | SYS-003/004 + UX-17; fixture nunca pinta live |
| **CR-v3-003** | Credenciais compostas: SA JSON presente + smartlic_local deploy + git history | Seg, Deploy, DB | **CRITICAL** | SEC-02 + DT-35 Wave 1; re-scan; **não FAST** |
| **CR-v3-004** | Dump 07-14 ≠ HEAD 043–054 + dual track + diagnostics mentiroso | DB, Docs, CI | **HIGH** | Story P0 DT-24/33 + DT-23 + DT-28 |
| **CR-v3-005** | M1 lido como M2 ou como GO | Produto, UX, Comercial | **HIGH** | UX-14 P0 ops; M2=0% honesto; disclaimer workspace |
| **CR-v3-006** | Refactor TD-010 sem TQ-04 | Sistema, Crawl | **HIGH** | TQ-04 antes; SYS-001 primeiro |
| **CR-v3-007** | `LOCAL_RESILIENCE_READY` = VPS / 95% | Gestão, Ops | **HIGH** | C6; claims separados no health; TQ-07 |
| **CR-v3-008** | Wave multi-área sem sequenciamento | Gestão | MEDIUM | Wave 1 secrets → Wave 2 health → Wave 3 runtime; UX-02 paralelo seguro |
| **CR-v3-009** | Live DB offline → RESOLVED de dados superestimado | DB, QA | MEDIUM | RESIDUAL-VERIFY-2026-07-17; smoke obrigatório |

### Continuidade riscos v2

| Risco v2 | Estado v3 |
|----------|-----------|
| CR-001 monitor quebra crawlers | Mitigado em prioridade (TD-010 após SYS-001); residual = CR-v3-006 |
| CR-002 credenciais compostas | **Ativo** como CR-v3-003 (SEC-02 **confirmado presente**) |
| CR-003 DT-02 sem rollback | Eixo resolvido; residual DT-32 (P2) |
| CR-004 UX-01 bloqueado | CI resolvido; UX-01 DEFERRED — risco rebaixado |
| CR-005 Sprint 0 descoordenado | Substituído por Waves 1–7 |

---

## Critérios de Sucesso

### Métricas pós-resolução (globais)

| Métrica | Baseline 2026-07-17 | Alvo | Ferramenta |
|---------|---------------------|------|------------|
| Claim VPS | proibido | só com SYS-001/002 + TQ-07 verdes | health `claim=` |
| M2 cobertura operacional | **0%** | 95% (alvo produto, pós SYS-008) | coverage contract |
| M1 ≠ M2 na CLI | PARTIAL | seções distintas + disclaimer | workspace snapshot |
| SA JSON no tree | **presente** | **ausente** | `test ! -f` + CI |
| Defaults smartlic_local em deploy | presente | **0** | `git grep` |
| Dual runtime oficial | 2 famílias | **1** oficial | systemd inventory |
| Health fixture → live healthy | possível | **impossível** | unit + CLI |
| `_migrations` vs HEAD | não verificado live | max version == HEAD | SQL + diagnostics |
| Coverage CI | 10% | 30% → 45% → ≥60% | pytest --cov |
| monitor.py LOC | ~1581 | &lt; 1000 (pós TD-010) | wc -l |
| Progress em comandos longos | 0 | 4 alvos | checklist UX-02 |
| Score consistência UX | ~5/10 | **7/10** pós pack | Uma checklist |

### DoD binário por P0 (GAP-v3-003)

| ID | Fechado quando |
|----|----------------|
| SYS-001 | 0 writers FS-only no path oficial; evidence row em PG no happy path |
| SYS-002 | 1 família units oficiais; legados disabled ou tagged non-prod |
| SYS-003 | fixture mode nunca overall=healthy + claim operational_live |
| SYS-004 | thresholds lidos do registry; teste unitário de divergência |
| SYS-005 | schema inválido levanta erro (não pass) |
| SYS-006 | adapter CIGA não grava success de pipeline |
| SEC-02 | arquivo ausente + gitignore + prova CI |
| DT-23 | legacy apply fail-closed; docs apontam só `db/` |
| DT-24+33 | `_migrations` HEAD + dump com objetos 043–054 + SHA |
| TQ-02 | CI vermelho abaixo do patamar da policy da branch |
| TQ-07 | gate FAIL sem `ALLOW_PRE_VPS_WARN=1` se dual runtime e claim VPS |
| UX-02 | progress visível nos 4 alvos |
| UX-14 | 2 seções + disclaimer + cores distintas |
| UX-17 | `--human` + exit codes idênticos ao JSON |

### Cobertura mínima antes de TD-010 (TQ-04)

| Fonte | Mínimo |
|-------|--------|
| PNCP | 1 happy path upsert + 1 failure |
| CIGA | 1 adapter contract (sem success prematuro) |
| SC Compras | 1 snapshot/hash **ou** skip explícito se SYS-007 aberto |
| Regressão monitor | suite existente 100% verde |

---

## Respostas formais às perguntas @qa (C5)

### Q1 — TQ-02 threshold progressivo

**10% → 30% → 45% → ≥60%** em PRs separados. Denominator preferencial: `scripts/` crítico (`crawl`, `opportunity_intel`, `ops`, `schema`, `coverage`). **Omitir** monólitos legados (`generate-report-b2g.py`) do denominator inicial.

### Q2 — TQ-07 fail vs warn

**FAIL** ao autorizar claim VPS / enable timers oficiais. **WARN** só com `ALLOW_PRE_VPS_WARN=1` (dev). Default **nunca** fail-open.

### Q3 — SEC-02 Story 1.1 Done vs arquivo presente

**Nova story HIGH-RISK** (ou “1.1 residual security”). **Proibido FAST**. DoD: arquivo ausente + gitignore + CI limpa + rotação se aplicável.

### Q4 — TQ-04 antes de TD-010

**Sim.** Mínimo PNCP + CIGA + suite verde. Sem isso, TD-010 = **FAIL gate**.

### Q5 — Falsos verdes F1–F7

Checklist adversarial = **gate de release pré-VPS** (CRITICAL = SYS-001…006). LOW (ex. F7) pode warn.

### Q6 — Re-extração Reversa após SYS-001/002

**Sim, recomendar** re-extração `_reversa_sdd` de crawl/resilience/ops **após Done** — follow-up de story, não automático (protocolo AIOX-Reversa §9).

### Respostas Architect → especialistas (consolidadas)

| Tema | Decisão FINAL |
|------|----------------|
| SYS-001 desenho | **(B) monitor único writer** (Dara); (C) só transitório ≤1 sprint |
| DT-24+33 | **Uma story** 2.5h |
| DT-23 hours | **6h** |
| DT-07 | **PARTIAL** + **DT-35** |
| UX-02 | **CRITICAL ops** / P0 execução; dual-label OK |
| UX-04 | **HIGH** |
| UX-01 | **DEFERRED** pós-VPS |
| UX-19…22 | **Incorporados** |
| Live RESOLVED | DDL ok; dados = residual verify |

---

## Próximos passos do Brownfield

| Fase | Agente | Artefato | Status |
|------|--------|----------|--------|
| 1–3 | @architect / @data-engineer / @ux | arch + DB-AUDIT + frontend-spec v3 | ✅ |
| 4 | @architect | technical-debt-DRAFT v3 | ✅ |
| 5 | @data-engineer | db-specialist-review v3 | ✅ |
| 6 | @ux-design-expert | ux-specialist-review v3 | ✅ |
| 7 | @qa | qa-review v3 — APPROVED WITH CONDITIONS | ✅ |
| **8** | **@architect** | **este documento — FINAL v3.0** | ✅ |
| 9 | @analyst | TECHNICAL-DEBT-REPORT executivo | ⏳ |
| 10 | @pm / @sm | epics + stories (Wave 1 pre-VPS first) | ⏳ |

### Recomendação de epics (input Phase 10)

1. **EPIC Pre-VPS Truth** — Waves 1–3 (SEC-02, DT-35, SYS-001…006, schema, TQ-07)  
2. **EPIC CLI Honesty** — Wave 6 pack (UX-02/14/17/04/21)  
3. **EPIC Runtime Unification & Coupling** — Wave 4 (TQ-04, TD-010, PNCP)  
4. **EPIC Data Integrity Residual** — Wave 5  
5. **EPIC Coverage Product (M2)** — SYS-008 *após* epic 1  
6. **Backlog Non-critical** — Wave 7 incl. UX-01 quando critérios reabrirem  

---

## Referências

- `docs/architecture/system-architecture.md` v3.0  
- `supabase/docs/DB-AUDIT.md` v3.0 · `supabase/docs/SCHEMA.md` v3.0  
- `docs/frontend/frontend-spec.md` v3.0  
- `docs/prd/technical-debt-DRAFT.md` v3.0  
- `docs/prd/technical-debt-assessment.md` v2.0 (2026-07-13)  
- `docs/reviews/db-specialist-review.md` v3.0 (Dara)  
- `docs/reviews/ux-specialist-review.md` v3.0 (Uma)  
- `docs/reviews/qa-review.md` v3.0 (Quinn) — gate **APPROVED WITH CONDITIONS**  
- Stories 1.1–1.5 Done · PRE-VPS adversarial audit · ADR-007/020/021  
- `.aiox/gotchas.json`  

---

## YAML machine-readable (totais)

```yaml
technical_debt_assessment:
  version: "3.0 FINAL"
  date: "2026-07-17"
  authors: ["Aria (@architect)", "Dara (@data-engineer)", "Uma (@ux-design-expert)", "Quinn (@qa)"]
  qa_gate: "APPROVED WITH CONDITIONS"
  conditions_closed: [C1, C2, C3, C4, C5, C6]
  operational_claims:
    LOCAL_RESILIENCE_READY: true
    VPS_OPERATIONAL: false
    m2_operational_coverage: "0/1093 (0%)"
    m1_commercial_signal: "116/1093 (10.61%)"
    sa_json_present: true
    live_db_verified_2026_07_17: false
  inventory:
    ids_tracked_gross: 140
    ids_canonical_active: 118
    resolved_since_v2: 22
    accepted_phase: 4
    p0_class: 16
    high: 14
    medium: 55
    low: 31
  effort_hours:
    pre_vps_wave: { min: 72, max: 80, mid: 76 }
    database_open_dara: 46
    ux_active_without_web: 101
    total_active_without_ux01_without_m2: { min: 310, max: 360, mid: 335 }
    total_with_ux01_full: { min: 390, max: 440, mid: 415 }
    sys008_m2_product: 40
    pre_vps_db_mustfix: { min: 12, max: 14 }
    pre_vps_ux_pack: 20
  design_decisions:
    sys001_writer: "B_monitor_single_writer"
    dt24_dt33: "fused_story_2.5h"
    dt23_hours: 6
    dt07_status: "PARTIAL"
    ux02_severity: "CRITICAL_ops"
    ux04_severity: "HIGH"
    ux01: "DEFERRED_post_vps"
  waves:
    1: "security_integrity"
    2: "build_tests_observability"
    3: "architecture_single_runtime"
    4: "coupling"
    5: "performance_data_integrity"
    6: "ux_ops_cli_honesty"
    7: "non_critical_strategic"
  blocked:
    official_timers: true
    vps_operational_claim: true
    until: ["SYS-001", "SYS-002", "TQ-07", "SEC-02", "schema_truth"]
  next:
    - "@analyst → executive TECHNICAL-DEBT-REPORT"
    - "@pm/@sm → epics pre-VPS wave first"
```

---

*Documento FINAL gerado por Aria (Visionary Architect) em 2026-07-17 — Brownfield Discovery Phase 8.*  
*Incorpora: DRAFT v3.0 · Dara DB v3.0 · Uma UX v3.0 · Quinn QA v3.0 (APPROVED WITH CONDITIONS C1–C6).*  
*Status: COMPLETO — fonte definitiva de planejamento. `LOCAL_RESILIENCE_READY` · **NÃO** `VPS_OPERATIONAL`.*  
*Próxima etapa: @analyst (relatório executivo) → @pm/@sm (epics Wave 1).*
