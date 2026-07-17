# Technical Debt Assessment — DRAFT

## Para Revisão dos Especialistas

| Campo | Valor |
|-------|-------|
| **Versão** | **3.0 DRAFT** |
| **Data** | **2026-07-17** |
| **Autor** | Aria (@architect) |
| **Origem** | Brownfield Discovery — Fase 4: consolidação Phases 1–3 (refresh) |
| **Baseline anterior** | v2.0 FINAL 2026-07-13 (**79 débitos** no assessment final) |
| **Draft predecessor** | v2.0 DRAFT 2026-07-13 (60 débitos Phases 1–3; assessment elevou a 79) |
| **Fontes** | `docs/architecture/system-architecture.md` v3.0 · `supabase/docs/DB-AUDIT.md` v3.0 · `docs/frontend/frontend-spec.md` v3.0 · `docs/prd/technical-debt-assessment.md` v2 |

---

## Changelog vs v2 (2026-07-13 → 2026-07-17)

### Contexto de escala

| Métrica | v2 (2026-07-13) | v3 (2026-07-17) |
|---------|-----------------|-----------------|
| Commits desde assessment v2 | — | **~131** |
| Python em `scripts/` | ~menor | **270 arquivos / ~141.7k LOC** |
| `test_*.py` | menor | **127** |
| Migrations SQL `db/migrations/` | núcleo v2/v3 | **59** (~9k LOC) |
| Units systemd | parcial | **49** (services + timers) |
| Universo canônico SC 200 km | em evolução | **1.093** entidades |
| ESR (source mapping) | — | **1.093/1.093** |
| Sinal comercial recente (M1) | — | **116/1.093 (10,61%)** |
| Cobertura operacional estrita (M2) | claim frágil | **0/1.093 (0%)** — honesto |
| CI/CD | ausente | **GitHub Actions fail-closed** |
| Matching unificado | duplicado | **monitor → entity_matcher** |
| Stories P0 1.1–1.5 | planejadas | **Done** |

### O que foi resolvido (audit trail — não silenciar)

| ID | Área | Resolução | Evidência |
|----|------|-----------|-----------|
| **TD-027** | Sistema | Matching unificado | `monitor.py` importa `entity_matcher` |
| **TD-028** | Sistema | CI/CD fail-closed | `.github/workflows/ci.yml` (ruff → mypy → pytest → bandit → pip-audit) |
| **TD-001** *(imports quebrados)* | Sistema | Package `ingestion/` + imports corrigidos (Story 1.1) | Story 1.1 Done — **reframe residual:** dual path PNCP permanece como TD-001 STILL OPEN (HIGH) |
| **TD-019** | Sistema | Import `lib.cli_validation` | Story 1.1 Done |
| **TD-021** | Sistema | PNCP BASE_URL v3 alinhado | Story 1.1 + `.env.example` |
| **SEC-03 / DT-07** | Segurança / DB | Senha hardcoded removida do default | `settings.py` via `DATABASE_URL` / env; residual histórico git |
| **SEC-01 / TD-016** *(caso principal)* | Segurança | f-string SQL em `_upsert_raw_records` → `psycopg2.sql.Identifier` | Story 1.1; **residual** TD-016 STILL OPEN (risco residual revalidar) |
| **DT-01 / DT-17** | Database | match_logging presente | Dump + mig 005-v2 / 010 |
| **DT-02** | Database | Tabelas v3 aplicadas | hierarchy, evidence, opportunity_*, eng, etc. |
| **DT-04 / DT-05** | Database | Upserts set-based | CTE + ON CONFLICT; 044/050 |
| **DT-06** | Database | UNIQUE `cnpj_8` | `uq_spe_cnpj_8` |
| **DT-08** | Database | CHECK `esfera_id` | `chk_pncp_raw_bids_esfera_id` |
| **DT-11** | Database | GIN trigram objeto_compra | `idx_bids_objeto_compra_gin` |
| **DT-16** | Database | GIN contracts | Presente no dump |
| **DT-18** | Database | Soft-delete contracts | `is_active` |
| **DT-19** | Database | FK órgão em bids | via `orgao_cnpj_8` (041a); *validar NOT VALID residual* |
| **Stories 1.1–1.5** | Transversal | Segurança crítica, schema unificado, universe authority, reconcile open tenders, coverage model | Status **Done** em `docs/stories/` |
| **SEC-04** *(parcial)* | Segurança | bandit + pip-audit no CI | CI fail-closed; processo contínuo de CVE ainda amadurece |
| **Charts HTML executivo** | Frontend | real-vs-planned restaurados/responsivos | commits docs 2026-07-17 (não fecha UX-xx de CLI) |

### O que permanece (legado v2 ainda ativo)

- God-module `monitor.py` (~1581 LOC) — **TD-010**
- Dualidade PNCP (adapter + bids_crawler + resilient) — **TD-001 / TD-011**
- SA JSON ainda no tree — **TD-029 / SEC-02** ⚠ (Story 1.1 marcou Done; arquivo **ainda presente** em 2026-07-17)
- Coverage CI frouxo (`--cov-fail-under=10`) — **TD-026 / TQ-02**
- UX CLI: progress, truncation, dual rich/print, web UI deferred
- Débitos DB legado OPEN: DT-09,10,12,13,15 + PARTIAL DT-14,22
- SEC-05/06 (secrets strategy, threat model) não iniciados

### O que é NOVO desde 2026-07-13

| Classe | IDs | Origem |
|--------|-----|--------|
| **Pre-VPS / resiliência (P0)** | SYS-001…SYS-007 | `PRE-VPS-FINAL-ADVERSARIAL-AUDIT.md` |
| **Produto / ops** | SYS-008…SYS-015 | arch v3 + gotchas + ADR-007/020 |
| **Database pós-054** | DT-23…DT-33 | DB-AUDIT v3.0 |
| **UX plataforma B2G** | UX-13…UX-18 | frontend-spec v3.0 |
| Plataforma B2G | ESR, coverage contract 5+1, workspace facade, resilience ADR-021, official_acts | 131 commits / target arch |

### Posição pré-VPS (gate de verdade)

> **READY** para *iniciar provisionamento futuro* no eixo de mecânica de resiliência local (`LOCAL_RESILIENCE_READY`).  
> **NÃO READY** para timers “novos oficiais” em host remoto enquanto **SYS-001…SYS-006** (e dual runtime SYS-002) permanecerem abertos.  
> M2 = **0%** — meta 95% é alvo de produto, **não claim atual**.

---

