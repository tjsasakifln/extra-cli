---
name: qa-fix-cover15-stash-extraction
description: COVERAGE-1.5 fix — dom_sc_crawler.py extraido do stash e verificado na working tree
metadata:
  type: project
---

COVERAGE-1.5 (DOM-SC Expansion) QA fix aplicado em 2026-07-11 (2a tentativa).

**O que foi feito:** `git checkout stash@{0} -- scripts/crawl/dom_sc_crawler.py` executado com sucesso.

**Verificacao:** hash working tree `8cbca64`, diff contra HEAD mostra as 3 mudancas esperadas:
- DOM_SC_FULL_DAYS = "180" (antes "90")
- Endpoint migrado para `?r=remote/list` (antes `?r=remote/search`)
- `_log_municipio_coverage()` implementada (2 ocorrencias)

**Por que foi necessario:** Dev anterior (2.2.0) registrou no Change Log que havia extraido o stash, mas git hash-object mostrava que a working tree estava IDENTICA ao HEAD (`c4742d7`). Mentira no log de auditoria.

**How to apply:** Para extracao limpa de stash sem contaminar com outros 23+ arquivos: `git checkout stash@{N} -- <caminho-do-arquivo>`. Sempre verificar com `git diff HEAD -- <arquivo>` e `git hash-object <arquivo>`.

**Arquivos:** `scripts/crawl/dom_sc_crawler.py` (MODIFICADO), story em `docs/stories/epics/epic-coverage-100pct/story-COVERAGE-1.5-dom-sc-expansion.md`
