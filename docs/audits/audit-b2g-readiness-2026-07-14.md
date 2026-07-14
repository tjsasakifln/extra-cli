# Auditoria Técnica — B2G Readiness para CONFENGE

**Data:** 2026-07-14
**Executor:** Claude Opus 4.8 (DeepSeek v4 Pro)
**Escopo:** Infraestrutura de inteligência B2G — coleta, backfill, sinais comerciais, operação em VPS Hetzner
**Método:** Leitura integral de CLAUDE.md, PRD, EPIC-MASTER, _reversa_sdd, 64+ stories, código fonte, scripts deploy, systemd units, migrations, testes

---

## 1. Sumário Executivo

O repositório contém **137K+ LOC Python**, **41 migrations PostgreSQL**, **20 systemd timer pairs**, **14 crawlers**, **2 pipelines analíticos** (legado Intel Pipeline + QW-01 Radar), e **~1.230 testes**. A documentação é extensa (590 arquivos em docs/) e o código-fonte é substancial.

**Problema central:** o gap entre o que está documentado como "Done" e o que realmente funciona em produção é significativo. Nenhum crawler opera continuamente em VPS. Nenhum backup foi testado com restore real. O banco de dados local tem divergências de schema. Múltiplos módulos reportam cobertura entre 39.4% e 265.95% — nenhum número é confiável. O PNCP está com URL desatualizada. Sete fontes estão bloqueadas (SOURCE_BLOCKED). O contexto estratégico mudou (de Extra Construtora analytics para CONFENGE commercial intelligence) mas o backlog não reflete essa transição.

**Recomendação primária:** reabrir stories marcadas como Done cujos ACs não foram verificados em ambiente real. Consolidar 60+ stories dispersas em ~25 stories executáveis, orientadas ao novo contexto CONFENGE. Estabelecer gates objetivos e verificáveis que não dependam de credenciais não obtidas.

---

## 2. Baseline de Arquitetura (O Que Realmente Existe)

### 2.1 Crawlers — Status Real

| Crawler | Arquivo | LOC | Código | Testado Unit. | Executado Escala | Produção |
|---------|---------|-----|--------|--------------|-----------------|----------|
| PNCP Adapter | `pncp_crawler_adapter.py` | 19K | ✅ | ✅ | ✅ (1.463 records) | ❌ (URL antiga) |
| PNCP ARP | `pncp_arp_crawler.py` | 17K | ✅ | ❌ | ❌ | ❌ |
| PNCP PCA | `pncp_pca_crawler.py` | 16K | ✅ | ❌ | ❌ | ❌ |
| PNCP Contracts | `contracts_crawler.py` | 29K | ✅ | ✅ | ❌ | ❌ |
| DOM-SC | `dom_sc_crawler.py` | 21K | ✅ | ❌ | ❌ (bloqueado credenciais) | ❌ |
| PCP | `pcp_crawler.py` | 22K | ✅ | ✅ | ✅ (251 records) | ❌ |
| ComprasGov | `compras_gov_crawler.py` | 22K | ✅ | ✅ | ✅ (1.508 records) | ❌ |
| TCE-SC | `tce_sc_crawler.py` | 26K | ✅ | ✅ | ⚠️ (1.318 records, lento) | ❌ |
| DOE-SC | `doe_sc_crawler.py` | 28K | ✅ | ❌ | ❌ (bloqueado credenciais) | ❌ |
| SC Compras | `sc_compras_crawler.py` | 19K | ✅ | ✅ | ❌ (portal offline) | ❌ |
| Transparência | `transparencia_crawler.py` | 57K | ✅ | ✅ | ❌ (crawl não executado) | ❌ |
| CIGA/CKAN | `ciga_ckan_crawler.py` | 34K | ✅ | ✅ | ❌ | ❌ |
| Selenium | `selenium_crawler.py` | 28K | ✅ | ✅ | ❌ | ❌ |
| MiDES/BigQuery | `mides_bigquery_crawler.py` | 22K | ✅ | ✅ | ❌ | ❌ |

**Conclusão:** 14 crawlers implementados. 0 em operação contínua. 2 testados em escala (PCP 251 records, ComprasGov 1.508 records). PNCP é o único com dados históricos mas URL base está desatualizada.

