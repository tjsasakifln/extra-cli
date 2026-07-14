# EPIC-MASTER-B2G-READINESS v3.0: Infraestrutura de Inteligência B2G — CONFENGE

**Epic ID:** EPIC-MASTER-B2G-READINESS (Single Source of Truth)
**Versão:** 3.0
**Data:** 2026-07-14
**Status:** Active
**Autor:** Claude Opus 4.8 (DeepSeek v4 Pro) — Auditoria + Consolidação
**PRD:** `docs/prd/PRD-consultoria-extra.md` v2.0
**Auditoria:** `docs/audits/audit-b2g-readiness-2026-07-14.md`

---

## Mudanças na v3.0

1. **Contexto estratégico atualizado:** De "Extra Construtora analytics" para "CONFENGE commercial intelligence"
2. **60+ stories consolidadas em ~35 stories** com dependências lineares e gates verificáveis
3. **Stories "Done" reabertas** quando ACs não foram verificados em ambiente real (FEAT-4.1, TD-8.5)
4. **Stories "Ready" reavaliadas** — FIX-UNIVERSE e FIX-TRANSACTION marcadas como implementadas
5. **Stories obsoletas arquivadas** — B2G-5 (Supabase path), COVERAGE-2.1 (MiDES), C1/C4 (Telegram/TUI)
6. **Gates objetivos** que exigem evidência de execução real, não apenas script
7. **Nomenclatura unificada:** `B2G-{FASE}-{NUM}` para todas as stories

---

## Objetivo

Infraestrutura de inteligência B2G para CONFENGE: coleta multi-source → backfill histórico → sinais comerciais → operação contínua em VPS Hetzner de baixo custo.

**Métrica principal:** capacidade de detectar oportunidades comercialmente relevantes (poucas, priorizadas, acionáveis), não volume bruto de dados.

---

## Baseline Real (2026-07-14)

### O que realmente existe e funciona

| Componente | Status |
|-----------|--------|
| 14 crawlers implementados (código) | ✅ |
| Crawlers funcionalmente testados (não quebrados) | ✅ 10/14 (ARP e PCA quebrados, Selenium zumbi, bids_crawler dead code) |
| Crawlers com teste de escala (>0 records) | ⚠️ 3/14 (PNCP 1.463, PCP 251, ComprasGov 1.508) |
| PNCP URL correta | ❌ 7 arquivos com URL antiga |
| PostgreSQL local com 41 migrations | ✅ (schema diverge do código em 10 tabelas) |
| 20 systemd timer pairs | ✅ (3 padrões de nomenclatura inconsistentes) |
| Backup script (410 linhas) | ✅ (nunca testado com Storage Box real) |
| Restore script (255 linhas) | ✅ (nunca testado com restore real) |
| VPS Hetzner provisionada | ❌ (scripts existem, nunca executados) |
| 604 entidades geocodificadas | ❌ (scripts existem, nunca executados) |
| Universo canônico único | ⚠️ (FIX-UNIVERSE 95% implementado, falta coverage/manifest.py) |
| Testes (1.230 funções) | ⚠️ 4.8% coverage, 1 teste quebrado |
| Cobertura real de entidades | 39.4% (822/2.085) multi-source; 8.2% (90/1.093) só PNCP |

### O que está "Done" mas não está em produção

| Story | Status documentado | Estado real |
|-------|-------------------|-------------|
| FEAT-4.1 (Hetzner VPS) | Done | Scripts criados. VPS nunca provisionada. |
| TD-8.5 (Multi-source backfill) | Done | 39.4% coverage. 5/7 crawlers não executaram. ACs rebaixados durante QA. |
| FIX-UNIVERSE | In Review | 95% implementado. Só falta `coverage/manifest.py`. |
| FIX-TRANSACTION | Ready | Código implementado e funcional. Status desatualizado. |

---

## Fases e Stories

### Fase 0 — CRITICAL FIXES (bloqueadores)

**Gate: READY_TO_PROVISION**

