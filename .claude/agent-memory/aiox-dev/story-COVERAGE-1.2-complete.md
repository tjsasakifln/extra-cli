---
name: story-cover1.2-ciga-ckan
description: COVERAGE-1.2 implementado — monitor.py integrado, 61 testes, lint clean, AC3-7 bloqueados por API real
metadata:
  type: project
---

Story COVERAGE-1.2 (CIGA CKAN Crawler) implementada em modo YOLO. Monitor.py alterado: SOURCES, argparse choices ("ciga-ckan"), module_map, conversao hifen->underline. Ciga_ckan_crawler.py lint fixes (unused imports, N806, E731, E402). Testes: 61/61 unitarios com mocks para CKAN API, ZIP, DB.

**Why:** Story pronta para execucao real contra CKAN API e PostgreSQL — testes mockados garantem logica correta sem acesso externo.
**How to apply:** Ao executar AC3-AC7, usar comando `python scripts/crawl/monitor.py --source ciga-ckan --mode full` no VPS. O argparse ja aceita "ciga-ckan" com conversao automatica para "ciga_ckan".