## 1. Débitos de Sistema

Fonte: `docs/architecture/system-architecture.md` v3.0  
Legenda: **RESOLVED** · **STILL OPEN** · **PARTIAL** · **NEW** · **ACCEPTED**

### 1.1 Pre-VPS blockers (NEW — 🔴 P0)

| ID | Débito | Severidade | Status | Esforço | Prioridade | Evidência |
|----|--------|------------|--------|---------|------------|-----------|
| **SYS-001** | Split-brain: `resilient_cycle` grava FS, não PostgreSQL | **P0 / CRITICAL** | **NEW OPEN** | 12h | **P0 pré-VPS** | Audit F1 — caminho resiliente paralelo ≠ monitor DB |
| **SYS-002** | Dual systemd runtimes (`extra-crawl-*` FS vs `pncp-crawl-*` / monitor DB) | **P0 / CRITICAL** | **NEW OPEN** | 8h | **P0 pré-VPS** | Audit F2 — 49 units; duas verdades de persistência |
| **SYS-003** | Health “healthy” após fixtures (falso verde) | **P0 / CRITICAL** | **NEW OPEN** | 4h | **P0 pré-VPS** | Audit F3 — `ops/health` não distingue fixture/live |
| **SYS-004** | Freshness SLA hardcoded ≠ registry (ex.: PNCP 24h vs 4h) | **P0 / CRITICAL** | **NEW OPEN** | 3h | **P0 pré-VPS** | Audit F4 — SLA deve vir de `coverage_slas.yaml` / registry |
| **SYS-005** | Checkpoint schema engolido (`TypeError: pass`) | **P0 / CRITICAL** | **NEW OPEN** | 3h | **P0 pré-VPS** | Audit F5 — fail-open em schema inválido |
| **SYS-006** | CIGA salva checkpoint success no adapter (sucesso operacional prematuro) | **P0 / CRITICAL** | **NEW OPEN** | 3h | **P0 pré-VPS** | Audit F6 — adapter não deve marcar success de pipeline |

### 1.2 Produto / ops (NEW)

| ID | Débito | Severidade | Status | Esforço | Prioridade | Evidência |
|----|--------|------------|--------|---------|------------|-----------|
| **SYS-007** | SC Compras bulk sem snapshot imutável (hash) | HIGH | **NEW OPEN** | 4h | P1 | Audit F7 |
| **SYS-008** | M2 operational coverage **0/1093** | HIGH | **NEW OPEN** | 40h+ | P1 *(após SYS-001…006)* | Coverage contract; honesty OK, gap de produto |
| **SYS-009** | Provedor cloud / VPS não definido | MEDIUM | **STILL OPEN** | 2h | P2 | ADR-007 |
| **SYS-010** | MIDES BigQuery sem conta GCP | LOW | **STILL OPEN** | — | P3 | gotcha EPIC-COVERAGE (PULADO) |
| **SYS-011** | TCE-SC e-Sfinge inviável sem ICP-Brasil | MEDIUM | **STILL OPEN** | — | P3 | gotcha (custo R$300–800/ano) |
| **SYS-012** | DOM-SC API key / contrato CIGA | MEDIUM | **STILL OPEN** | 4h+ | P2 | gotcha + contrato comercial |
| **SYS-013** | Recall benchmark NOT_READY | MEDIUM | **STILL OPEN** | 8h | P2 | coverage contract |
| **SYS-014** | Preset AIOX `nextjs-react` ≠ stack real (Python CLI) | LOW | **STILL OPEN** | 1h | P3 | confusão de agentes |
| **SYS-015** | Operational data accidental no git | MEDIUM | **STILL OPEN** | 2h | P1 | ADR-020 disciplina |

### 1.3 Legado TD-* (v2 → v3)

| ID | Débito | Severidade | Status | Esforço | Prioridade | Evidência |
|----|--------|------------|--------|---------|------------|-----------|
| **TD-001** | Dual path PNCP async legado (`bids_crawler`) | HIGH | **STILL OPEN** *(reframe)* | 6h | P1 | Imports quebrados **RESOLVED** Story 1.1; dual path permanece |
| **TD-002** | DEFAULT_DSN duplicado settings vs CLIs | MEDIUM | **STILL OPEN** | 1h | P2 | settings alias + CLIs |
| **TD-003** | Type hints / funções longas em monitor | MEDIUM | **STILL OPEN** | 4h | P2 | monitor ~1581 LOC |
| **TD-004** | Cache IBGE global mutável | MEDIUM | **STILL OPEN** | 2h | P2 | race potencial |
| **TD-010** | `monitor.py` god-module | HIGH | **STILL OPEN** | 20h | P1 *(após unificar runtime)* | Reduzido de ~1756 → ~1581; ainda acoplado |
| **TD-011** | Duas+ implementações PNCP | HIGH | **STILL OPEN** | 6h | P1 | adapter sync + bids_crawler + resilient adapter |
| **TD-015** | Healthcheck unificado | MEDIUM | **PARTIAL** | 4h | P1 | `ops/health.py` existe; SYS-003/004 bloqueiam “unificado honesto” |
| **TD-016** | SQL com f-strings (risco residual) | HIGH | **STILL OPEN** / residual | 2h | P1 | Story 1.1 fixou caso principal; revalidar codebase |
| **TD-017** | Scripts hyphen + underscore | MEDIUM | **STILL OPEN** | 4h | P2 | vários `*-*.py` top-level |
| **TD-018** | `backend/` duplica config | MEDIUM | **STILL OPEN** | 1h | P2 | `backend/sectors_data.yaml` |
| **TD-020** | Stubs ingestion transformer | LOW | **STILL OPEN** / mitigado | 4h | P3 | package evoluiu; stubs parciais |
| **TD-025** | Sem ORM / SQL espalhado | MEDIUM | **STILL OPEN** | 20h+ | P3 | aceitável se parametrizado |
| **TD-026** | Coverage threshold CI **10%** (frouxo) | MEDIUM | **STILL OPEN** | 2h | **P0 pré-VPS** *(gate rigor)* | `--cov-fail-under=10` |
| **TD-027** | Matching duplicado monitor vs matcher | HIGH | **RESOLVED** | — | — | entity_matcher canônico |
| **TD-028** | Sem CI/CD | HIGH | **RESOLVED** | — | — | GitHub Actions |
| **TD-029** | SA JSON no repo | HIGH | **STILL OPEN** ⚠ | 1h | **P0** | `config/mides-bigquery-sa.json` **ainda presente** |
| **TD-030** | Gaps de teste schema/coverage | MEDIUM | **PARTIAL** | 4h | P1 | muito teste novo; gaps contract_intel/buyer_intel |