| ID | Título | Status | Esforço | Deps |
|----|--------|--------|---------|------|
| **B2G-FIX-01** | Corrigir imports, PNCP URL, logging, arquivos duplicados | ready | M | — |
| **B2G-FIX-02** | Code quality cleanup — lint + format + type hints | ready | L | B2G-FIX-01 |
| **B2G-FIX-03** | Universo canônico único (finalizar FIX-UNIVERSE) | ready | S | — |
| **B2G-FIX-04** | Alinhar schema código↔banco (finalizar FIX-SCHEMA-MISMATCH) | ready | M | — |

### Fase 1 — PROVISIONING (VPS real)

**Gate: READY_FOR_PNCP**

| ID | Título | Status | Esforço | Deps |
|----|--------|--------|---------|------|
| **B2G-INFRA-01** | Provisionar VPS Hetzner CX22 + unificar systemd | ready | M | Fase 0 |
| **B2G-INFRA-02** | PostgreSQL + migrations + seeds na VPS | ready | S | B2G-INFRA-01, B2G-FIX-04 |
| **B2G-INFRA-03** | Hardening SSH + firewall + fail2ban | ready | S | B2G-INFRA-01 |
| **B2G-INFRA-04** | Backup automatizado + restore testado | ready | M | B2G-INFRA-02 |

### Fase 2 — DATA FOUNDATION

**Gate: READY_FOR_BACKFILL (parcial)**

| ID | Título | Status | Esforço | Deps |
|----|--------|--------|---------|------|
| **B2G-DB-01** | Schema canônico final — baseline limpa, constraints, índices | ready | L | B2G-FIX-04, B2G-INFRA-02 |
| **B2G-DB-02** | Modelo canônico de dados — entidades, provenance, dedup | draft | L | B2G-DB-01 |
| **B2G-DB-03** | Geocodificar 604 entidades não resolvidas | ready | M | B2G-FIX-03 |
| **B2G-DB-04** | Registry de portais por entidade + detector de plataforma | draft | M | B2G-DB-03 |
| **B2G-DB-05** | Sistema de checkpoints para retomada de backfill | ready | M | B2G-DB-01 |

### Fase 3 — CRAWLER ACTIVATION

| ID | Título | Status | Esforço | Deps |
|----|--------|--------|---------|------|
| **B2G-CRAWL-01** | Corrigir e ativar PNCP v3 | ready | M | B2G-FIX-01, B2G-INFRA-02 |
| **B2G-CRAWL-02** | Ativar PCP + ComprasGov em escala | ready | M | B2G-CRAWL-01 |
| **B2G-CRAWL-03** | Obter credenciais e ativar DOM-SC | ready | M | Credenciais |
| **B2G-CRAWL-04** | Obter credenciais e ativar DOE-SC | ready | M | Credenciais |
| **B2G-CRAWL-05** | Ativar TCE-SC com otimização | ready | M | B2G-CRAWL-01 |
| **B2G-CRAWL-06** | Executar Transparência crawl (75 portais) | ready | L | B2G-DB-04 |
| **B2G-CRAWL-07** | Estratégia Playwright (substitui Selenium) | draft | L | B2G-CRAWL-06 |

### Fase 4 — BACKFILL

**Gate: READY_FOR_MULTI_SOURCE**

| ID | Título | Status | Esforço | Deps |
|----|--------|--------|---------|------|
| **B2G-BACKFILL-01** | Backfill PNCP controlado — 90 dias | ready | M | B2G-CRAWL-01, B2G-DB-01, B2G-DB-05 |
| **B2G-BACKFILL-02** | Orquestrador de backfill — CLI, resume, status | ready | L | B2G-BACKFILL-01 |
| **B2G-BACKFILL-03** | Sistema de resume/checkpoint para todos os crawlers | ready | M | B2G-DB-05 |
| **B2G-BACKFILL-04** | Backfill multi-source — PCP + ComprasGov + TCE-SC | ready | L | B2G-BACKFILL-01 |
| **B2G-BACKFILL-05** | Backfill DOM-SC + DOE-SC (quando credenciais) | ready | M | B2G-CRAWL-03, B2G-CRAWL-04 |

### Fase 5 — INTELLIGENCE