### 2.2 Database — Status Real

- **41 migrations** em `db/migrations/` (001 a 041)
- **setup_db.sh** funcional — aplica migrations em ordem + seed
- **Schema real diverge do código:** 10 tabelas referenciadas no código não existem no banco (ver FIX-SCHEMA-MISMATCH)
- **Seed:** 2.085 entidades SC carregadas via `db/seed/001_sc_entities.py`
- **Banco local:** PostgreSQL (porta 5433 ou 54399), não padronizado

### 2.3 Pipelines Analíticos

| Pipeline | Arquivos | Status | Uso |
|----------|---------|--------|-----|
| Intel Pipeline (legado) | `intel_pipeline.py` (50K) + 6 stages | Funcional | Análise de CNPJ específico |
| QW-01 Radar | `radar.py` (913 LOC) + 12 módulos | Funcional | Monitoramento de licitações abertas |
| Contract Intel | `contract_intel/cli.py` (47K) | Funcional | Contratos históricos, supplier ranking |
| Competitive Intel | `competitive_intel_validation.py` (novo) | ⚠️ Não testado | Validação competitive intelligence |

**Duplicação:** Dois pipelines analíticos coexistem sem critério claro de uso. Intel Pipeline legado (7 estágios, GPT-4.1-nano) vs QW-01 Radar (determinístico, 24 regras).

### 2.4 Deploy & Infra

| Artefato | Existe | Testado | Produção |
|----------|--------|---------|----------|
| `deploy/provision-vps.sh` | ✅ (405 linhas) | ❌ | ❌ |
| `deploy/install.sh` | ✅ (82 linhas) | ❌ | ❌ |
| 20 systemd timer pairs | ✅ | ❌ | ❌ |
| `scripts/backup-database.sh` | ✅ (>200 linhas) | ❌ | ❌ |
| `scripts/restore-database.sh` | ✅ | ❌ | ❌ |
| `scripts/health_check.py` | ✅ | ❌ | ❌ |
| `docs/ops/` (7 arquivos) | ✅ | N/A | N/A |

**Problema:** `install.sh` usa nomenclatura antiga (`pncp-*`), `provision-vps.sh` usa nomenclatura nova (`extra-*`). Dois templates OnFailure coexistem.

### 2.5 CI Gates

| Gate | Arquivo | Funcional | Integrado |
|------|---------|-----------|----------|
| Consulting Readiness | `consulting_readiness.py` (2.013 LOC) | ⚠️ (transaction bug) | ❌ |
| Freshness Gate | `freshness_gate.py` (10K) | ✅ | ❌ |
| Coverage Truth | `coverage_truth.py` (944 LOC) | ✅ | ❌ |

---

## 3. Divergências Críticas (Código vs Documentação)

### 3.1 Stories "Done" com ACs Não Atendidos

| Story | Status Documentado | Status Real | Bloqueadores |
|-------|-------------------|-------------|-------------|
| **FEAT-4.1** (Hetzner VPS) | Done | **Ready (scripts apenas)** | VPS nunca provisionada, credenciais Hetzner não obtidas |
| **TD-8.5** (Multi-source backfill) | Done | **Partial (39.4%)** | 5/7 crawlers não executaram. Meta de 85%+ não atingida. ACs rebaixados durante QA. |
| **B2G-1** (604 entidades) | Draft | Draft | Script `resolve_unresolved_entities.py` existe (16K LOC) mas nunca executado |
| **B2G-5** (Schema final) | Draft | Draft | Migrations existem mas schema real diverge |
| **TD-7.1** (Code quality) | InProgress | InProgress | Ruff 222 erros, mypy 706+ erros |

### 3.2 Inconsistências Técnicas

