---
name: dedup-consolidacao-td-32
description: Consolidacao de codigo duplicado entre crawlers (Story TD-3.2) - common.py, DSN, upsert
metadata:
  type: project
---

Consolidacao de tres focos de duplicacao concluida em 2026-07-11:

**TD-SYS-016:** Dois crawlers PNCP consolidados. BidsCrawler (async, dead code) marcado como DEPRECATED com rollback plan. Sync adapter (pncp_crawler_adapter.py) mantido como unica implementacao funcional.

**TD-SYS-002:** DSN default unificado em `config/settings.py` como `DEFAULT_DSN`. `monitor.py` e `orchestrator.py` agora importam de settings -- nao redefinem localmente.

**TD-DB-16:** Upsert de contratos ja era set-based (SQL function). Documentado que row-by-row esta deprecated.

**scripts/crawl/common.py:** Criado com `digits_only`, `parse_date`, `safe_float`, `safe_date`, `extract_cnpj`, `trunc`, `generate_content_hash`. Todos os crawlers foram atualizados para usar estas funcoes.

**Why:** Eliminar codigo duplicado reduz risco de comportamento divergente e custo de manutencao.
**How to apply:** Crawlers novos devem usar `scripts.crawl.common` em vez de definir proprias funcoes helper.
