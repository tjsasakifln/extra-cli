# EPIC-MASTER-B2G-READINESS: Plataforma de Inteligência B2G — Extra Construtora

**Epic ID:** EPIC-MASTER-B2G-READINESS (Single Source of Truth)
**Criado por:** Morgan (PM) — Synkra AIOX
**Data:** 2026-07-12
**Status:** Active
**PRD:** `docs/prd/PRD-consultoria-extra.md` v2.0

---

## Objetivo

Unificar todo o backlog de desenvolvimento da plataforma Extra Consultoria em um único epic mestre, com fases claras, dependências mapeadas e status tracking para cada story. Substitui EPIC-001, EPIC-COVERAGE-100PCT, EPIC-FEAT-001, EPIC-TD-001, EPIC-TD-002, EPIC-TD-003 como fonte única de verdade.

## Situação Atual (2026-07-12)

### Cobertura

| Indicador | Valor |
|-----------|-------|
| Total entes na planilha | 2.085 |
| Universo confirmado | 1.481 |
| Nao resolvidos (sem coordenadas) | 604 |
| Dentro do raio 200km | 1.093 |
| Fora do raio 200km | 388 |
| **Cobertura** | **64.4%** (threshold 95% — NAO PASSOU) |
| Entes com editais abertos | 220 (20.1%) |
| Entes com contratos | 404 (37.0%) |
| Freshness fresh | 479 |
| Freshness stale | 9 |
| Freshness unknown | 605 |
| Source health PNCP | 100% |

### Comercial — ALL NOT_READY

| Métrica | Status |
|---------|--------|
| contract_total_value | NOT_READY |
| desagio | NOT_READY |
| win_rate | NOT_READY |
| relicitacao_probability | NOT_READY |

### Quality

| Indicador | Valor |
|-----------|-------|
| Ruff lint | 222 erros (apos auto-fix, antes 932) |
| Ruff format | 96/96 arquivos formatados |
| Mypy | 706+ erros em 60+ arquivos |
| Test coverage | ~6% |
| Systemd timers ativos | 3/11 |
| CRITICAL/HIGH blockers | TD-0.1 backup, TD-0.2 imports quebrados, TD-8.2 module imports |

## Fases

### Fase 0 — Emergencia (Technical Debt CRITICAL)

Stories que resolvem blockers CRITICAL. Devem ser executadas antes de qualquer outra fase.

| Story | Nome | Status | Prioridade | Agente | Depende de |
|-------|------|--------|------------|--------|------------|
| TD-0.1 | Setup backup automatizado | Ready | P0 | @dev | Nenhuma |
| TD-0.2 | Corrigir imports quebrados | Ready | P0 | @dev | Nenhuma |
| TD-0.3 | Config package fix | Ready | P0 | @dev | Nenhuma |
| TD-8.2 | Fix broken module imports | Draft | P0 | @dev | Nenhuma |

### Fase 1 — Quick Wins & Qualidade

| Story | Nome | Status | Prioridade | Agente | Depende de |
|-------|------|--------|------------|--------|------------|
| TD-1.1 | Otimizacao de queries | Ready | P1 | @dev | Nenhuma |
| TD-1.2 | Remover segredos hardcoded | Ready | P1 | @dev | Nenhuma |
| TD-1.3 | Iniciar suite de testes | Ready | P1 | @qa | Nenhuma |
| TD-7.1 | Code quality cleanup (lint + format + types) | **InProgress** | P1 | @dev | Nenhuma |
| TD-8.1 | Reversa cleanup — duplicacao, subprocess, psycopg2 | Draft | P1 | @dev | TD-8.2 |
| TD-4.3 | Code review + lint automatizado | Ready | P1 | @dev | TD-7.1 |

### Fase 2 — Schema & Migrations

| Story | Nome | Status | Prioridade | Agente | Depende de |
|-------|------|--------|------------|--------|------------|
| TD-2.1 | Reconstruir migrations do zero | Ready | P1 | @data-engineer | TD-0.1 |
| TD-2.2 | Aplicar migrations adaptadas | Ready | P1 | @data-engineer | TD-2.1 |
| TD-2.3 | Normalizacao e constraints | Ready | P1 | @data-engineer | TD-2.1 |
| TD-2.4 | Sincronizar schema do DataLake | Ready | P1 | @data-engineer | TD-2.1, TD-2.2 |
| TD-8.3 | PNCP API v3 migration | Draft | P1 | @dev | TD-8.2 |
| **B2G-5** | Schema final + Supabase path | Draft | P1 | @data-engineer | TD-2.x |

### Fase 3 — Refactoring & Crawlers