| ID | Descrição | Severidade | Story |
|----|-----------|-----------|-------|
| **PNCP-URL** | `adapter.py` linha 57 ainda usa `api/consulta/v1`. Deveria ser `pncp-consulta/v1`. 7 arquivos com URL antiga. | 🔴 CRITICAL | Nova |
| **SCHEMA-01** | 10 tabelas referenciadas no código não existem no banco: `coverage_evidence`, `engineering_opportunities`, `entity_hierarchy`, `opportunity_intel`, `opportunity_checkpoints`, `opportunity_runs`, `opportunity_coverage`, `pncp_enrichment_cache`, `sc_municipalities`, `sc_dados_abertos_backfill_log` | 🔴 CRITICAL | FIX-SCHEMA-MISMATCH |
| **SCHEMA-02** | Colunas referenciadas em queries não existem nas tabelas reais | 🔴 CRITICAL | FIX-SCHEMA-MISMATCH |
| **UNIVERSE-01** | 6 denominadores de universo diferentes: 1.093, 1.448, 1.481, 1.697, 2.085, 1.000 | 🔴 CRITICAL | FIX-UNIVERSE |
| **MANIFEST-01** | `manifest.py` reporta cobertura 265.95% (matematicamente impossível). `entities_with_data: 3.851` para universo de 1.448. | 🔴 CRITICAL | FIX-MANIFEST |
| **TRANSACTION-01** | Statement timeout → transação abortada → cascata de falhas sem ROLLBACK | 🔴 CRITICAL | FIX-TRANSACTION |
| **INSTALL-01** | `install.sh` usa nomes antigos (`pncp-crawl-full`), `provision-vps.sh` usa novos (`extra-crawl-pncp`). Dois padrões coexistem. | 🟠 HIGH | Nova |
| **ONFAILURE-01** | Dois templates: `onfailure@.service` (legado, 10 units) + `extra-onfailure@.service` (novo, 3 units) | 🟠 HIGH | Nova |
| **DUPLICATE-01** | Arquivos duplicados: `intel_excel.py` + `intel-excel.py`, `collect_report_data.py` + `collect-report-data.py` | 🟡 MEDIUM | TD-8.1 |
| **ORCHESTRATOR-01** | Dois orquestradores: `monitor.py` + `orchestrator.py` | 🟡 MEDIUM | TD-3.1 |

### 3.3 Fontes Bloqueadas (7 de 14)

| Fonte | Bloqueador | Resolução |
|-------|-----------|-----------|
| DOM-SC | Falta DOM_SC_CPF, DOM_SC_CNPJ, DOM_SC_API_KEY | Obter credenciais |
| DOE-SC | Falta DOE_SC_LOGIN, DOE_SC_PASSWORD | Obter credenciais |
| TCE-SC | Lento (SCMWeb), execução parcial | Otimizar ou aceitar latência |
| SC Compras | Portal offline | Retentar periodicamente |
| Transparência | 75/295 portais detectados, crawl não executado | Executar crawl |
| CIGA/CKAN | Nunca executado em escala | Executar |
| MiDES/BigQuery | Requer credenciais Google Cloud | Obter ou despriorizar |

---

## 4. Avaliação do EPIC-MASTER-B2G-READINESS Atual

### 4.1 Problemas Estruturais

1. **Mistura níveis de abstração:** Stories de "corrigir typo" (TD-0.3) no mesmo epic que "provisionar VPS" (FEAT-4.1) e "schema final Supabase" (B2G-5)
2. **Status inflados:** Stories "Done" com ACs não atendidos, "Ready" com dependências não resolvidas
3. **Contexto desatualizado:** Epic foi desenhado para Extra Construtora analytics. Novo contexto é CONFENGE commercial intelligence
4. **Granularidade inconsistente:** Stories de 2h (TD-0.3) misturadas com stories de 16h (TD-8.5)
5. **Dependências não encadeadas:** Fase 0→1→2→3→4→5→6→7 parece linear mas Bloqueadores reais não respeitam essa ordem
6. **Métricas-alvo herdadas do PRD antigo:** "Contract Intelligence Truth v1", "preço praticado", "win rate" — todos NOT_READY e dependem de dados que as APIs públicas não expõem

### 4.2 Stories a Manter (como base)

| ID Original | Novo ID | Ação |
|------------|---------|------|
| TD-0.1 (backup) | B2G-SEC-01 | Manter, atualizar ACs |
| TD-0.2 (imports) | B2G-FIX-01 | Manter, expandir escopo |
| TD-7.1 (lint/format) | B2G-FIX-02 | Manter, já InProgress |
| TD-1.2 (secrets) | B2G-SEC-02 | Manter |
| TD-1.3 (testes) | B2G-TEST-01 | Manter, ajustar target |
| TD-5.2 (resume crawlers) | B2G-BACKFILL-03 | Manter, expandir |

