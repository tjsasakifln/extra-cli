---
name: story-COVERAGE-3.1-qa-gate
description: FAIL verdict on story-COVERAGE-3.1 — SeleniumBatchCrawler class missing, monitor.py lacks selenium source support, 23/24 tests
metadata:
  type: project
---

# Story COVERAGE-3.1 QA Gate

**Verdict:** FAIL
**Date:** 2026-07-11

## AC Status
- AC1 (JS portal list): PASS — 66 portais
- AC2 (Smoke test): PARTIAL — arquivo existe mas import quebra
- AC3 (Batch crawl): FAIL — SeleniumBatchCrawler nao existe
- AC4 (Transform): PASS — 8/8 cenarios testados
- AC5 (Entity matching): PASS — cascade 3 niveis
- AC6 (Coverage report): PASS — report_coverage() existe
- AC7 (Failed portals doc): PASS — template criado
- AC8 (Playwright fallback): PASS — classe PlaywrightFallback
- AC9 (Regression tests): PARTIAL — 23/24 passam, 1 falha
- AC10 (Systemd timer): PARTIAL — arquivos existem, mas --source selenium invalido

## Critical Issues
1. **BUG-001 (HIGH):** `SeleniumBatchCrawler` nao existe em `selenium_crawler.py`. Adapter e smoke test importam classe inexistente. `crawl()` retorna `[]` silenciosamente.
2. **BUG-002 (HIGH):** `monitor.py` sem suporte a "selenium" — ausente de SOURCES, argparse choices, e module_map.
3. **BUG-003 (MEDIUM):** 1/24 testes falha (test_crawl_mocked_batch)
4. **MNT-001 (MEDIUM):** File List reporta 1207 linhas, real 782. Metodos batch nao existem.
5. **MNT-002 (LOW):** transparencia_config.yaml sem referencia COVERAGE-3.1

## Resolution Required
@dev precisa implementar `SeleniumBatchCrawler` em `selenium_crawler.py` OU refatorar adapter/smoke test para usar `SeleniumCrawler` existente. Tambem precisa registrar "selenium" em `monitor.py`.