| Story | Nome | Status | Prioridade | Agente | Depende de |
|-------|------|--------|------------|--------|------------|
| TD-3.1 | Refatorar monitor.py | Ready | P1 | @dev | TD-1.3 |
| TD-3.2 | Eliminar codigo duplicado | Ready | P1 | @dev | TD-0.2, TD-1.3 |
| TD-3.3 | Adicionar type hints | Ready | P1 | @dev | Nenhuma |
| TD-3.4 | Melhorar tratamento de erros | Ready | P1 | @dev | Nenhuma |
| FEAT-1.1 | Adaptar DOM-SC crawler | Ready | P1 | @dev | Nenhuma |
| FEAT-1.2 | Adaptar PCP v2 crawler | Ready | P2 | @dev | Nenhuma |
| FEAT-1.3 | Adaptar ComprasGov crawler | Ready | P2 | @dev | Nenhuma |
| FEAT-1.4 | Adaptar Contracts crawler | Ready | P3 | @dev | Nenhuma |

### Fase 4 — Coverage & Geocoding

| Story | Nome | Status | Prioridade | Agente | Depende de |
|-------|------|--------|------------|--------|------------|
| **B2G-1** | Resolver 604 entidades nao resolvidas | Draft | P0 | @dev | Nenhuma |
| COVERAGE-1.1 | Entity matching enhancement | Ready | P0 | @analyst + @dev | B2G-1 |
| COVERAGE-1.2 | CIGA CKAN crawler | Ready | P0 | @dev | Nenhuma |
| COVERAGE-1.3 | Portal Transparencia batch detect | Ready | P0 | @dev | Nenhuma |
| COVERAGE-1.4 | PNCP v3 coverage expansion | Ready | P1 | @dev | TD-8.3 |
| COVERAGE-1.5 | DOM-SC expansion | Ready | P1 | @dev | FEAT-1.1 |
| COVERAGE-1.6 | PCP coverage expansion | Ready | P1 | @dev | FEAT-1.2 |
| COVERAGE-1.7 | Gap analysis report | Ready | P1 | @analyst | B2G-1 |
| COVERAGE-1.8 | Hierarchical match | Ready | P1 | @analyst | B2G-1 |
| COVERAGE-1.9 | SC Dados Abertos fix | Ready | P1 | @dev | Nenhuma |
| COVERAGE-1.10 | PCP diagnostic | Ready | P1 | @dev | FEAT-1.2 |
| COVERAGE-1.11 | Geocoding | Ready | P1 | @dev | B2G-1 |
| COVERAGE-2.1 | MiDES BigQuery integration | Ready | P2 | @data-engineer | Nenhuma |
| COVERAGE-2.2 | SC Compras crawler activation | Ready | P2 | @dev | Nenhuma |
| COVERAGE-2.3 | DOE-SC crawler activation | Ready | P2 | @dev | Nenhuma |
| COVERAGE-2.4 | Entity coverage rebuild | Ready | P2 | @data-engineer | B2G-1 |
| COVERAGE-3.1 | Selenium crawler JS portals | Ready | P3 | @dev | Nenhuma |
| COVERAGE-3.2 | Portal Transparencia individual | Ready | P3 | @dev | COVERAGE-1.3 |
| COVERAGE-3.3 | Multi-source backfill pipeline | Ready | P3 | @dev | COVERAGE-x.x |
| COVERAGE-3.4 | Coverage validation documentation | Ready | P3 | @analyst | COVERAGE-x.x |

### Fase 5 — Comercial Metrics

| Story | Nome | Status | Prioridade | Agente | Depende de |
|-------|------|--------|------------|--------|------------|
| **B2G-2** | Metricas comerciais — preco praticado | Draft | P1 | @data-engineer | B2G-1, TD-2.x |
| **B2G-3** | Concorrencia e win rate | Draft | P1 | @data-engineer | B2G-2 |
| FEAT-3.1 | Pipeline Intel CNPJ Extra | Ready | P1 | @dev | Nenhuma |

### Fase 6 — Producao & Automacao

| Story | Nome | Status | Prioridade | Agente | Depende de |
|-------|------|--------|------------|--------|------------|
| **B2G-4** | Quality Gate Automation | Draft | P1 | @dev | TD-7.1 |
| TD-4.1 | Expandir cobertura de testes | Ready | P1 | @qa | TD-1.3, TD-3.1, TD-3.2 |
| TD-4.2 | Setup CI/CD pipeline | Ready | P1 | @devops | TD-4.1 |
| TD-5.1 | Logging estruturado | Ready | P1 | @dev | TD-3.1, TD-3.4 |
| TD-5.2 | Resume para crawlers | Ready | P2 | @dev | Nenhuma |
| TD-5.3 | Otimizacao de performance | Ready | P2 | @dev | TD-2.1 |
| TD-5.4 | Hardening de seguranca | Ready | P2 | @dev | TD-1.2 |
| TD-5.5 | Monitoramento e alertas | Ready | P2 | @dev | TD-5.1 |
| FEAT-4.1 | Provisionar Hetzner VPS | Ready | P1 | @devops | TD-0.1 |
| TD-6.1 | Documentacao operacional | Ready | P2 | @dev | Fases anteriores |
| TD-6.2 | Runbooks e onboarding | Ready | P2 | @dev | TD-6.1 |

### Fase 7 — Expansao (Backlog)