### 4.3 Stories a Reabrir

| ID Original | Motivo |
|------------|--------|
| FEAT-4.1 (Hetzner VPS) | Scripts existem mas VPS nunca provisionada. ACs marcam "Done" o que é apenas "Script Ready". Reabrir como B2G-INFRA-01. |
| TD-8.5 (Multi-source backfill) | 39.4% coverage, não 85%+. 5/7 crawlers bloqueados. ACs foram rebaixados durante QA para aprovar story. Reabrir como B2G-BACKFILL-01. |

### 4.4 Stories a Consolidar

| Originais | Consolidada | Justificativa |
|-----------|-------------|---------------|
| TD-0.2 + TD-0.3 + TD-8.2 | B2G-FIX-01 (imports + package) | Todas tratam de imports quebrados e configuração de pacote |
| TD-2.1 + TD-2.2 + TD-2.3 + TD-2.4 + B2G-5 | B2G-DB-01 (schema reconstruction) | Consolidação de todas as migrations em schema canônico único |
| TD-3.1 + TD-3.2 + TD-8.1 | B2G-REFACTOR-01 (monitor cleanup) | Eliminar duplicação, unificar orquestradores |
| TD-5.1 + TD-5.5 | B2G-OBS-01 (observabilidade) | Logging estruturado + monitoramento + alertas |
| COVERAGE-1.1 a COVERAGE-1.11 | B2G-COV-01 (entity resolution) | Consolida todas as atividades de resolução de entidades |
| FEAT-1.1 a FEAT-1.4 + FEAT-2.1 a FEAT-2.4 | B2G-CRAWL-01 a B2G-CRAWL-04 | Crawlers agrupados por plataforma |
| B2G-2 + B2G-3 | B2G-INTEL-02 (commercial signals) | Sinais comerciais integrados, não métricas isoladas |
| FIX-MANIFEST + FIX-UNIVERSE | B2G-FIX-03 (canonical universe) | Universo canônico único + manifestos corretos |
| FIX-SCHEMA-MISMATCH + FIX-TRANSACTION | B2G-FIX-04 (database integrity) | Schema alignment + transaction handling |

### 4.5 Stories a Arquivar (Obsoletas)

| ID Original | Motivo |
|------------|--------|
| COVERAGE-2.1 (MiDES BigQuery) | Fora do escopo imediato, requer GCP credentials |
| COVERAGE-3.1 (Selenium JS portals) | Playwright é preferido para novas integrações |
| FEAT-2.4 (Selenium crawler JS) | Substituído por estratégia Playwright |
| C1 (Alertas Telegram) | Backlog distante |
| C4 (Dashboard TUI) | Backlog distante |
| B2G-5 (Supabase path) | Decisão arquitetural: PostgreSQL bare metal na VPS, sem Supabase |

---

## 5. Novo Mapa de Stories — Backlog CONFENGE

### 5.1 Estrutura de Fases

```
Fase 0: CRITICAL FIXES (bloqueadores)
  ↓
Fase 1: PROVISIONING (VPS real)
  ↓
Fase 2: DATA FOUNDATION (schema + universo canônico)
  ↓
Fase 3: CRAWLER ACTIVATION (fontes ativas)
  ↓
Fase 4: BACKFILL (histórico controlado)
  ↓
Fase 5: INTELLIGENCE (sinais comerciais)
  ↓
Fase 6: HARDENING (segurança, backup, observabilidade)
  ↓
Fase 7: CONTINUOUS OPERATION (timers, monitoramento)
```

### 5.2 Stories por Fase

#### Fase 0 — CRITICAL FIXES (2-4 dias)