### 1.4 Legado TD-* cosmético / baixo (não re-listados na arch v3 — audit trail)

| ID | Débito | Severidade | Status | Notas |
|----|--------|------------|--------|-------|
| TD-005 | Subprocess sem output estruturado | LOW | **STILL OPEN** | cosmético |
| TD-006 | ANSI manual com `rich` disponível | LOW | **STILL OPEN** | cosmético |
| TD-007 | `import json` inline | LOW | **STILL OPEN** | cosmético |
| TD-008 | Constantes espalhadas vs settings | MEDIUM | **STILL OPEN** | config drift |
| TD-009 | supabase_client inline | MEDIUM | **STILL OPEN** | PEP 8 / perf |
| TD-012 | Fallback silencioso rapidfuzz→difflib | LOW | **STILL OPEN** | degradação silenciosa |
| TD-013 | Schema validation ausente em YAML | MEDIUM | **STILL OPEN** | |
| TD-014 | Sem renovação automática de API keys | MEDIUM | **STILL OPEN** | |
| TD-019 | Import quebrado lib.cli_validation | HIGH | **RESOLVED** | Story 1.1 |
| TD-021 | PNCP BASE_URL divergente | HIGH | **RESOLVED** | Story 1.1 |
| TD-022 | Fallback DSN hardcoded em CLIs | MEDIUM | **STILL OPEN** | residual SEC |
| TD-023 | Mides BigQuery PULADO sem aviso | LOW | **STILL OPEN** | → SYS-010 |
| TD-024 | Migrations silenciosas em test DB | MEDIUM | **STILL OPEN** | → TQ-01 |

### Contagem Sistema (ativo + audit)

| Classe | Qtd |
|--------|-----|
| RESOLVED (TD-027, TD-028, TD-019, TD-021 + import-break de TD-001) | **5** resoluções rastreáveis |
| P0 NEW (SYS-001…006) | **6** |
| NEW HIGH/MED/LOW (SYS-007…015) | **9** |
| STILL OPEN legado TD (excluindo RESOLVED) | **~22** (incl. cosméticos) |
| PARTIAL | **2** (TD-015, TD-030) |

---

## 2. Débitos de Database

Fonte: `supabase/docs/DB-AUDIT.md` v3.0  
⚠️ **PENDENTE:** Revisão do @data-engineer (Dara)

### 2.1 RESOLVED desde v2 (audit trail)

| ID | Débito | Severidade orig. | Status | Esforço residual | Evidência |
|----|--------|------------------|--------|------------------|-----------|
| **DT-01** | Colunas match_logging ausentes em bids | HIGH | **RESOLVED** | — | dump + mig |
| **DT-02** | 10 tabelas v3 não aplicadas | HIGH | **RESOLVED** | — | dump contém opportunity_*, hierarchy, etc. |
| **DT-04** | upsert_pncp_raw_bids row-by-row | MEDIUM | **RESOLVED** | — | set-based CTE |
| **DT-05** | upsert contracts row-by-row | MEDIUM/HIGH | **RESOLVED** | — | set-based + 044/050 |
| **DT-06** | Sem UNIQUE `cnpj_8` | MEDIUM | **RESOLVED** | — | `uq_spe_cnpj_8` |
| **DT-07** | Senha hardcoded settings | MEDIUM | **RESOLVED*** | histórico git | default sem senha + env |
| **DT-08** | Sem CHECK esfera_id | LOW | **RESOLVED** | — | chk no dump |
| **DT-11** | ILIKE sem trigram | LOW | **RESOLVED** | — | GIN partial active |
| **DT-16** | GIN contracts ausente v2 | MEDIUM | **RESOLVED** | — | presente |
| **DT-17** | match cols 005-v2 vs schema | HIGH | **RESOLVED** | — | = DT-01 |
| **DT-18** | Soft-delete contracts | LOW | **RESOLVED** | — | `is_active` |
| **DT-19** | FK órgão em bids | MEDIUM | **RESOLVED*** | VALIDATE residual | 041a |

### 2.2 ACCEPTED / PARTIAL (legado)

| ID | Débito | Severidade | Status | Esforço | Prioridade | Evidência |
|----|--------|------------|--------|---------|------------|-----------|
| **DT-03** | Ordem 003-v2 depende de 005-v2 | MEDIUM | **ACCEPTED** | 1h | P3 | track `db/` canônico; supabase residual |
| **DT-14** | Sem reconciliação periódica coverage | MEDIUM | **PARTIAL** | 3h | P1 | fns 1.4/1.5 existem; cron não auditado |
| **DT-20** | FK contracts → entities | MEDIUM | **ACCEPTED** | — | — | criado 034/041a; **removido 050** (pilot nacional) |
| **DT-22** | Política de retenção | MEDIUM | **PARTIAL** | 3h | P2 | `fn_purge_old_data` existe; cron não verificado |

### 2.3 OPEN legado

| ID | Débito | Severidade | Status | Esforço | Prioridade | Evidência |
|----|--------|------------|--------|---------|------------|-----------|
| **DT-09** | Sem CHECK `source` | LOW | **OPEN** | 2h | P2 | TEXT livre |
| **DT-10** | Sem CHECK status `ingestion_runs` | LOW | **OPEN** | 0.5h | P2 | |
| **DT-12** | DATE vs TIMESTAMPTZ inconsistente | LOW | **OPEN** | 2h | P2 | bids DATE; opportunity TIMESTAMPTZ |
| **DT-13** | `ingestion_checkpoints` sem uso | LOW | **OPEN** | 2h | P3 | supersedido em parte por watermarks 046 |
| **DT-15** | content_hash UNIQUE sem partial `is_active` | LOW | **OPEN** | 1h | P2 | soft-delete reinsert |

### 2.4 NEW (2026-07-17) — DT-23…33

