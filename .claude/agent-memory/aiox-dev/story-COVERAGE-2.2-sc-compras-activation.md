---
name: story-COVERAGE-2.2-sc-compras-activation
description: Story COVERAGE-2.2 implementada — diagnostic(), systemd, dry-run, 88 testes, bugfix _map_modalidade empty string
metadata:
  type: project
---

# Story COVERAGE-2.2: SC Compras Crawler Activation

Implementada em YOLO mode em 2026-07-11.

**O que foi feito:**
- `diagnostic()` function adicionada ao `sc_compras_crawler.py` — testa conectividade, detecta Cloudflare/anti-bot
- `_check_url()` helper — lightweight GET com timeout de 15s, le 8KB do body para deteccao de challenge
- `monitor.py` dry-run mode aprimorado — chama `crawler.diagnostic()` se disponivel
- Bugfix: `_map_modalidade()` com string vazia — `"" in key` retorna True em Python, causando match falso. Corrigido com `if normalized:` guard no fuzzy fallback.
- Systemd service/timer criados: `deploy/systemd/sc-compras-crawl.{service,timer}` (domingo 09:00 UTC)
- Documento de diagnostico: `docs/epic-coverage/sc-compras-diagnostic.md`
- 88 testes unitarios: `tests/test_sc_compras_crawler.py`

**Por que:** Ativar crawler existente que nunca foi validado em producao. Cobertura estimada: +50-100 entidades estaduais.

**Como aplicar:** ACs de runtime (AC0-AC2, AC4-AC5, AC7) requerem execucao em producao com PostgreSQL e acesso a rede. Para deploy: copiar systemd files, configurar .env com SC_COMPRAS_* vars, rodar `monitor.py --source sc-compras --mode dry-run` para diagnostico.