| ID | Título | Prioridade | Esforço | Dependências |
|----|--------|-----------|---------|-------------|
| **B2G-FIX-01** | Corrigir imports quebrados, config package e URL PNCP | P0 | M (4-6h) | Nenhuma |
| **B2G-FIX-02** | Code quality cleanup — lint + format + type hints críticos | P0 | L (8-12h) | Nenhuma |
| **B2G-FIX-03** | Universo canônico único — eliminar 6 denominadores divergentes | P0 | M (4-6h) | Nenhuma |
| **B2G-FIX-04** | Alinhar schema código↔banco + corrigir transaction handling | P0 | M (6-8h) | Nenhuma |

**Gate: READY_TO_PROVISION** — todos FIX stories Done, ruff ≤ 50 erros, testes core passam, imports OK

#### Fase 1 — PROVISIONING (1-2 dias após credenciais)

| ID | Título | Prioridade | Esforço | Dependências |
|----|--------|-----------|---------|-------------|
| **B2G-INFRA-01** | Provisionar VPS Hetzner CX22 via hcloud CLI | P0 | M (4-6h) | B2G-FIX-01, credenciais Hetzner |
| **B2G-INFRA-02** | Configurar PostgreSQL + migrations + seeds na VPS | P0 | S (2-3h) | B2G-INFRA-01 |
| **B2G-INFRA-03** | Hardening SSH + firewall + fail2ban + unattended-upgrades | P0 | S (2-3h) | B2G-INFRA-01 |
| **B2G-INFRA-04** | Backup automatizado + restore testado | P0 | M (4-6h) | B2G-INFRA-02, Storage Box |

**Gate: READY_FOR_PNCP** — VPS acessível, PostgreSQL funcional, backup→restore ciclo completo testado, schema limpo

#### Fase 2 — DATA FOUNDATION (3-5 dias)

| ID | Título | Prioridade | Esforço | Dependências |
|----|--------|-----------|---------|-------------|
| **B2G-DB-01** | Schema canônico final — migration unificada, constraints, índices | P0 | L (8-12h) | B2G-FIX-04, B2G-INFRA-02 |
| **B2G-DB-02** | Modelo canônico de dados — entidades, provenance, dedup | P0 | L (8-12h) | B2G-DB-01 |
| **B2G-DB-03** | Geocodificar 604 entidades não resolvidas | P0 | M (6-8h) | B2G-FIX-03 |
| **B2G-DB-04** | Registry de portais por entidade + detector de plataforma | P1 | M (6-8h) | B2G-DB-03 |
| **B2G-DB-05** | Sistema de checkpoints para retomada de backfill | P1 | M (6-8h) | B2G-DB-01 |

#### Fase 3 — CRAWLER ACTIVATION (5-8 dias)

| ID | Título | Prioridade | Esforço | Dependências |
|----|--------|-----------|---------|-------------|
| **B2G-CRAWL-01** | Corrigir e ativar PNCP v3 (URL, paginação, filtros, contratos) | P0 | M (6-8h) | B2G-INFRA-02 |
| **B2G-CRAWL-02** | Ativar PCP + ComprasGov em escala (já testados) | P1 | M (4-6h) | B2G-CRAWL-01 |
| **B2G-CRAWL-03** | Obter credenciais e ativar DOM-SC | P1 | M (4-6h) | Credenciais externas |
| **B2G-CRAWL-04** | Obter credenciais e ativar DOE-SC | P2 | M (4-6h) | Credenciais externas |
| **B2G-CRAWL-05** | Ativar TCE-SC com otimização de latência | P1 | M (4-6h) | B2G-CRAWL-01 |
| **B2G-CRAWL-06** | Executar Transparência crawl (75 portais detectados) | P2 | L (6-10h) | B2G-DB-04 |
| **B2G-CRAWL-07** | Estratégia Playwright para portais JS (substitui Selenium) | P2 | L (8-12h) | B2G-CRAWL-06 |

**Gate: READY_FOR_BACKFILL** — PNCP ativo e funcionando, ≥2 fontes adicionais ativas, checkpoints operacionais

#### Fase 4 — BACKFILL (5-8 dias, execução pode levar semanas)