| ID | Débito | Severidade | Status | Esforço | Prioridade | Evidência |
|----|--------|------------|--------|---------|------------|-----------|
| **DT-23** | Dual migration track (`db/` vs `supabase/`) sem política única | **HIGH** | **NEW OPEN** | 4h | **P0** | dois apply paths |
| **DT-24** | `db/current-schema.sql` desatualizado (falta 043–054) | **HIGH** | **NEW OPEN** | 1h | **P0** | dump vs HEAD |
| **DT-25** | Live DB offline / sem smoke schema em CI local | MEDIUM | **NEW OPEN** | 2h | P1 | compose + diagnostics |
| **DT-26** | CHECK constraints NOT VALID | MEDIUM | **NEW OPEN** | 2h | P1 | VALIDATE em janela |
| **DT-27** | FKs contracts dropadas (050) sem view de orfandade | MEDIUM | **NEW OPEN** | 3h | P1 | métrica % órfãos |
| **DT-28** | `diagnostics.py` EXPECTED_* incompleto vs 052–054 | MEDIUM | **NEW OPEN** | 2h | P1 | |
| **DT-29** | `audit_sql_references.KNOWN_*` defasado | MEDIUM | **NEW OPEN** | 2h | P1 | official_acts, dlq, etc. |
| **DT-30** | Enum `evidence_state` legados + novos (duplicidade semântica) | LOW | **NEW OPEN** | 3h | P2 | |
| **DT-31** | pgvector instalado sem uso garantido de embedding | LOW | **NEW OPEN** | 2h | P2 | |
| **DT-32** | Rollback unificado 043–054 ausente | MEDIUM | **NEW OPEN** | 4h | P2 | |
| **DT-33** | Aplicação 043–054 no local **não verificada** | **HIGH** | **NEW OPEN** | 1h | **P0** | `_migrations` ORDER BY version |

### Contagem Database

| Classe | IDs | N |
|--------|-----|---|
| **RESOLVED** | DT-01,02,04,05,06,07*,08,11,16,17,18,19* | **12** |
| **ACCEPTED** | DT-03, DT-20 | **2** |
| **PARTIAL** | DT-14, DT-22 | **2** |
| **OPEN legado** | DT-09,10,12,13,15 | **5** |
| **NEW OPEN** | DT-23…33 | **11** |
| **OPEN-ish total** (OPEN + NEW + PARTIAL) | | **18** |
| **Inventário total DT (histórico)** | DT-01…33 (sem DT-21) | **32 IDs** |

---

## 3. Débitos de Frontend/UX

Fonte: `docs/frontend/frontend-spec.md` v3.0  
⚠️ **PENDENTE:** Revisão do @ux-design-expert (Uma)

> Nota de continuidade: assessment v2 elevou UX-02 a CRITICAL e UX-04 a HIGH. Spec v3 mantém UX-02 **HIGH** e UX-04 **MEDIUM**. Este draft **adota severidades da spec v3** (fonte Phase 3 refresh); Uma pode re-elevar.

| ID | Débito | Severidade | Status | Esforço | Prioridade | Evidência |
|----|--------|------------|--------|---------|------------|-----------|
| **UX-01** | Web UI interativa (FastAPI+HTMX / portal) | HIGH | **DEFERRED** | 80h+ | P3 pós-VPS | inexistente; fora do caminho pré-VPS |
| **UX-02** | Sem progress indicators em comandos longos | HIGH | **OPEN** | 8h | **P0 ops** | update, radar, crawls, PDF |
| **UX-03** | Dual display: `rich` vs raw `print` | MEDIUM | **PARTIAL** | 12h | P1 | rich em datalake/golden_path; workspace/opp_intel ASCII |
| **UX-04** | Truncamento agressivo opportunity_intel (20c/10 cols) | MEDIUM | **OPEN** | 4h | P1 | workspace cap 48c melhor; opp_intel inalterado |
| **UX-05** | Exit codes inconsistentes | LOW | **PARTIAL** | 2h | P2 | golden_path 0–5 / ops 0/1/2; opp_intel 0/1 |
| **UX-06** | Flags output inconsistentes (`--format` vs `--json`) | LOW | **OPEN** | 2h | P2 | |
| **UX-07** | Sem paginação interativa | LOW | **OPEN** | 6h | P3 | limits fixos |
| **UX-08** | Erros silenciosos / pouca mensagem | MEDIUM | **PARTIAL** | 3h | P1 | workspace/opp_intel melhoraram; legado permanece |
| **UX-09** | Coverage duplicado (opp_intel vs datalake vs contract) | MEDIUM | **PARTIAL** | 6h | P2 | `coverage_contract_cli` + workspace |
| **UX-10** | Monólito `generate-report-b2g.py` (~7.4k LOC) | MEDIUM | **OPEN** | 16h | P2 | executive_report modular ajuda |
| **UX-11** | URLs não clicáveis no terminal | LOW | **OPEN** | 2h | P3 | |
| **UX-12** | Validação de input pouco amigável | LOW | **OPEN** | 4h | P3 | erro SQL vs “UF inválida” |
| **UX-13** | A11y incompleta em charts HTML executivos | LOW | **NEW** | 3h | P3 | charts OK; WCAG não auditado |
| **UX-14** | Confusão cobertura vs sinal comercial | HIGH | **PARTIAL** | 3h | **P0 ops** | guide documenta; CLI sem separação visual forte |
| **UX-15** | Fragmentação de CLIs (muitos entry points) | MEDIUM | **PARTIAL** | 8h | P1 | facade `workspace` + guide; legados necessários |
| **UX-16** | Mistura PT/EN em mensagens CLI | LOW | **NEW** | 4h | P3 | legibilidade do consultor |
| **UX-17** | Ops health JSON-only (sem vista humana rich) | MEDIUM | **NEW** | 2h | **P0 ops** | máquina OK; operador quer summary ASCII |
| **UX-18** | HTML comercial sem TOC sticky / multi-página | LOW | **NEW** | 3h | P3 | aceitável sessão única |

### Contagem Frontend/UX

| Status | Qtd |
|--------|-----|
| OPEN | **6** |
| PARTIAL | **6** |
| NEW (subset of above) | **4** (UX-13,16,17,18) |
| DEFERRED | **1** (UX-01) |
| RESOLVED total | **0** (nenhum UX-xx 100% fechado) |
| **Total IDs** | **18** |

---

## 4. Segurança (categoria própria — gap do QA v2)

Fonte: assessment v2 §4 + arch v3 §13 + Story 1.1 + verificação 2026-07-17  
**Justificativa:** QA v2 (GAP-001) exigiu visão consolidada. Mantida como categoria.

