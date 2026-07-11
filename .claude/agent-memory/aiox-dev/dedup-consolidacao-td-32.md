---
name: dedup-consolidacao-td-32
description: Consolidacao de codigo duplicado entre crawlers Python (Story TD-3.2) - common.py, DSN unificado, upsert documentado
metadata:
  type: project
---

Consolidacao concluida em 2026-07-11 para a Extra Consultoria (projeto Python de crawling de licitacoes).

**scripts/crawl/common.py** — modulo compartilhado com `digits_only`, `parse_date`, `safe_float`, `safe_date`, `extract_cnpj`, `trunc`, `generate_content_hash`. Sete crawlers atualizados para usar estas funcoes em vez de definicoes locais.

**TD-SYS-016 (crawlers PNCP):** `bids_crawler.py` (async, dead code) marcado como DEPRECATED com rollback plan. `pncp_crawler_adapter.py` (sync) mantido como unica implementacao.

**TD-SYS-002 (DSN):** `config/settings.py` agora exporta `DEFAULT_DSN`. `monitor.py` e `orchestrator.py` importam de settings.

**TD-DB-16 (upsert):** SQL function `upsert_pncp_supplier_contracts` ja era set-based. Documentado.

191 testes passando (0 falhas, 0 regressoes).

**Why:** Eliminar duplicacao reduz risco de divergencia entre crawlers.
**How to apply:** Crawlers novos devem usar `scripts.crawl.common` em vez de definir proprias funcoes.
