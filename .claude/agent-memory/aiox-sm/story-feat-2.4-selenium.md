---
name: story-feat-2-4-selenium
description: "Story FEAT-2.4: Selenium crawler para portais JS-rendered — extensao do EPIC-FEAT-001"
metadata:
  type: reference
---

# Story FEAT-2.4: Selenium Crawler para Portais com JavaScript

**Path:** `docs/stories/epics/epic-feat-001-crawlers-coverage/story-FEAT-2.4-selenium-crawler-js-portals.md`

**Criada:** 2026-07-11 por River (SM)

**Contexto:** EPIC-FEAT-001 ja tinha FEAT-2.2 (Portal Transparencia crawler HTTP+BS4, Done). 
FEAT-2.4 adiciona browser automation (Selenium) para portais que exigem JavaScript.

**Por que separada da FEAT-2.2:** FEAT-2.2 cobre deteccao de plataforma + templates HTML.
FEAT-2.4 adiciona camada de renderizacao JS. Sao capacidades ortogonais.

**Estrutura:**
- `scripts/crawl/selenium_crawler.py` (NOVO) — classe base SeleniumCrawler
- `scripts/crawl/transparencia_crawler.py` (MOD) — modo selenium
- `config/transparencia_config.yaml` (MOD) — campo requires_js
- Reusa templates existentes (`parse_page()` apos renderizacao)

**Checklist:** 100% (23/23) na story-draft-checklist. Status: Draft, pronta para @po validar.

**Proximo passo:** @po `*validate-story-draft FEAT-2.4`