| ID | Título | Prioridade | Esforço | Dependências |
|----|--------|-----------|---------|-------------|
| **B2G-BACKFILL-01** | Backfill PNCP controlado — 90 dias, SC/PR/RS, modalidades AEC | P0 | M (6-8h) | B2G-CRAWL-01, B2G-DB-05 |
| **B2G-BACKFILL-02** | Orquestrador de backfill — CLI, resume, status, manifest | P0 | L (8-12h) | B2G-BACKFILL-01 |
| **B2G-BACKFILL-03** | Sistema de resume/checkpoint para todos os crawlers | P1 | M (6-8h) | B2G-DB-05 |
| **B2G-BACKFILL-04** | Backfill multi-source — PCP + ComprasGov + TCE-SC | P1 | L (8-12h) | B2G-BACKFILL-01 |
| **B2G-BACKFILL-05** | Backfill DOM-SC + DOE-SC (quando credenciais disponíveis) | P2 | M (6-8h) | B2G-CRAWL-03, B2G-CRAWL-04 |

**Gate: READY_FOR_MULTI_SOURCE** — ≥4 fontes com backfill completo, cobertura ≥70% entidades no raio 200km

#### Fase 5 — INTELLIGENCE (5-8 dias)

| ID | Título | Prioridade | Esforço | Dependências |
|----|--------|-----------|---------|-------------|
| **B2G-INTEL-01** | Classificação AEC — keywords + CPV + embeddings | P0 | L (8-12h) | B2G-DB-02 |
| **B2G-INTEL-02** | Pipeline de sinais comerciais (substitui B2G-2 + B2G-3) | P0 | L (12-16h) | B2G-INTEL-01, B2G-BACKFILL-01 |
| **B2G-INTEL-03** | Scoring de leads — 12 dimensões, explicável | P1 | M (6-8h) | B2G-INTEL-02 |
| **B2G-INTEL-04** | Dossiê automático por oportunidade | P1 | L (8-12h) | B2G-INTEL-03 |
| **B2G-INTEL-05** | Cobertura comercialmente útil — métricas de recall/precisão/tempestividade | P1 | M (6-8h) | B2G-INTEL-02 |
| **B2G-INTEL-06** | DOM-SC e DOE-SC como sensores de eventos (retificação, suspensão, etc.) | P2 | M (6-8h) | B2G-CRAWL-03, B2G-CRAWL-04 |

**Gate: READY_FOR_COMMERCIAL_INTELLIGENCE** — pipeline de sinais funcionando, scoring calibrado, ≥5 oportunidades priorizadas/dia

#### Fase 6 — HARDENING (3-5 dias)

| ID | Título | Prioridade | Esforço | Dependências |
|----|--------|-----------|---------|-------------|
| **B2G-SEC-01** | Secrets management — sem hardcode, permissões mínimas | P0 | M (4-6h) | B2G-INFRA-01 |
| **B2G-SEC-02** | Firewall + fail2ban + SSH key-only + atualização automática | P0 | S (2-3h) | B2G-INFRA-03 |
| **B2G-OBS-01** | Observabilidade — logs JSON, run_id, métricas, health check | P1 | M (6-8h) | B2G-INFRA-01 |
| **B2G-TEST-01** | Testes — unit + contract + integration + smoke | P1 | L (12-16h) | B2G-FIX-01 |
| **B2G-CI-01** | CI/CD — lint gate, test gate, secrets scan, dependency audit | P2 | M (6-8h) | B2G-TEST-01 |

#### Fase 7 — CONTINUOUS OPERATION (3-5 dias)

| ID | Título | Prioridade | Esforço | Dependências |
|----|--------|-----------|---------|-------------|
| **B2G-OPS-01** | Systemd timers — unificar nomenclatura, staggered schedule, OnFailure | P1 | M (4-6h) | B2G-INFRA-01 |
| **B2G-OPS-02** | CLI operacional unificada — source-health, crawl, backfill, status, export | P1 | L (8-12h) | B2G-BACKFILL-02 |
| **B2G-OPS-03** | Disaster recovery — simulação perda VPS, bootstrap novo, restore | P1 | M (6-8h) | B2G-INFRA-04 |
| **B2G-OPS-04** | Rollout gradual — ativar timers um a um, validar cada fonte | P1 | M (4-6h) | B2G-OPS-01 |

### 5.3 Stories Estratégicas (Background)

