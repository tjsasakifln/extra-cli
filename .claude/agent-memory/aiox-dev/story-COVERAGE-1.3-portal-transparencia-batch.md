---
name: story-COVERAGE-1.3-portal-transparencia-batch
description: Portal Transparencia batch detect — 295 municipios SC. 64 Betha (JS SPA), 231 residuais. 5 novas plataformas adicionadas mas 0 deteccoes.
metadata:
  type: project
---

# COVERAGE-1.3 Portal Transparencia Batch Detect

**Batch detection completed 2026-07-11 for all 295 SC municipios.**

## Results
- **64 detected** (all Betha/atende.net, 21.7%)
- **231 not found** (78.3%)
- **0 erros**

## Critical Finding — JS Rendering
Todos os portais Betha (atende.net) sao SPAs JavaScript-renderizados. HTTP scraping com BeautifulSoup retorna body vazio (0 texto, 0 links, 0 tabelas). Template scraping via HTTP e inviavel.

**Impact:** AC3 (template scraping) e AC4 (entity matching) estao bloqueados ate COVERAGE-3.1 (Selenium).

## 5 New Platforms (Fiorilli, Iplan, IRI, Prima, Tecnospeed)
Adicionadas ao `_PLATFORM_TEMPLATES` e `config/transparencia_config.yaml` mas **0 deteccoes** para qualquer uma. Possiveis causas:
1. Nao utilizadas por municipios SC
2. URL patterns estimados incorretos
3. Portais atras de Cloudflare/WAF

## Residuals
231 municipios sem plataforma documentados em `data/transparencia_residual_municipios.json` para COVERAGE-3.2.

**Why:** Verificacao crucial para planejamento do epic: portal transparencia nao e fonte de dados confiavel via HTTP em SC. DOM-SC e PNCP continuam sendo fontes primarias.

**How to apply:** Ao planejar scraping de portais municipais, assumir JS rendering como requisito. Template scraping HTTP (BeautifulSoup) e inviavel para atende.net e provavelmente para outras plataformas de transparencia.
