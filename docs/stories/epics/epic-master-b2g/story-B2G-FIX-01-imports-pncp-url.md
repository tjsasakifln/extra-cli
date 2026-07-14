---
story_id: B2G-FIX-01
title: "Corrigir imports quebrados, config package e URL base do PNCP"
status: Done
priority: P0
risk_level: STANDARD
effort: M
agent: "@dev"
epic: EPIC-MASTER-B2G-READINESS
phase: 0
depends_on: []
blocks: [B2G-INFRA-01, B2G-CRAWL-01]
---

# Story B2G-FIX-01: Corrigir imports quebrados, config package e URL base do PNCP

## Problema

4 bugs críticos confirmados por auditoria de código:

### 1. URL base do PNCP desatualizada (3 valores diferentes no código)

- `adapter.py` linha 57: `https://pncp.gov.br/api/consulta/v1` (hardcoded, sem env var)
- `pncp_arp_crawler.py` linha 52: `https://pncp.gov.br/api/consulta/v1` (hardcoded)
- `pncp_pca_crawler.py` linha 51: `https://pncp.gov.br/api/consulta/v1` (hardcoded)
- `config/settings.py` linha 55: `https://pncp.gov.br/api/consulta/v3` (com env var `PNCP_BASE`)
- API real: `https://pncp.gov.br/pncp-consulta/v1`

**3 URLs diferentes no mesmo projeto.** `adapter.py` ignora completamente a configuração centralizada de `config/settings.py`. A URL v1 e v3 antigas retornam timeout. A API está em `/pncp-consulta/v1`.

7 arquivos referenciam URLs antigas da PNCP.

### 2. Configuração de logging quebrada

`config/logging_config.py` linha 88 e 114: `datetime.UTC` — a classe `datetime.datetime` não tem atributo `UTC`. Em Python 3.12, o correto é `from datetime import UTC` (módulo) ou `datetime.timezone.utc`. Confirmado experimentalmente: `JsonFormatter.format()` crasha com `AttributeError`.

### 3. Arquivos duplicados com conteúdo divergente

5 pares de arquivos com mesmo nome (underscore vs hyphen), **todos com conteúdo diferente**:

| Underscore | Hyphen | Diferença |
|-----------|--------|-----------|
| `intel_excel.py` (1091 linhas) | `intel-excel.py` (1048 linhas) | MD5 diferentes |
| `intel_collect.py` (3487 linhas) | `intel-collect.py` (3251 linhas) | MD5 diferentes |
| `intel_validate.py` (1028 linhas) | `intel-validate.py` (1017 linhas) | MD5 diferentes |
| `intel_report.py` (2749 linhas) | `intel-report.py` (2592 linhas) | MD5 diferentes |
| `collect_report_data.py` (11055 linhas) | `collect-report-data.py` (11064 linhas) | MD5 diferentes |

### 4. `pyproject.toml` não declara `scripts` como pacote instalável

Scripts dependem de `PYTHONPATH` manual.

## Valor de Negócio

Sem URL correta do PNCP, zero dados novos entram no sistema. Sem imports limpos, qualquer manutenção é dificultada. Bloqueia Fase 1 (provisionamento).

## Escopo

### IN
- Atualizar URL base do PNCP em todos os 7 arquivos para `pncp-consulta/v1`
- Corrigir `datetime.UTC` → `datetime.timezone.utc`
- Resolver inconsistências de hífen vs underscore nos módulos ativos
- Garantir que `python3 -c "from scripts.crawl.monitor import main"` funciona limpo
- Garantir que `python3 -c "from scripts.opportunity_intel.cli import main"` funciona limpo
- Atualizar `pyproject.toml` se necessário para package discovery

### OUT
- Refatoração geral de código (B2G-FIX-02)
- Correção de type hints (B2G-FIX-02)
- Correção de schema (B2G-FIX-04)

## Acceptance Criteria

### AC1: PNCP URL atualizada
**Given** que a API PNCP mudou para `/pncp-consulta/v1`
**When** qualquer crawler PNCP faz uma requisição
**Then** a URL base usada é `https://pncp.gov.br/pncp-consulta/v1`
**And** o override via env var `PNCP_BASE` continua funcional

### AC2: Logging funcional
**Given** Python 3.12
**When** `config/logging_config.py` é importado
**Then** não ocorre `AttributeError: module 'datetime' has no attribute 'UTC'`

### AC3: Imports de monitor.py OK
**Given** o ambiente virtual configurado
**When** `python3 -c "from scripts.crawl.monitor import main"` é executado
**Then** não ocorre erro de import

### AC4: Imports de opportunity_intel OK
**Given** o ambiente virtual configurado
**When** `python3 -c "from scripts.opportunity_intel.cli import main"` é executado
**Then** não ocorre erro de import

### AC5: Sem regressões
**Given** as correções aplicadas
**When** `pytest tests/ -x -q --timeout=30 -k "not integration and not live"` executa
**Then** zero novos testes quebram em relação ao baseline

## Tasks

- [ ] Task 1: Atualizar URL base PNCP nos 7 arquivos
- [ ] Task 2: Corrigir `datetime.UTC` → `datetime.timezone.utc`
- [ ] Task 3: Verificar e corrigir imports quebrados (hífen vs underscore)
- [ ] Task 4: Atualizar pyproject.toml para package discovery correto
- [ ] Task 5: Executar teste de importação para todos os módulos core
- [ ] Task 6: Rodar pytest de regressão

## Definition of Done

- [ ] 7 arquivos com URL PNCP corrigida
- [ ] `logging_config.py` funcional em Python 3.12
- [ ] `from scripts.crawl.monitor import main` funciona
- [ ] `from scripts.opportunity_intel.cli import main` funciona
- [ ] pytest sem novas falhas
- [ ] ruff check limpo nos arquivos alterados

## Arquivos Afetados

- `scripts/crawl/adapter.py`
- `scripts/crawl/async_client.py`
- `scripts/crawl/pncp_crawler_adapter.py`
- `scripts/crawl/pncp_arp_crawler.py`
- `scripts/crawl/pncp_pca_crawler.py`
- `scripts/crawl/sync_client.py`
- `scripts/crawl/contracts_crawler.py`
- `config/logging_config.py`
- `pyproject.toml`

## Riscos

| Risco | Mitigação |
|-------|-----------|
| PNCP API pode ter mudado mais que só a URL | Testar endpoint `/contratos` e `/licitacoes` após correção |
| Arquivos hífen/underscore podem ser usados em produção | Verificar systemd services e cron jobs antes de remover |