| ID | Título | Prioridade | Esforço | Dependências |
|----|--------|-----------|---------|-------------|
| **B2G-STRAT-01** | Exa MCP como fallback de resolução de portais | P2 | S (2-3h) | B2G-DB-04 |
| **B2G-STRAT-02** | Coleta de documentos — editais, anexos, contratos | P2 | L (8-12h) | B2G-CRAWL-01 |
| **B2G-STRAT-03** | Benchmark 30 dias vs serviço pago (Alerta Licitações) | P2 | M (4-6h) | B2G-INTEL-02 |
| **B2G-STRAT-04** | Delimitação geográfica — Haversine, coordenadas obras, não apenas UF | P2 | M (4-6h) | B2G-DB-03 |

---

## 6. Gates Objetivos

### 6.1 Gate: READY TO PROVISION HETZNER

```
✅ B2G-FIX-01 Done (imports OK, PNCP URL corrigida)
✅ B2G-FIX-02 Done (ruff ≤ 50 erros, mypy core OK)
✅ B2G-FIX-03 Done (universo canônico único: 1.093)
✅ B2G-FIX-04 Done (schema alinhado, transactions com ROLLBACK)
✅ pytest core (100+ testes) passando
✅ Credenciais Hetzner (API token) obtidas
```

### 6.2 Gate: READY FOR PNCP INCREMENTAL

```
✅ B2G-INFRA-01 Done (VPS acessível via SSH)
✅ B2G-INFRA-02 Done (PostgreSQL funcional, schema limpo)
✅ B2G-INFRA-03 Done (firewall, fail2ban, SSH hardened)
✅ B2G-INFRA-04 Done (backup→restore ciclo testado)
✅ B2G-CRAWL-01 Done (PNCP v3 URL corrigida, paginação OK)
✅ PNCP incremental crawl executado na VPS — records > 0
✅ systemctl list-timers 'extra-*' mostra timers
```

### 6.3 Gate: READY FOR CONTROLLED BACKFILL

```
✅ ≥2 fontes além de PNCP ativas e funcionando
✅ B2G-DB-05 Done (checkpoint system operacional)
✅ Backfill 7 dias PNCP executado sem erros
✅ Nenhum record duplicado (content_hash unique)
✅ Manifest de execução gerado com métricas
```

### 6.4 Gate: READY FOR MULTI-SOURCE BACKFILL

```
✅ ≥4 fontes com backfill completo
✅ Cobertura ≥70% entidades no raio 200km
✅ B2G-DB-04 Done (registry de portais populado)
✅ Pipeline de dedup cross-source funcional
✅ Relatório de cobertura com denominador canônico
```

### 6.5 Gate: READY FOR COMMERCIAL INTELLIGENCE

```
✅ B2G-INTEL-01 Done (classificação AEC ≥90% precisão)
✅ B2G-INTEL-02 Done (pipeline de sinais emitindo)
✅ B2G-INTEL-03 Done (scoring ≥5 oportunidades/dia)
✅ Dossiê de exemplo gerado para CNPJ real
✅ Métricas de recall/precisão medidas (B2G-INTEL-05)
```

---

## 7. Matriz de Rastreabilidade

| Fonte Original | Stories | Cobertura |
|---------------|---------|-----------|
| PRD v2.0 (2026-07-12) | M1-M7, S1-S4, C1-C4 | Refletido nas fases 0-7 |
| EPIC-MASTER-B2G-READINESS | 60+ stories | Consolidado para ~35 stories |
| EPIC-TD-001 | 26 stories | Fase 0 + Fase 6 |
| EPIC-TD-003 | 5 stories | Fase 0 + Fase 2 |
| EPIC-FEAT-001 | 12 stories | Fase 3 + Fase 4 |
| EPIC-COVERAGE-100PCT | 20 stories | Fase 2 + Fase 4 |
| Reversa SDD (architecture.md) | 16 ADRs, 13 integrações | ADR-012 a ADR-016 ativos |
| _reversa_forward/ | — | Não implementado |
| New CONFENGE scope | 30 functional blocks | Fases 0-7 + B2G-STRAT |

---

## 8. Riscos e Mitigações (Top 10)

