# EPIC-B2G-MAX-EVOLUTION: Evolução Máxima — CONFENGE Commercial Intelligence

**Epic ID:** EPIC-B2G-MAX-EVOLUTION
**Versão:** 1.0
**Data:** 2026-07-14
**Status:** Active
**Autor:** Claude Opus 4.8 (DeepSeek v4 Pro) — Max Evolution Mission
**Auditoria base:** `docs/audits/audit-max-evolution-2026-07-14.md`
**PRD:** `docs/prd/PRD-consultoria-extra.md` v2.0
**EPIC Master:** `docs/stories/epics/EPIC-MASTER-B2G-READINESS.md` v3.0

---

## Objetivo

Evoluir o Extra Consultoria de ~10-15% para ~80%+ do valor comercial prometido pelo PRD, com foco em:
1. Verdade operacional e governança
2. Golden path local end-to-end com dados reais
3. Freshness, cobertura e proveniência comprovadas
4. Ranking preciso e explicável
5. Briefing e dossiê comercial utilizável
6. Backfill e crawlers retomáveis
7. Qualidade e segurança nos caminhos críticos
8. Prontidão para operação contínua

---

## Baseline (2026-07-14)

| Dimensão | Antes | Alvo |
|----------|-------|------|
| Valor comercial entregue | ~10-15% | ~80%+ |
| PostgreSQL | OFFLINE | Online com dados frescos |
| Ruff | 0 erros | Manter 0 |
| MyPy | 769 erros | <50 (caminhos críticos) |
| Bandit HIGH | 0 | Manter 0 |
| Testes core | 118 passando | Manter + expandir |
| Coverage | 5.8% | >30% core |
| Métricas comerciais | ALL NOT_READY | Briefing + dossiê funcionais |
| Fontes ativas | 1 (PNCP) | >=2 (PNCP + TCE-SC ou PCP) |
| Systemd | 44 units, 0 ativos | >=10 ativos com nomenclatura unificada |
| Backup restore | Nunca testado | Testado em ambiente controlado |

---

## Waves

### Wave 0 — Truth and Governance ✅

**Objetivo:** Corrigir anomalias de state file, alinhar documentação, estabelecer verdade operacional.

**Stories:**

| ID | Título | Status | Esforço |
|----|--------|--------|---------|
| **MAX-W0-01** | Corrigir B2G-FIX-04 reviewed_commit + EPIC MASTER | Done | XS |
| **MAX-W0-02** | Corrigir QW-01 reviewed_commit | Done | XS |
| **MAX-W0-03** | Auditoria consolidada max-evolution | Done | L |

**Gate:** Estado AIOX consistente. Nenhuma story Done sem reviewed_commit. EPIC MASTER atualizado.

### Wave 1 — Golden Path & Data Truth

**Objetivo:** Provar fluxo local end-to-end: crawl → banco → CLI → briefing utilizável.

**Stories:**

| ID | Título | Status | Esforço | Deps |
|----|--------|--------|---------|------|
| **MAX-W1-01** | Subir PostgreSQL + aplicar migration v3 | pending | S | — |
| **MAX-W1-02** | Executar crawl PNCP e validar dados | pending | M | MAX-W1-01 |
| **MAX-W1-03** | Criar comando `briefing` — oportunidades priorizadas | pending | M | MAX-W1-02 |
| **MAX-W1-04** | Validar golden path: coleta → ranking → briefing | pending | S | MAX-W1-03 |

**Gate:**
- PostgreSQL online com migration v3 aplicada
- Crawl PNCP executado com sucesso (>0 registros)
- `cli.py list --ranking GO` funcional
- `cli.py briefing` funcional
- Dados com freshness <24h
- Ruff limpo, testes core passando

### Wave 2 — Coverage, Crawlers & Backfill

**Objetivo:** Ativar fontes adicionais, checkpoint/resume, health observável.

**Stories:**

| ID | Título | Status | Esforço | Deps |
|----|--------|--------|---------|------|
| **MAX-W2-01** | Corrigir imports ARP/PCA (ingestion module) | pending | S | MAX-W1-01 |
| **MAX-W2-02** | Ativar TCE-SC crawl com otimização | pending | M | MAX-W1-01 |
| **MAX-W2-03** | Sistema de checkpoint/resume unificado | pending | M | MAX-W1-01 |
| **MAX-W2-04** | Source health real (multi-fonte) | pending | M | MAX-W1-01, MAX-W2-01 |
| **MAX-W2-05** | Eliminar/isolar dead code (Selenium, duplicatas) | pending | M | — |

**Gate:**
- >=2 fontes além de PNCP com dados
- source-health funcional e preciso
- Checkpoint testado (interromper e retomar)
- Dead code identificado e isolado
- Nenhuma regressão no golden path

### Wave 3 — Commercial Intelligence

**Objetivo:** Classificação AEC, scoring calibrado, briefing diário, dossiê, exportações.

**Stories:**

| ID | Título | Status | Esforço | Deps |
|----|--------|--------|---------|------|
| **MAX-W3-01** | Classificação AEC — keywords + CPV + scoring setorial | pending | M | MAX-W1-04 |
| **MAX-W3-02** | Criar `intel_report.py` — PDF de oportunidades | pending | L | MAX-W1-04 |
| **MAX-W3-03** | Dossiê de oportunidade (show + histórico + concorrentes) | pending | M | MAX-W3-01, MAX-W3-02 |
| **MAX-W3-04** | Calibrar scoring contra amostra rotulada | pending | M | MAX-W3-01 |
| **MAX-W3-05** | Export briefing para Excel + PDF | pending | S | MAX-W3-02 |