**Gate: READY_FOR_COMMERCIAL_INTELLIGENCE**

| ID | Título | Status | Esforço | Deps |
|----|--------|--------|---------|------|
| **B2G-INTEL-01** | Classificação AEC — keywords + CPV + embeddings | draft | L | B2G-DB-02 |
| **B2G-INTEL-02** | Pipeline de sinais comerciais para CONFENGE | ready | L | B2G-INTEL-01, B2G-BACKFILL-01 |
| **B2G-INTEL-03** | Scoring de leads — 12 dimensões, explicável | draft | M | B2G-INTEL-02 |
| **B2G-INTEL-04** | Dossiê automático por oportunidade | draft | L | B2G-INTEL-03 |
| **B2G-INTEL-05** | Cobertura comercialmente útil (recall/precisão) | draft | M | B2G-INTEL-02 |
| **B2G-INTEL-06** | DOM-SC e DOE-SC como sensores de eventos | draft | M | B2G-CRAWL-03, B2G-CRAWL-04 |

### Fase 6 — HARDENING

| ID | Título | Status | Esforço | Deps |
|----|--------|--------|---------|------|
| **B2G-SEC-01** | Secrets management — sem hardcode, permissões mínimas | ready | M | B2G-INFRA-01 |
| **B2G-SEC-02** | Firewall + fail2ban + SSH key-only | ready | S | B2G-INFRA-03 |
| **B2G-OBS-01** | Observabilidade — logs JSON, métricas, health check | ready | M | B2G-INFRA-01 |
| **B2G-OBS-02** | CLI operacional unificada | ready | L | B2G-BACKFILL-02 |
| **B2G-TEST-01** | Testes — unit + contract + integration + smoke | ready | L | B2G-FIX-01 |
| **B2G-CI-01** | CI/CD — lint gate, test gate, secrets scan | draft | M | B2G-TEST-01 |

### Fase 7 — CONTINUOUS OPERATION

| ID | Título | Status | Esforço | Deps |
|----|--------|--------|---------|------|
| **B2G-OPS-01** | Unificar e ativar systemd timers | ready | M | B2G-INFRA-01 |
| **B2G-OPS-03** | Disaster recovery — simulação perda VPS + bootstrap | ready | M | B2G-INFRA-04 |
| **B2G-OPS-04** | Rollout gradual — ativar timers um a um | ready | M | B2G-OPS-01 |

### Backlog Estratégico

| ID | Título | Status | Esforço |
|----|--------|--------|---------|
| **B2G-STRAT-01** | Exa MCP como fallback de resolução de portais | draft | S |
| **B2G-STRAT-02** | Coleta de documentos — editais, anexos, contratos | draft | L |
| **B2G-STRAT-03** | Benchmark 30 dias vs serviço pago | draft | M |
| **B2G-STRAT-04** | Delimitação geográfica precisa (Haversine obra) | draft | M |

---

## Dependências (Grafo)

```
Fase 0 (B2G-FIX-01..04)
  ↓
Fase 1 (B2G-INFRA-01..04)
  ↓
Fase 2 (B2G-DB-01..05) ─────────────┐
  ↓                                  │
Fase 3 (B2G-CRAWL-01..07)           │
  ↓                                  │
Fase 4 (B2G-BACKFILL-01..05) ←──────┘
  ↓
Fase 5 (B2G-INTEL-01..06)
  ↓
Fase 6 (B2G-SEC-*, B2G-OBS-*, B2G-TEST-*, B2G-CI-*)  (paralelo com Fase 5)
  ↓
Fase 7 (B2G-OPS-01..04)
```

---

## Gates Objetivos

### READY_TO_PROVISION
- [ ] B2G-FIX-01..04 Done
- [ ] ruff ≤50 erros
- [ ] pytest core passando
- [ ] Credenciais Hetzner obtidas

### READY_FOR_PNCP
- [ ] VPS acessível via SSH
- [ ] PostgreSQL funcional, schema limpo
- [ ] Backup→restore ciclo testado
- [ ] PNCP incremental funcional na VPS

