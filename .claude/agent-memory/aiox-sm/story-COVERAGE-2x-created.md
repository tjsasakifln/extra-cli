---
name: story-COVERAGE-2x-created
description: "4 stories da Fase 2 do EPIC-COVERAGE-100PCT criadas: MiDES BigQuery, SC Compras, DOE-SC, Entity Coverage Rebuild"
metadata:
  type: project
---

# COVERAGE-2.x Stories Criadas (2026-07-11)

Criadas 4 stories detalhadas da Fase 2 do EPIC-COVERAGE-100PCT em `docs/stories/epics/epic-coverage-100pct/`:

1. **COVERAGE-2.1** — MiDES BigQuery Integration (P0/PULAR, 8h, @data-engineer)
2. **COVERAGE-2.2** — SC Compras Crawler Activation (P1, 5h, @dev)
3. **COVERAGE-2.3** — DOE-SC Crawler Activation (P1, 5h, @dev)
4. **COVERAGE-2.4** — Entity Coverage Rebuild (P1, 2h, @dev + @data-engineer)

**Dados reais do banco utilizados:** 2.085 entes, 972 cobertos (46.6%), 1.113 descobertos
**Crawlers existentes referenciados:** sc_compras_crawler.py (636L), doe_sc_crawler.py (772L), compras_gov_crawler.py (596L)
**INDEX.md atualizado** com as 4 novas stories

**ACs totais:** 66 (media de 16.5/story)
**Riscos documentados:** 20 (media de 5/story)
**Codigo exemplos:** snippets Python + SQL em todas as stories
