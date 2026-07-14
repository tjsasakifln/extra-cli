---
story_id: B2G-FIX-02
title: "Code quality cleanup — lint + format + type hints críticos"
status: ready
priority: P0
risk_level: STANDARD
effort: L
agent: "@dev"
epic: EPIC-MASTER-B2G-READINESS
phase: 0
depends_on: [B2G-FIX-01]
blocks: [B2G-INFRA-01]
---

# Story B2G-FIX-02: Code quality cleanup

## Problema

O projeto tem 222 erros ruff, 706+ erros mypy e cobertura de testes ~4.8%. Isso torna qualquer manutenção arriscada e dificulta o onboarding de novos desenvolvedores (humanos ou agentes).

Métricas atuais (2026-07-14):
- Ruff lint: 222 erros (após auto-fix, baseline era 932)
- Ruff format: 96/96 arquivos formatados ✅
- Mypy: 706+ erros em 60+ arquivos
- Test coverage: 4.8% (48.210 LOC, 45.887 sem cobertura)
- 1 teste quebrado: `test_canonical_views_exist`

## Valor de Negócio

Código limpo reduz o tempo de debugging, facilita implementação das Fases 1-7 e reduz risco de bugs em produção. Pré-requisito para o gate READY_TO_PROVISION.

## Escopo

### IN
- Reduzir ruff lint para ≤50 erros (apenas não-corrigíveis intencionais)
- Corrigir mypy nos top-10 módulos mais críticos: `monitor.py`, `adapter.py`, `radar.py`, `cli.py`, `ranking.py`, `manifest.py`, `transformer.py`, `dedup.py`, `scoring.py`, `status.py`
- Corrigir `test_canonical_views_exist`
- Garantir que `ruff format` passa sem alterações em todos os arquivos

### OUT
- Type hints em todos os 60+ módulos (apenas top-10)
- 100% test coverage (target é ≥30% core modules, Fase 6)
- Correção de todos os 706 erros mypy (apenas top-10 módulos)

## Acceptance Criteria

### AC1: Ruff lint gate
**Given** o código após correções
**When** `ruff check scripts/` executa
**Then** ≤50 erros reportados
**And** zero erros novos em relação ao baseline

### AC2: Ruff format gate
**Given** o código após correções
**When** `ruff format --check scripts/` executa
**Then** zero arquivos com diferenças de formatação

### AC3: Mypy top-10
**Given** os 10 módulos críticos
**When** `mypy scripts/crawl/monitor.py scripts/opportunity_intel/radar.py ...` executa
**Then** erros `no-untyped-def` e `no-any-return` reduzidos em ≥50%

### AC4: Teste canônico corrigido
**Given** o banco de dados com schema real
**When** `pytest tests/integration/test_migration_fresh_install.py::test_canonical_views_exist` executa
**Then** passa sem falha

### AC5: Sem novas regressões
**Given** as correções aplicadas
**When** `pytest tests/ -x -q` executa
**Then** zero novos testes quebrando

## Tasks

- [ ] Task 1: Executar `ruff check --fix` para auto-corrigir o que for possível
- [ ] Task 2: Corrigir manualmente erros ruff restantes (E402, N806, etc.)
- [ ] Task 3: Executar `ruff format` em todos os arquivos alterados
- [ ] Task 4: Adicionar type hints nos top-10 módulos
- [ ] Task 5: Corrigir `test_canonical_views_exist`
- [ ] Task 6: Rodar pytest de regressão completa

## Definition of Done

- [ ] ruff check scripts/ ≤50 erros
- [ ] ruff format --check scripts/ limpo
- [ ] mypy top-10 módulos com ≥50% redução de erros críticos
- [ ] test_canonical_views_exist passa
- [ ] pytest sem novas falhas

## Arquivos Afetados

- 96 arquivos Python em `scripts/` (formatação)
- Top-10 módulos: `monitor.py`, `adapter.py`, `radar.py`, `cli.py`, `ranking.py`, `manifest.py`, `transformer.py`, `dedup.py`, `scoring.py`, `status.py`
- `tests/integration/test_migration_fresh_install.py`