| ID | Débito | Severidade | Status | Esforço | Prioridade | Origem / Evidência |
|----|--------|------------|--------|---------|------------|-------------------|
| **SEC-01** | SQL f-strings (injection teórico) | HIGH | **PARTIAL** | 2h residual | P1 | Story 1.1 fixou caso principal; TD-016 residual |
| **SEC-02** | Service account JSON no repo | HIGH | **STILL OPEN** ⚠ | 1h | **P0** | Story 1.1 marcou Done; **arquivo ainda em `config/`** |
| **SEC-03** | Senha hardcoded settings | HIGH | **RESOLVED*** | residual git | — | env-only default; histórico pode conter secret |
| **SEC-04** | Dependências sem auditoria CVE | MEDIUM | **PARTIAL** | 2h | P1 | **pip-audit + bandit no CI** (melhoria forte vs v2) |
| **SEC-05** | Estratégia de secrets management | MEDIUM | **OPEN** | 3h | P2 | vault / segregação / rotação formal |
| **SEC-06** | Ausência de threat modeling | MEDIUM | **OPEN** | 4h | P2 | single-user SSH adequado à fase; formalizar |
| **SEC-07** | Superfície multi-tenant / RLS ausente | LOW | **ACCEPTED** (fase) | — | P3 | 0 RLS; OK single-operator; reabrir se multi-user |
| **SEC-08** | Headers sensíveis em raw crawl | MEDIUM | **MITIGATED** | — | — | resilience strip + ADR-020 |

### Contagem Segurança

| Status | Qtd |
|--------|-----|
| RESOLVED / MITIGATED | **2** (SEC-03*, SEC-08) |
| PARTIAL | **2** (SEC-01, SEC-04) |
| STILL OPEN | **1** (SEC-02) ⚠ |
| OPEN | **2** (SEC-05, SEC-06) |
| ACCEPTED fase | **1** (SEC-07) |
| **Total IDs** | **8** |

---

## 5. Testes / QA (categoria própria)

Fonte: assessment v2 §5 + arch v3 (CI, coverage, chaos) + DB-AUDIT diagnostics

| ID | Débito | Severidade | Status | Esforço | Prioridade | Origem / Evidência |
|----|--------|------------|--------|---------|------------|-------------------|
| **TQ-01** | Migrations falham silenciosamente em test DB | MEDIUM | **OPEN** | 3h | P1 | TD-024 / conftest_db |
| **TQ-02** | Coverage mínima frouxa (10% vs alvo ≥60%) | MEDIUM | **OPEN** | 2h | **P0 pré-VPS** | TD-026; gate existe mas fraco |
| **TQ-03** | Módulos críticos sem testes adequados | MEDIUM | **PARTIAL** | 4h | P1 | TD-030; schema/coverage melhoraram; contract/buyer gaps |
| **TQ-04** | Suite integração crawlers (blocker histórico de TD-010) | HIGH | **PARTIAL** | 6h residual | P1 | resilience + chaos existem; cobertura crawler legado incompleta |
| **TQ-05** | Métricas de qualidade dos testes (assert quality, unit vs int ratio) | MEDIUM | **OPEN** | 4h | P2 | QA GAP-002 |
| **TQ-06** | Schema diagnostics / EXPECTED_* defasados vs 052–054 | MEDIUM | **NEW OPEN** | 2h | P1 | = DT-28 (cross-ref) |
| **TQ-07** | Live canary / truth gate não bloqueia claim VPS | HIGH | **NEW OPEN** | 4h | **P0 pré-VPS** | pre-vps-final-gate vs dual runtime |

### Contagem Testes/QA

| Status | Qtd |
|--------|-----|
| OPEN / NEW OPEN | **5** |
| PARTIAL | **2** |
| **Total IDs** | **7** |

---

## 6. Observabilidade / Performance

| ID | Débito | Severidade | Status | Esforço | Prioridade | Evidência |
|----|--------|------------|--------|---------|------------|-----------|
| **OBS-01** | Health unificado sem mode/environment/fixture flag | HIGH | **OPEN** | 4h | **P0** | SYS-003 + TD-015 |
| **OBS-02** | SLA freshness não lido do registry | HIGH | **OPEN** | 3h | **P0** | SYS-004 |
| **OBS-03** | Métricas M1/M2 confundíveis em ops diária | HIGH | **PARTIAL** | 3h | P1 | UX-14 + coverage contract docs |
| **OBS-04** | Sem reconciliação periódica coverage/evidence (job) | MEDIUM | **PARTIAL** | 3h | P1 | DT-14 |
| **OBS-05** | Upserts set-based resolvidos; volume live N/A (DB offline) | MEDIUM | **MITIGATED** (código) | — | — | DT-04/05 RESOLVED; perf live não medida |
| **OBS-06** | Checkpoint / DLQ observabilidade incompleta | MEDIUM | **OPEN** | 4h | P1 | SYS-005/006 + migrations 043+ |
| **OBS-07** | Logging estruturado inconsistente (subprocess ANSI) | LOW | **OPEN** | 2h | P3 | TD-005/006 |

### Contagem Observabilidade/Perf

| Status | Qtd |
|--------|-----|
| OPEN | **4** |
| PARTIAL / MITIGATED | **3** |
| **Total IDs** | **7** |

---

## 7. Dependências externas

| ID | Débito | Severidade | Status | Esforço | Prioridade | Evidência |
|----|--------|------------|--------|---------|------------|-----------|
| **DEP-01** | MIDES BigQuery sem conta / SA | LOW | **OPEN** | — | P3 | SYS-010 + TD-023 |
| **DEP-02** | TCE-SC e-Sfinge requer ICP-Brasil | MEDIUM | **BLOCKED** | — | P3 | SYS-011 |
| **DEP-03** | DOM-SC / CIGA API key contratual | MEDIUM | **OPEN** | comercial | P2 | SYS-012 |
| **DEP-04** | Provedor VPS/cloud TBD | MEDIUM | **OPEN** | 2h decisão | P2 | SYS-009 / ADR-007 |
| **DEP-05** | PNCP API v3 estabilidade / rate limits | MEDIUM | **OPEN** | contínuo | P2 | dual client paths |
| **DEP-06** | OpenAI quota / modelo para classificação | LOW | **OPEN** | — | P3 | env-driven |
| **DEP-07** | CVE continuous audit (processo) | MEDIUM | **PARTIAL** | 2h | P1 | SEC-04; pip-audit strict no CI |

### Contagem Dependências

| Status | Qtd |
|--------|-----|
| OPEN / BLOCKED | **6** |
| PARTIAL | **1** |
| **Total IDs** | **7** |

---

## 8. Documentação / Ambientes

