---
name: story-td-8-2-validation
description: Validacao PO da story TD-8.2 Fix Broken Module Imports — GO 10/10, concern AC13 (falso positivo cli_validation.py)
metadata:
  type: project
---

Story TD-8.2 foi validada como **GO 10/10** em 2026-07-11. Status atualizado de Draft para Ready.

**Escopo:** Criacao de stubs para clients/, ingestion/, supabase_client, exceptions, middleware, rate_limiter, metrics, redis_pool, degradation + correcao de import paths em intel-enrich.py + pip packages + verificacao automatizada (check_imports.py). 16h estimada, 18 ACs, todos testaveis.

**Concern documentado:** AC13 instrui correcao de import em `scripts/lib/cli_validation.py` de `from constants` para `from config.constants`, mas o codigo real usa `from .constants import ...` (import relativo funcional) e `config/constants.py` contem constantes diferentes (crawler vs pipeline). Seguir AC13 quebraria o modulo. [AUTO-DECISION] manter import atual.

**Recomendacao ao @dev:** Ignorar AC13. O import relativo `.constants` em cli_validation.py funciona corretamente. Priorizar AC1-AC12 e AC14-AC18.

[[validation-process-po]]
