---
name: extra-consultoria-system-architecture
description: "Extra Consultoria: CLI Python de inteligencia em licitacoes publicas. Single-client (Extra Construtora). 64k LOC, 8 crawlers, pipeline intel com 5 quality gates, PostgreSQL 17 + systemd timers."
metadata:
  type: project
---

# Extra Consultoria — Architecture Overview

## Project type
CLI Python puro (sem frontend web). Plataforma de crawling/licitacoes para consultoria B2G.

## Stack
- Python 3.12, PostgreSQL 17 (Hetzner VPS), systemd timers
- Crawl async com httpx, pipeline sync com subprocess
- LLM: OpenAI GPT-4.1-nano (classificacao) + text-embedding-3-small
- PDF: ReportLab, Excel: openpyxl, CLI: rich

## Critical technical debts
- **TD-001 (CRITICAL)**: `bids_crawler.py` tem imports quebrados para `ingestion/` package que nao existe no diretorio `scripts/crawl/`
- **TD-009 (CRITICAL)**: Zero testes automatizados em 64k linhas
- **TD-016 (HIGH)**: Duas implementacoes concorrentes de crawler PNCP (sync adapter em monitor.py vs async BidsCrawler)

## Key files
- Entry point crawl: `scripts/crawl/monitor.py` (687 linhas, orquestrador multi-source)
- Entry point intel: `scripts/intel_pipeline.py` (7 steps, 5 quality gates)
- Config central: `config/settings.py` (env vars) + `config/sectors_config.yaml` (14 setores, 2116 linhas)
- Database schema: `db/migrations/001` a `012`
- Deploy: `deploy/systemd/` (22 services + timers)
- Documento de arquitetura: `docs/architecture/system-architecture.md`

## For future architecture work
- Sempre verificar se alteracoes afetam os 8 crawlers + 22 services systemd
- Pipeline intel tem 5 quality gates que validam cada step -- nao quebrar o fluxo de dados entre eles
- Configuracao de setores e o unico SSOT para regras de CNAE/filtragem
- Entity matching e 3-level cascade critico -- qualquer mudanca requer validacao com dados reais