| ID | Débito | Severidade | Status | Esforço | Prioridade | Evidência |
|----|--------|------------|--------|---------|------------|-----------|
| **DOC-01** | Dual track migrations docs (`db/` vs `supabase/`) | HIGH | **OPEN** | 4h | **P0** | DT-23 |
| **DOC-02** | `current-schema.sql` desatualizado | HIGH | **OPEN** | 1h | **P0** | DT-24 |
| **DOC-03** | Preset AIOX nextjs ≠ stack Python | LOW | **OPEN** | 1h | P3 | SYS-014 |
| **DOC-04** | Operational data / fixtures no git | MEDIUM | **OPEN** | 2h | P1 | SYS-015 / ADR-020 |
| **DOC-05** | Workspace-guide vs CLIs legados (múltiplas “fontes da verdade” UX) | MEDIUM | **PARTIAL** | 3h | P1 | UX-15 |
| **ENV-01** | Ambiente local DB apply 043–054 não verificado | HIGH | **OPEN** | 1h | **P0** | DT-33 |
| **ENV-02** | VPS não provisionada; dual units prontos no repo | HIGH | **OPEN** | 16h+ | **P0 pré-VPS** | SYS-002 + deploy/systemd |
| **ENV-03** | Test DB / REQUIRE_TEST_DB não universal no CI local | MEDIUM | **OPEN** | 2h | P1 | DT-25 / TQ |
| **ENV-04** | Secrets em histórico git (pós-BFG residual) | MEDIUM | **PARTIAL** | 2h | P1 | SEC-03 residual |

### Contagem Documentação/Ambientes

| Status | Qtd |
|--------|-----|
| OPEN | **7** |
| PARTIAL | **2** |
| **Total IDs** | **9** |

---

## 9. Matriz Preliminar consolidada

> Inclui débitos **ativos** (OPEN / PARTIAL / NEW / STILL OPEN / DEFERRED). RESOLVED listados na §Changelog e seções de audit trail — **não** somam como backlog ativo.

### 9.1 🔴 Pre-VPS blockers (ordem obrigatória)

| ID | Débito | Área | Impacto | Esforço | Prioridade | Status |
|----|--------|------|---------|---------|------------|--------|
| **SYS-001** | Resilient cycle não grava PostgreSQL (split-brain FS/DB) | Sistema | Falso verde em VPS | 12h | **P0** | NEW OPEN |
| **SYS-002** | Dual systemd runtimes | Sistema / Env | Duas verdades de coleta | 8h | **P0** | NEW OPEN |
| **SYS-003** | Health healthy com fixtures | Sistema / Obs | Gate de verdade quebrado | 4h | **P0** | NEW OPEN |
| **SYS-004** | SLA freshness ≠ registry | Sistema / Obs | Alertas errados | 3h | **P0** | NEW OPEN |
| **SYS-005** | Checkpoint schema engolido | Sistema | Estado mentiroso | 3h | **P0** | NEW OPEN |
| **SYS-006** | CIGA success no adapter | Sistema | Success prematuro | 3h | **P0** | NEW OPEN |
| **SEC-02 / TD-029** | SA JSON no tree | Segurança | Credencial versionada | 1h | **P0** | STILL OPEN ⚠ |
| **TQ-02 / TD-026** | Coverage strict 0% rigor (threshold 10%) | Testes | Qualidade fraca no gate | 2h | **P0** | OPEN |
| **DT-23** | Dual migration track | Database | Apply errado em prod | 4h | **P0** | NEW OPEN |
| **DT-24 / DT-33** | Schema dump + apply local não verificados | Database / Env | Drift silencioso | 2h | **P0** | NEW OPEN |
| **TQ-07** | Truth gate não bloqueia claim VPS | Testes | LOCAL_RESILIENCE_READY mal interpretado | 4h | **P0** | NEW OPEN |
| **UX-02** | Progress em comandos longos | UX | Abort prematuro | 8h | **P0 ops** | OPEN |
| **UX-14** | Cobertura vs sinal comercial | UX | Decisão comercial errada | 3h | **P0 ops** | PARTIAL |
| **UX-17** | Health humano ASCII | UX / Ops | Operador cego no JSON | 2h | **P0 ops** | NEW |

### 9.2 P1 — Curto prazo (amostra prioritária)

| ID | Débito | Área | Impacto | Esforço | Prioridade | Status |
|----|--------|------|---------|---------|------------|--------|
| SYS-007 | SC Compras bulk sem snapshot | Sistema | Irreprodutibilidade | 4h | P1 | NEW |
| SYS-008 | M2 = 0/1093 | Sistema | Meta produto | 40h+ | P1 | NEW |
| SYS-015 | Ops data no git | Sistema | Leak / noise | 2h | P1 | OPEN |
| TD-010 | monitor.py god-module | Sistema | Manutenção | 20h | P1 | OPEN |
| TD-011 / TD-001 | Dual PNCP paths | Sistema | Divergência | 6–12h | P1 | OPEN |
| TD-016 / SEC-01 | SQL residual | Seg | Injection residual | 2h | P1 | PARTIAL |
| SEC-04 | CVE process continuous | Seg | Vulnerabilidades | 2h | P1 | PARTIAL |
| DT-25…29 | Diagnostics / orphans / NOT VALID | DB | Integridade | 11h | P1 | NEW |
| DT-14 | Coverage reconciliation job | DB | Drift entity_coverage | 3h | P1 | PARTIAL |
| TQ-01,03,04,06 | Test gaps | QA | Regressão | ~15h | P1 | OPEN/PARTIAL |
| UX-03,04,08,15 | CLI consistency | UX | Produtividade | ~27h | P1 | OPEN/PARTIAL |
| OBS-01…04,06 | Health/SLA/jobs | Obs | Ops cego | ~17h | P1 | OPEN/PARTIAL |
| DOC-04, ENV-03 | Env/docs | Docs | Setup | 4h | P1 | OPEN |

### 9.3 P2–P3 (resumo quantitativo)

| Prioridade | Exemplos de IDs | Qtd aprox. ativa |
|------------|-----------------|------------------|
| **P2** | TD-002…004,017,018,025; DT-09,10,12,15,22,26,32; UX-05,06,09,10; SEC-05,06; SYS-009,012,013; DEP-03…05 | **~35** |
| **P3** | TD cosméticos 005–007,012,020; DT-13,30,31; UX-01,07,11–13,16,18; SYS-010,011,014; DEP-01,02,06; DOC-03 | **~25** |

### 9.4 Contagem consolidada por severidade (ativo)

Definição **ativo** = OPEN + NEW OPEN + STILL OPEN + PARTIAL + DEFERRED + BLOCKED + ACCEPTED residual que ainda exige disciplina.  
**Não inclui** RESOLVED/MITIGATED puros.

