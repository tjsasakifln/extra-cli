---
name: ciga-ckan-pncp-overlap
description: "CIGA CKAN DOM-SC coverage: 152 entities, 30 exclusive. PNCP overlaps ~80%."
metadata:
  type: project
---

**CIGA CKAN Coverage Impact (Story COVERAGE-1.2) — 2026-07-11**

Full crawl of 54 months (2022-2026) do portal CIGA CKAN (DOM-SC) resultou em 152 entidades distintas cobertas, das quais apenas 30 sao exclusivas (nao cobertas por PNCP). As estimativas originais da story (200+ entidades, 100+ exclusivas) eram otimistas devido ao alto overlap com PNCP (~376 entidades).

**Resultados reais:**
- Total covered within 200km: 416/1093 (38.1%)
- CIGA CKAN entities: 152
- Exclusive to CIGA CKAN: 30
- Still uncovered: 677

**Why:** PNCP ja cobre 376 entidades (34.4%), a maioria das quais sao os mesmos orgaos publicos que publicam no DOM-SC. Entidades exclusivas do CIGA CKAN sao orgaos menores que nao aparecem no PNCP (secretarias municipais especificas, fundacoes culturais, institutos de previdencia, conselhos municipais).

**How to apply:** Para stories futuras de coverage em EPIC-COVERAGE-100PCT, estimativas de novas entidades exclusivas devem considerar o overlap com fontes existentes (especialmente PNCP). Uma nova fonte provavelmente adicionara 20-50 exclusivas, nao 100+.
