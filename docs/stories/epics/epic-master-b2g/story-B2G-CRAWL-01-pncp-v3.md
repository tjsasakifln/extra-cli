---
story_id: B2G-CRAWL-01
title: "Corrigir e ativar PNCP v3 — URL, paginação, filtros, contratos"
status: ready
priority: P0
risk_level: STANDARD
effort: M
agent: "@dev"
epic: EPIC-MASTER-B2G-READINESS
phase: 3
depends_on: [B2G-FIX-01, B2G-INFRA-02]
blocks: [B2G-BACKFILL-01]
---

# Story B2G-CRAWL-01: Corrigir e ativar PNCP v3

## Problema

O PNCP é a fonte primária e mais confiável, mas o código tem 3 URLs diferentes:
- `adapter.py`: `api/consulta/v1` (hardcoded, ignora config centralizada)
- `settings.py`: `api/consulta/v3` (com env var `PNCP_BASE`)
- API real: `pncp-consulta/v1`

7 arquivos referenciam URLs antigas. O crawler PNCPAdapter não usa a configuração centralizada de `config/settings.py`. O relatório de cobertura real (2026-07-11) mostrou que o PNCP cobre apenas 8.2% das entidades no raio 200km — mas é a única fonte atualmente funcional com dados históricos.

## Escopo

**IN:** Unificar URL base via `config/settings.py` + env var `PNCP_BASE`, corrigir todos os crawlers para usar config centralizada, validar endpoints (contratos, licitações, documentos), testar paginação, adicionar contract tests, executar crawl incremental na VPS.

**OUT:** Backfill histórico (B2G-BACKFILL-01), PNCP ARP/PCA (fontes secundárias).

## Acceptance Criteria

1. **AC1:** Todos os crawlers PNCP usam `config.settings.PNCP_BASE` (não valor hardcoded)
2. **AC2:** `PNCP_BASE` default = `https://pncp.gov.br/pncp-consulta/v1`
3. **AC3:** Crawl incremental (1 dia, SC) retorna records > 0 sem erros HTTP
4. **AC4:** Endpoint de contratos funcional — `valor_global` populado
5. **AC5:** Endpoint de editais funcional — dados de modalidade, data, órgão
6. **AC6:** Rate limit respeitado — sem 429 após 50+ requests
7. **AC7:** Contract test: `pytest tests/test_crawler_pncp.py -v` passa

## Tasks

- [ ] Task 1: Atualizar `config/settings.py` com URL correta default
- [ ] Task 2: Refatorar `adapter.py` para usar `settings.PNCP_BASE`
- [ ] Task 3: Corrigir 7 arquivos com URLs antigas
- [ ] Task 4: Executar crawl incremental na VPS
- [ ] Task 5: Validar contratos e editais nos resultados
- [ ] Task 6: Adicionar contract tests
- [ ] Task 7: Criar systemd timer `extra-crawl-pncp.timer`

## Definition of Done

- [ ] URL única e correta em todos os crawlers PNCP
- [ ] Crawl incremental funcional na VPS
- [ ] Contratos e editais retornando dados
- [ ] Contract tests passando
- [ ] Systemd timer ativo

## Arquivos Afetados

- `config/settings.py`
- `scripts/crawl/adapter.py`
- `scripts/crawl/pncp_crawler_adapter.py`
- `scripts/crawl/pncp_arp_crawler.py`
- `scripts/crawl/pncp_pca_crawler.py`
- `scripts/crawl/async_client.py`
- `scripts/crawl/sync_client.py`
- `scripts/crawl/contracts_crawler.py`
- `deploy/systemd/extra-crawl-pncp.service` (novo, unificado)
- `deploy/systemd/extra-crawl-pncp.timer` (novo)
