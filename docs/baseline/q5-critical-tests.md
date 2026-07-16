# Q5.1 — Testes do caminho crítico (fechamento)

**Date:** 2026-07-16  
**Last run:** 2026-07-16 (suíte expandida)

## Suite mandatória (paths da missão)

```bash
pytest tests/test_ciga_ckan_transform.py \
       tests/test_golden_path_ledger.py \
       tests/test_dlq_sync.py \
       tests/test_watermark_sync.py \
       tests/test_freshness.py \
       tests/test_ciga_ckan_crawler.py \
       -q --tb=line --no-cov
```

| Módulo | Coletados | Resultado |
|--------|-----------|-----------|
| CIGA transform/registry (`test_ciga_ckan_transform.py`) | 8 | 8 PASS |
| golden_path ledger (`test_golden_path_ledger.py`) | 5 | 5 PASS |
| DLQ (`test_dlq_sync.py`) | 3 | 3 PASS |
| Watermark (`test_watermark_sync.py`) | 2 | 2 PASS |
| Freshness (`test_freshness.py`) | 3 | 3 PASS |
| CIGA CKAN crawler (`test_ciga_ckan_crawler.py`) | 61 | 61 PASS |
| **Total** | **82** | **82 PASS / 0 FAIL** |

### Resultado da execução

```
collected 82 items
============================== 82 passed in 4.27s ==============================
```

- **PASS:** 82  
- **FAIL:** 0  
- **SKIP / XFAIL / ERROR:** 0  
- **Exit code:** 0  
- **Ambiente:** Linux, Python 3.12.3, pytest 8.4.1  

`test_ciga_ckan_crawler.py` **não** falhou por ambiente; todos os 61 testes passaram sem necessidade de credenciais externas ou rede.

## Lint (caminho crítico)

```bash
ruff check scripts/crawl/monitor.py scripts/golden_path.py scripts/crawl/ciga_ckan_crawler.py
```

| Alvo | Resultado |
|------|-----------|
| `scripts/crawl/monitor.py` | All checks passed |
| `scripts/golden_path.py` | All checks passed |
| `scripts/crawl/ciga_ckan_crawler.py` | All checks passed |

## Escopo

- Caminho crítico de fundação de dados (DLQ, watermark, freshness, CIGA transform, CIGA crawler, ledger)
- Falhas residuais da monorepo fora desses paths **não** bloqueiam Q5.1 da janela 30d

## Histórico resumido

| Data | Suite | Total | Resultado |
|------|-------|-------|-----------|
| 2026-07-16 (inicial) | 5 módulos (sem crawler) | 21 | 21 PASS |
| 2026-07-16 (expandida) | 6 módulos (+ `test_ciga_ckan_crawler.py`) | 82 | 82 PASS |

**Status:** DONE