| Severidade | Sistema (TD/SYS) | Database | Frontend/UX | Segurança | Testes | Obs/Perf | Deps | Docs/Env | **Total** |
|------------|------------------|----------|-------------|-----------|--------|----------|------|----------|-----------|
| **CRITICAL / P0** | 6 (SYS-001…006) | 0* | 0** | 1 (SEC-02) | 2 (TQ-02,07) | 2 (OBS-01,02) | 0 | 3 (DOC-01,02, ENV-01/02) | **~14 P0-class** |
| **HIGH** | ~8 | 3 (DT-23,24,33) | 3 (UX-01,02,14) | 0 abertos HIGH além SEC-02 | 1 (TQ-04 PARTIAL) | 1 (OBS-03) | 0 | 1 (ENV-02 se não contado) | **~17** |
| **MEDIUM** | ~18 | ~12 | 7 | 4 | 4 | 3 | 4 | 3 | **~55** |
| **LOW** | ~10 | 7 | 8 | 1 | 0 | 1 | 3 | 1 | **~31** |
| **RESOLVED (audit)** | 5+ | 12 | 0 | 2 | 0 | 1 | 0 | 0 | **~20** |

\* DT-23/24/33 são HIGH com **prioridade P0**.  
\** UX-02/14/17 tratados como **P0 ops** com severidade HIGH/MEDIUM na fonte.

### 9.5 Totais de inventário (IDs únicos rastreados neste draft)

| Categoria | IDs rastreados | Ativos (aprox.) | Resolvidos / mitigados (audit) |
|-----------|----------------|-----------------|--------------------------------|
| Sistema TD/SYS | ~45 | ~40 | ~5 |
| Database DT | 32 | 18 open-ish + 2 accepted | 12 |
| Frontend UX | 18 | 18 | 0 |
| Segurança SEC | 8 | 5 | 2 + 1 accepted |
| Testes TQ | 7 | 7 | 0 |
| Obs/Perf OBS | 7 | 6 | 1 |
| Dependências DEP | 7 | 7 | 0 |
| Docs/Env DOC+ENV | 9 | 9 | 0 |
| **Total bruto IDs** | **~133** | **~110 ativos/tracked** | **~20 resolved** |

> Comparativo v2 FINAL: **79 débitos**. v3 expande inventário (SYS/DT-new/UX-new/OBS/DEP/DOC) e marca resoluções sem apagar histórico.  
> **Backlog acionável pré-VPS (P0):** **~14 itens**.  
> **Esforço P0 estimado:** ~**55–65h** (sem SYS-008 elevação M2).  
> **Esforço total ativo (sem UX-01 web, sem M2 40h+):** ordem de grandeza **~280–350h**.

---

## 10. Ordem de resolução proposta (pre-VPS first)

### Onda 0 — Truth & secrets (antes de qualquer timer novo)

1. **SEC-02 / TD-029** — Remover SA JSON do tree + `.gitignore` + rotacionar se exposto (**1h**)  
2. **SYS-005 / SYS-006** — Checkpoint tipado fail-closed; adapter não marca success (**6h**)  
3. **SYS-003 / SYS-004 / OBS-01 / OBS-02** — Health com `mode`/`environment`/fixture flag; SLA do registry (**7h**)  
4. **SYS-001 / SYS-002** — **Um runtime oficial**: resilient contract **com** projeção PostgreSQL **ou** monitor consumindo `FetchResult` end-to-end; desligar dualidade de units (**20h**)  
5. **DT-33 / DT-24 / DOC-01 / DT-23** — Apply/verify migrations até 054; regenerar dump+SHA; política única `db/setup_db.sh` (**6h**)  
6. **TQ-02 / TQ-07** — Subir rigor de coverage (ex. 30% → 60% gradual) + truth gate no Makefile/CI (**6h**)

**Saída da Onda 0:** claim “pode habilitar timers oficiais” só com evidência de **uma** verdade de persistência + health honesto + schema HEAD verificado.

### Onda 1 — Ops diário do consultor (paralelo parcial)

7. **UX-02** — `rich.progress` em update/radar/crawls/PDF (**8h**)  
8. **UX-17** — `ops/health --human` (**2h**)  
9. **UX-14** — Labels “sinal comercial” vs “cobertura operacional” no workspace (**3h**)  
10. **UX-04** — Colunas prioritárias sem truncar id/ranking/órgão (**4h**)  
11. **SEC-01 residual / TD-016** — Grep final f-strings SQL (**2h**)  
12. **DT-28 / DT-29 / TQ-06** — diagnostics + KNOWN_* vs 052–054 (**4h**)

### Onda 2 — Unificação de runtime e qualidade

13. **TD-010 / TD-011 / TD-001** — Fatiar monitor + unificar PNCP **após** SYS-001 (**26h+**)  
14. **TQ-04 residual + TQ-03** — Integração crawlers + gaps buyer/contract (**10h**)  
15. **SYS-007** — Snapshot hash SC Compras bulk (**4h**)  
16. **DT-14 / OBS-04** — Job periódico reconciliação coverage (**3h**)  
17. **DT-25…27** — Smoke CI + VALIDATE + orfandade contracts (**7h**)

### Onda 3 — Produto (só com Onda 0 fechada)

18. **SYS-008** — Elevar M2 com evidence real (meta 95% = alvo, não claim) (**40h+**)  
19. **UX-03 + UX-15** — Workspace facade + rich tables compartilhadas (**12h**)  
20. **UX-09 / UX-10** — Coverage entry único + modularizar PDF B2G (**22h**)  
21. **SEC-05 / SEC-06** — Secrets strategy + threat model leve (**7h**)

### Onda 4 — Estratégico / backlog

22. **UX-01** Web UI — **somente** após VPS estável + fluxo CLI diário (**80h+**)  
23. **TD-025** ORM — só se multi-app ou web (**20h+**)  
24. **DEP-01…03 / SYS-010…012** — Fontes externas sob contrato/orçamento  
25. Cosméticos TD/UX LOW

### Dependências cruzadas (grupos)

```
Grupo Pre-VPS Truth:
  SYS-005/006 → SYS-003/004 → SYS-001/002 → TQ-07 → ENV-02 (timers)

Grupo Schema:
  DT-33 → DT-24 → DT-23/DOC-01 → DT-28/29 → DT-25

Grupo Segurança:
  SEC-02 → SEC-05 → SEC-06
  SEC-01 residual ∥ SEC-04 continuous

Grupo Runtime unificado:
  SYS-001/002 → TD-010 → TD-011/TD-001 → SYS-008

Grupo UX ops:
  UX-02 ∥ UX-17 ∥ UX-14 → UX-04 → UX-03/15 → UX-01 (último)
```