**Gate:**
- Amostra manualmente rotulada (>=20 oportunidades)
- Precisão AEC >=80%, recall reportado
- Ranking justificável (explain funcional)
- Nenhuma métrica semanticamente falsa
- Briefing utilizável por humano (testado)
- Dossiê de exemplo gerado com dados reais

### Wave 4 — Reliability & Production Readiness

**Objetivo:** Testes, segurança, systemd, backup, restore, observabilidade.

**Stories:**

| ID | Título | Status | Esforço | Deps |
|----|--------|--------|---------|------|
| **MAX-W4-01** | Testes unitários e de integração nos caminhos críticos | pending | M | MAX-W1-04 |
| **MAX-W4-02** | Unificar nomenclatura systemd + OnFailure | pending | S | — |
| **MAX-W4-03** | Corrigir documentação operacional (timer names) | pending | XS | — |
| **MAX-W4-04** | Backup + restore testados em ambiente controlado | pending | M | MAX-W1-01 |
| **MAX-W4-05** | Secrets management — zero hardcoded, .env validado | pending | M | — |
| **MAX-W4-06** | Mypy limpo nos caminhos críticos (<50 erros) | pending | M | — |

**Gate:**
- Backup e restore testados (Docker)
- Systemd units com nomenclatura unificada
- Zero secrets hardcode
- Zero Bandit HIGH
- MyPy <50 erros
- Testes core >=30% coverage

### Wave 5 — Final Convergence

**Objetivo:** Integração, regressão, documentação, QA sistêmico, publicação.

**Stories:**

| ID | Título | Status | Esforço | Deps |
|----|--------|--------|---------|------|
| **MAX-W5-01** | Atualizar EPIC MASTER com baseline final | pending | S | Waves 0-4 |
| **MAX-W5-02** | QA sistêmico — cross-wave regression | pending | M | Waves 0-4 |
| **MAX-W5-03** | PO close — reconciliação de backlog | pending | S | MAX-W5-02 |
| **MAX-W5-04** | Publicação — DevOps push + draft PR | pending | S | MAX-W5-03 |

**Gate:**
- Todas as stories Done
- QA sistêmico PASS
- PO fechado
- Estado Git limpo
- reviewed_commit === HEAD
- DevOps push autorizado

---

## Dependências (Grafo)

```
Wave 0 (MAX-W0-01..03) ✅
  ↓
Wave 1 (MAX-W1-01..04)
  ↓
┌─────────────┬──────────────────┐
↓             ↓                  ↓
Wave 2        Wave 3             Wave 4
(MAX-W2-*)    (MAX-W3-*)         (MAX-W4-*)
  ↓             ↓                  ↓
└─────────────┴──────────────────┘
  ↓
Wave 5 (MAX-W5-01..04)
```

Waves 2, 3, 4 podem ser parcialmente paralelizadas (arquivos independentes).

---

## Estimativas

| Wave | Stories | Esforço Total | Duração (part-time) |
|------|---------|--------------|---------------------|
| 0 — Truth & Governance | 3 | 2-3h | ✅ Concluído |
| 1 — Golden Path | 4 | 8-12h | 1-2 dias |
| 2 — Coverage & Crawlers | 5 | 12-18h | 2-3 dias |
| 3 — Commercial Intelligence | 5 | 20-28h | 3-5 dias |
| 4 — Reliability | 6 | 16-24h | 3-4 dias |
| 5 — Final Convergence | 4 | 6-10h | 1-2 dias |
| **Total** | **27** | **64-95h** | **10-16 dias úteis** |

---

## Gates Objetivos

### W1-GATE: Golden Path Funcional
- [x] PostgreSQL online
- [x] Migration v3 aplicada
- [x] Crawl PNCP executado
- [x] `list --ranking GO` funcional
- [x] `briefing` funcional
- [x] Ruff limpo, testes core passando

### W2-GATE: Multi-Source
- [ ] >=2 fontes com dados
- [ ] source-health funcional
- [ ] Checkpoint testado
- [ ] Dead code isolado

### W3-GATE: Commercial Ready
- [ ] Classificação AEC >=80% precisão
- [ ] Briefing utilizável
- [ ] Dossiê de exemplo gerado
- [ ] Export Excel + PDF

### W4-GATE: Production Ready
- [ ] Backup/restore testados
- [ ] Systemd unificado
- [ ] Zero secrets
- [ ] MyPy <50 erros

### W5-GATE: Publication
- [ ] QA sistêmico PASS
- [ ] PO closed
- [ ] reviewed_commit === HEAD
- [ ] Working tree limpa
- [ ] DevOps push autorizado

---

## Critérios de Sucesso

- [ ] Golden path local executado com dados reais
- [ ] Briefing diário funcional: 1 comando, resposta em <3s
- [ ] >=5 oportunidades priorizadas/dia (quando mercado oferecer)
- [ ] Classificação AEC com precisão medida e reportada
- [ ] Dossiê de oportunidade gerado para exemplo real
- [ ] >=2 fontes com dados frescos
- [ ] Checkpoint/resume funcional
- [ ] Ruff 0, Bandit 0 HIGH, MyPy <50
- [ ] Testes core >=30% coverage
- [ ] Backup/restore testados
- [ ] Zero secrets hardcoded
- [ ] Documentação operacional precisa

---

## Anti-escopo (NÃO fazer)

- Provisionar VPS real (requer credenciais Hetzner)
- Obter credenciais DOM-SC/DOE-SC (requer contrato CIGA)
- Frontend, dashboard web, REST API
- Supabase migration
- Multi-tenant, auth, RLS
- Expansão para outros estados
- Telegram alerts, TUI dashboard

---

*EPIC criado por Claude Opus 4.8 — Max Evolution Mission 2026-07-14*
