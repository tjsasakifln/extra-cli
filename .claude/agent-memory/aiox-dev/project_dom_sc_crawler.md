---
name: project_dom_sc_crawler
description: DOM-SC Crawler adaptado para interface monitor.py — FEAT-1.1
metadata:
  type: project
---

# DOM-SC Crawler Adaptado (FEAT-1.1)

DOM-SC (`diariomunicipal.sc.gov.br`) crawler adaptado em `scripts/crawl/dom_sc_crawler.py` para a interface sync do monitor.py.

## Interface

- `crawl(mode) -> list[dict]` — busca da API (full=90d, incremental=3d)
- `transform(records) -> list[dict]` — normaliza para schema `pncp_raw_bids`

## Detalhes Tecnicos

- **Auth**: HTTP Basic (CPF:CNPJ) + header X-API-Key
- **API**: `/?r=remote/search` com `com_metadados=1` retorna JSON (nao HTML). BeautifulSoup/lxml nao e necessario.
- **Categorias**: 6 (Contratos), 7 (Convenios), 28 (Empenhos) — 3 chamadas por crawl
- **Dependencias**: apenas stdlib (hashlib, json, urllib, base64, etc.) — zero ARQ/Redis/Supabase
- **Timeout**: 60s com tratamento de erro
- **Rate limit**: 0.5s entre categorias
- **Schema**: saida compativel com `upsert_pncp_raw_bids`. Campo `source='dom_sc'` adicionado pelo monitor.py.
- **Registrado em**: `monitor.py` — `_load_crawler('dom_sc')` module_map

## Lint

- flake8: OK (9 E501/E127 corrigidos)
- mypy: OK
- CodeRabbit: 0 findings

## Story

- File: `docs/stories/epics/epic-feat-001-crawlers-coverage/story-FEAT-1.1-adaptar-dom-sc-crawler.md`
- Status: InReview (10/10 ACs marcadas, self-critique salvo)
- Self-critique: `plan/self-critique-FEAT-1.1.json`
