---
name: tce-sc-crawler-implemented
description: TCE-SC e-Sfinge crawler implemented via SCMWeb JSON API adapter (Story 001.2)
metadata:
  type: project
---

TCE-SC crawler (`tce_sc_crawler.py`) foi implementado usando SCMWeb JSON API como fonte primária, conforme descoberto na investigation Phase 0 (e-Sfinge original morreu — DNS não resolve). O crawler segue o padrão `crawl(mode)`/`transform(records)` dos demais crawlers (dom_sc, pcp) e foi integrado ao `monitor.py`.

**Por que SCMWeb em vez de e-Sfinge:** O e-Sfinge original (`e-sfinge.tce.sc.gov.br`) não resolve DNS. A API REST documentada no Confluence requer credenciais. SCMWeb JSON API (`scmweb.com.br`) está funcional sem autenticação.

**Arquivos criados:**
- `scripts/crawl/tce_sc_crawler.py` — 764 linhas, suporta coleta por data/ano/município
- `deploy/systemd/tce-sc-crawl.service` — systemd service
- `deploy/systemd/tce-sc-crawl.timer` — daily 05:30 UTC

**Arquivos modificados:**
- `scripts/crawl/monitor.py` — adicionado `tce_sc` ao module_map, SOURCES, e CLI choices
- `docs/prd/PRD-consultoria-extra.md` — status TCE-SC atualizado para ativo

**Checklist findings:** 8/10 ACs implementados. AC8 (teste com 3 municípios) requer acesso à API real e execução do monitor.py. Entity coverage trigger (DoD) requer execução contra o banco PostgreSQL.

**Configurações via env vars:** `TCE_SC_REQUEST_DELAY`, `TCE_SC_FULL_DAYS`, `TCE_SC_INCREMENTAL_DAYS`, `TCE_SC_MAX_RETRIES`, `TCE_SC_ENABLED`