### READY_FOR_BACKFILL (controlado)
- [ ] PNCP ativo e funcionando
- [ ] ≥2 fontes adicionais ativas
- [ ] Checkpoints operacionais
- [ ] Backfill 7 dias executado sem erro

### READY_FOR_MULTI_SOURCE
- [ ] ≥4 fontes com backfill completo
- [ ] Cobertura ≥70% entidades no raio 200km
- [ ] Registry de portais populado
- [ ] Dedup cross-source funcional

### READY_FOR_COMMERCIAL_INTELLIGENCE
- [ ] Classificação AEC ≥90% precisão
- [ ] Pipeline de sinais emitindo ≥5 oportunidades/dia
- [ ] Scoring calibrado
- [ ] Dossiê de exemplo gerado

---

## Critérios de Sucesso Globais

- [ ] Cobertura ≥70% entidades no raio 200km (realista; 95% requer resolver 604 unresolved)
- [ ] ≥5 oportunidades comerciais priorizadas/dia
- [ ] Custo mensal ≤€15 (VPS + Storage Box)
- [ ] Backup→restore testado e documentado
- [ ] 20+ systemd timers ativos com nomenclatura unificada
- [ ] CLI operacional: source-health, crawl, backfill, signals, export
- [ ] Zero secrets hardcoded
- [ ] Testes core ≥30% coverage

---

## Stories Consolidadas/Arquivadas

| Story Original | Destino |
|---------------|---------|
| EPIC-001, EPIC-COVERAGE-100PCT, EPIC-FEAT-001, EPIC-TD-001..003 | Consolidados neste master |
| B2G-1 (604 entidades) | → B2G-DB-03 |
| B2G-2 (preço praticado) + B2G-3 (win rate) | → B2G-INTEL-02 (sinais comerciais) |
| B2G-4 (quality gate) | → B2G-CI-01 + B2G-TEST-01 |
| B2G-5 (Supabase path) | **Arquivado** — decisão: PostgreSQL bare metal |
| FIX-MANIFEST + FIX-UNIVERSE | → B2G-FIX-03 |
| FIX-SCHEMA-MISMATCH + FIX-TRANSACTION | → B2G-FIX-04 (schema apenas; transaction já implementado) |
| TD-0.1..0.3, TD-8.2 | → B2G-FIX-01 |
| TD-7.1, TD-3.3 | → B2G-FIX-02 |
| TD-2.1..2.4 | → B2G-DB-01 |
| TD-5.2, TD-8.5 | → B2G-BACKFILL-01..03 |
| FEAT-4.1 | → B2G-INFRA-01..04 (reaberta) |
| FEAT-1.1..1.4, FEAT-2.1..2.4 | → B2G-CRAWL-01..07 |
| COVERAGE-1.1..1.11 | → B2G-DB-03 + B2G-DB-04 |
| COVERAGE-2.1 (MiDES) | **Arquivado** |
| COVERAGE-3.1 (Selenium JS) | → B2G-CRAWL-07 (Playwright) |
| C1, C4 (Telegram, TUI) | **Arquivado** (backlog distante) |
| B2G-STRAT-01..04 | **Novos** — escopo CONFENGE |

---

## Estimativas

| Fase | Stories | Esforço Total | Duração (part-time) |
|------|---------|--------------|---------------------|
| 0 — Critical Fixes | 4 | 22-32h | 2-4 dias |
| 1 — Provisioning | 4 | 12-18h | 1-2 dias |
| 2 — Data Foundation | 5 | 36-48h | 3-5 dias |
| 3 — Crawler Activation | 7 | 40-58h | 5-8 dias |
| 4 — Backfill | 5 | 34-46h | 5-8 dias (+ execução) |
| 5 — Intelligence | 6 | 46-62h | 5-8 dias |
| 6 — Hardening | 6 | 36-49h | 3-5 dias |
| 7 — Continuous Ops | 3 | 18-26h | 3-5 dias |
| **Total** | **40** | **242-337h** | **27-45 dias úteis** |

---

*EPIC-MASTER v3.0 — 2026-07-14*
*Próximo passo: executar Fase 0 (B2G-FIX-01 a B2G-FIX-04)*