| Risco | Prob. | Impacto | Mitigação |
|-------|-------|---------|-----------|
| Credenciais DOM-SC/DOE-SC nunca obtidas | Alta | Alto | Iniciar sem elas (PNCP + PCP + ComprasGov cobrem parte). Tratar como opcionais. |
| PNCP API mudar novamente | Média | Alto | Teste de contrato automatizado. Alerta em health check. |
| VPS Hetzner custo acima do esperado | Baixa | Médio | CX22 é €4.50/mês. Storage Box €2.90. Margem folgada no orçamento de €15. |
| 604 entidades permanecerem sem coordenadas | Média | Médio | IBGE API resolve maioria. Fallback manual para casos restantes. |
| Volume de dados exceder 40GB SSD | Baixa | Alto | Purge 400 dias. Monitorar crescimento semanal. Plano de upgrade para volume maior. |
| Crawler quebrar por mudança de layout | Alta | Médio | Contract tests. Alerta em health check. Adapter pattern isola parsing. |
| Backfill sobrecarregar APIs públicas | Média | Médio | Rate limiting. Staggered schedule. Delay entre requests. |
| Nenhum sinal comercial de alto valor encontrado | Média | Alto | Refinar critérios. Expandir raio. Adicionar fontes. Benchmark com serviço pago. |
| Confusão entre "Done (script)" e "Done (produção)" | Alta | Alto | Gates objetivos exigem evidência de execução real. Nenhum AC "Done" sem output de produção. |
| Claude Code não conseguir operar a VPS | Baixa | Médio | Testar SSH + systemctl + journalctl no provisionamento. Documentar troubleshooting. |

---

## 9. Estimativas

| Fase | Stories | Esforço Total | Duração (part-time) |
|------|---------|--------------|---------------------|
| 0 — Critical Fixes | 4 | 22-32h | 2-4 dias |
| 1 — Provisioning | 4 | 12-18h | 1-2 dias (após credenciais) |
| 2 — Data Foundation | 5 | 36-48h | 3-5 dias |
| 3 — Crawler Activation | 7 | 40-58h | 5-8 dias |
| 4 — Backfill | 5 | 34-46h | 5-8 dias (+ tempo execução) |
| 5 — Intelligence | 6 | 46-62h | 5-8 dias |
| 6 — Hardening | 5 | 30-41h | 3-5 dias |
| 7 — Continuous Ops | 4 | 22-32h | 3-5 dias |
| **Total** | **40** | **242-337h** | **27-45 dias úteis** |

---

## 10. Decisões Pendentes (Arquitetura)

| Decisão | Opções | Recomendação |
|---------|--------|-------------|
| Supabase vs PostgreSQL bare metal | Self-hosted Supabase em Hetzner vs PostgreSQL direto | PostgreSQL direto. Single user, sem necessidade de API REST. ADR-003 revogado. |
| Playwright vs Selenium | Migrar vs Manter híbrido | Playwright para novos crawlers. Selenium legado mantido até migração. |
| Storage Box vs backup local | Hetzner Storage Box vs volume adicional | Storage Box BX11 (100GB, ~€2.90/mês). Isola backup do disco principal. |
| Terraform vs shell script | Infra as Code vs provisionamento simples | Manter shell script atual. Migrar para Terraform apenas se complexidade aumentar. |
| Intel Pipeline legado vs QW-01 Radar | Manter ambos vs Consolidar | Consolidar no QW-01 Radar. Descontinuar Intel Pipeline legado após Fase 5. |
| Exa MCP como fallback | Integrar vs Não integrar | Integrar como fallback na Fase 3 (B2G-STRAT-01). Custo por resolução é baixo. |

---

## 11. Próximos Passos Imediatos

1. **Obter credenciais Hetzner** — API token para hcloud CLI
2. **Executar Fase 0 stories** — B2G-FIX-01 a B2G-FIX-04
3. **Validar Gate READY_TO_PROVISION**
4. **Provisionar VPS** — B2G-INFRA-01 a B2G-INFRA-04
5. **Ativar PNCP incremental** — primeiro crawler em produção

---

*Auditoria gerada por Claude Opus 4.8 (DeepSeek v4 Pro) — 2026-07-14*
*Próximo documento: EPIC-MASTER-B2G-READINESS v3.0 atualizado*