| Story | Nome | Status | Prioridade | Agente | Depende de |
|-------|------|--------|------------|--------|------------|
| FEAT-2.3 | Criar DOE-SC crawler | Ready | P2 | @dev | Nenhuma |
| C1 | Alertas Telegram | Draft | P3 | @dev | Nenhuma |
| C3 | DOE-SC integracao | Draft | P3 | @dev | FEAT-2.3 |
| C4 | Dashboard TUI | Draft | P3 | @dev | Nenhuma |

## Dependencias Grafo

```
Fase 0 (TD-0.x, TD-8.x)
  |
  v
Fase 1 (TD-1.x, TD-7.1, TD-8.1)
  |
  v
Fase 2 (TD-2.x, B2G-5, TD-8.3)
  |
  +---> Fase 3 (TD-3.x, FEAT-1.x)
  |        |
  |        v
  +---> Fase 4 (B2G-1, COVERAGE-x.x)
  |        |
  |        v
  +---> Fase 5 (B2G-2, B2G-3, FEAT-3.1)
  |
  +---> Fase 6 (B2G-4, TD-4.x, TD-5.x, FEAT-4.1)
           |
           v
       Fase 7 (FEAT-2.3, C1, C3, C4)
```

## Criterios de Sucesso Globais

- [ ] **Coverage >=95%** — `coverage_manifest.coverage.passed == True`
- [ ] **Zero unresolved** — `coverage_manifest.universe.unresolved == 0`
- [ ] **Preco praticado DISPONIVEL** — CLI mostra desagio medio por modalidade, orgao, periodo
- [ ] **Win rate DISPONIVEL** — CLI `competitors` com ranking, win rate, ticket medio
- [ ] **Quality gate automatizado** — `scripts/ci-check.sh` bloqueia commits com CRITICAL/HIGH
- [ ] **Schema unificado** — Migration 006-v3 aplicada limpa, export SQLite->PostgreSQL funcional
- [ ] **Systemd timers** — 11/11 ativos sem erro
- [ ] **Test coverage** — >=60% modulos core, >=30% suporte, >=10% geral
- [ ] **Mypy** — 50% reducao nos erros `no-untyped-def` e `no-any-return` nos top-10 modulos
- [ ] **Ruff lint** — <= 50 erros (apenas non-fixaveis intencionais)

## Historico de Epics Consolidadas

| Epic | Stories | Status Original | Destino |
|------|---------|----------------|---------|
| **EPIC-001** (docs/stories/epics/epic-001-100-cobertura/) | 7 stories | Backlog | Mantido como historico. Stories incorporadas as Fases 4 e 6 do master. |
| **EPIC-COVERAGE-100PCT** (docs/stories/epics/epic-coverage-100pct/) | 20 stories | Draft | Mantido como referencia historica. Stories incorporadas a Fase 4. |
| **EPIC-FEAT-001** (docs/stories/epics/epic-feat-001-crawlers-coverage/) | 10 stories | Ready | Mantido como historico. Stories incorporadas as Fases 3, 5, 7. |
| **EPIC-TD-001** (docs/stories/epics/epic-td-001-resolution/) | 22 stories | Ready | Mantido como historico. Stories incorporadas as Fases 0-6. |
| **EPIC-TD-002** (docs/stories/epics/epic-td-002-code-quality/) | 1 story | — | Fundido ao EPIC-TD-001. Story TD-7.1 em InProgress. |
| **EPIC-TD-003** (docs/stories/epics/epic-td-003-reversa-remediation/) | 5 stories | Draft | Mantido como historico. Stories incorporadas as Fases 0-2. |

## Stories Novas (Criadas neste master)

| Story ID | Nome | Fase | Arquivo |
|----------|------|------|---------|
| B2G-1 | Resolver 604 entidades nao resolvidas | Fase 4 | `docs/stories/epics/epic-master-b2g/story-B2G-1-resolver-604-unresolved.md` |
| B2G-2 | Metricas comerciais — preco praticado | Fase 5 | `docs/stories/epics/epic-master-b2g/story-B2G-2-preco-praticado.md` |
| B2G-3 | Concorrencia e win rate | Fase 5 | `docs/stories/epics/epic-master-b2g/story-B2G-3-concorrencia-win-rate.md` |
| B2G-4 | Quality Gate Automation | Fase 6 | `docs/stories/epics/epic-master-b2g/story-B2G-4-quality-gate-automation.md` |
| B2G-5 | Schema final + Supabase path | Fase 2 | `docs/stories/epics/epic-master-b2g/story-B2G-5-schema-supabase-path.md` |

## ADRs Criados

| ADR | Título | Arquivo |
|-----|--------|---------|
| ADR-002 | Preco Praticado — Multi-source Value Semantics | `docs/decisions/adr-002-preco-praticado.md` |
| ADR-003 | Supabase Self-Hosted em Hetzner | `docs/decisions/adr-003-supabase-self-hosted.md` |

---

*Epic gerado por Morgan (PM Agent) — Synkra AIOX v5.2.9*