---

## 11. Perguntas para Especialistas

### @data-engineer (Dara)

1. **DT-33:** Ao subir o DB local, `_migrations` chega a **054**? Há gap entre dump 07-14 e HEAD 043–054?
2. **DT-23:** Confirma política canônica: **somente** `db/setup_db.sh` / `db/migrations` — `supabase/apply-migrations.sh` deprecated?
3. **DT-24:** Quem regenera `db/current-schema.sql` + SHA no DoD de migrations?
4. **DT-20 ACCEPTED:** Orfandade de contracts pós-drop FK 050 — aceitável em pilot nacional? Precisamos da view DT-27 antes de VPS?
5. **DT-14 PARTIAL:** Existe timer/systemd de reconciliação coverage/evidence em produção planejada, ou só funções manuais?
6. **DT-26:** Quais CHECKs estão NOT VALID e qual janela segura para `VALIDATE CONSTRAINT`?
7. **DT-07 residual:** Histórico git ainda contém `smartlic_local`? BFG foi suficiente ou re-scan necessário?
8. **SYS-001 (projeção DB):** Preferência de desenho — (A) resilient_cycle grava Postgres via loader canônico, (B) monitor consome FetchResult e permanece único writer, (C) dual-write temporário com checksum?

### @ux-design-expert (Uma)

1. **UX-02 severidade:** Manter HIGH (spec v3) ou re-elevar a CRITICAL (assessment v2)?
2. **UX-14:** Padrão visual mínimo no workspace para separar M1 (sinal) vs M2 (operacional) — cores, badges, colunas obrigatórias?
3. **UX-17:** Formato de `--human` para ops/health — painel `rich` ou ASCII tabela fixa (compatível com SSH sem TTY rico)?
4. **UX-03/15:** Workspace como **única** facade documentada — CLIs legados ficam “power user only” ou deprecados com prazo?
5. **UX-04:** Lista de colunas nunca truncáveis (`id`, `ranking`, `orgao_nome`, …)?
6. **UX-01:** Confirma DEFERRED pós-VPS (sem spike SPA no caminho crítico)?
7. **UX-16:** Política de idioma — PT-BR para mensagens user-facing; EN só em códigos/IDs?

### @qa (Quinn)

1. **TQ-02:** Threshold progressivo recomendado (10% → 30% → 60%) e o que entra no denominator (só `scripts/` vs tudo)?
2. **TQ-07:** O gate `make pre-vps-final-gate-offline` deve **falhar** se SYS-001/002 abertos, ou apenas warn?
3. **SEC-02:** Story 1.1 Done vs arquivo presente — reabrir story, hotfix FAST, ou nova story HIGH-RISK?
4. **TQ-04:** Cobertura mínima de integração por fonte (PNCP, CIGA, SC Compras) antes de autorizar refactor TD-010?
5. **Falsos verdes:** checklist adversarial permanente (F1–F7) vira gate de release ou só doc?
6. **Cross-check Reversa:** após fechar SYS-001/002, re-extrair `_reversa_sdd` de crawl/resilience?

### @devops (Gage) — informativo (não bloqueia este draft)

1. Timers `extra-crawl-*` vs legados — freeze de enable em host até Onda 0?
2. Secrets store na VPS (env file vs systemd credentials vs vault)?
3. Pipeline CI: job condicional com Postgres service para DT-25?

---

## 12. Resumo Executivo Preliminar

### O que mudou de verdade desde v2

- Plataforma B2G operacional nasceu (ESR, coverage contract, workspace, resilience local, 59 migrations, CI real).  
- Matching unificado e schema v3 no dump fecharam vários P0 de dados/matching.  
- **Novos P0 de honestidade pré-VPS** (split-brain FS/DB, dual systemd, health fixture, SLA, checkpoint) **substituem** os P0 antigos de “sem CI / sem v3 tables” como bloqueio principal.  
- M2 **0%** é progresso de honestidade, não regressão de métrica inventada.

### Top 5 recomendações (Architect)

1. **Fechar SYS-001/002** — sem um writer oficial, VPS multiplica falso verde.  
2. **Fechar SYS-003…006** — health e checkpoint mentem → gates mentem.  
3. **Remover SEC-02 (SA JSON)** — regressão visível vs Story 1.1 Done.  
4. **Política única de migrations (DT-23/24/33)** — dump e HEAD alinhados.  
5. **Só então** atacar SYS-008 (M2) e TD-010 (fatiar monitor).

### Riscos principais

| Risco | Impacto | Mitigação |
|-------|---------|-----------|
| Habilitar timers resilientes na VPS com split-brain | Dados “verdes” fora do Postgres | Bloquear ENV-02 até SYS-001/002 |
| Interpretar LOCAL_RESILIENCE_READY como cobertura 95% | Decisão comercial errada | UX-14 + contract M1≠M2 |
| SA JSON no git | Comprometimento GCP | SEC-02 imediato + rotação |
| Refactor monitor sem integração | Quebra crawl produção | TQ-04 antes de TD-010 |
| Dual migration apply | Schema fantasma | DT-23 política + DT-33 verify |

---

## 13. Próximos passos do Brownfield

| Fase | Agente | Artefato |
|------|--------|----------|
| **5** | @data-engineer | `db-specialist-review.md` sobre este DRAFT (DT-*) |
| **6** | @ux-design-expert | `ux-specialist-review.md` (UX-*) |
| **7** | @qa | `qa-review.md` + gate APPROVED / NEEDS WORK |
| **8** | @architect | `technical-debt-assessment.md` v3 FINAL |
| **9** | @analyst | relatório executivo |
| **10** | @pm / @sm | epics + stories (pre-VPS wave primeiro) |

---

*Documento gerado por Aria (Visionary Architect) em 2026-07-17.*  
*Fontes: system-architecture.md v3.0 · DB-AUDIT.md v3.0 · frontend-spec.md v3.0 · technical-debt-assessment.md v2 · PRE-VPS adversarial audit · Stories 1.1–1.5.*  
*Baseline v2: 79 débitos. Inventário v3 expandido com SYS/DT-new/UX-new + categorias SEC/TQ/OBS/DEP/DOC; ~20 resoluções em audit trail.*  
*Próxima etapa: revisão @data-engineer → @ux-design-expert → @qa.*
