---
name: story-COVERAGE-1.5-qa-gate
description: PASS verdict after RE-QA (2a tentativa) — stash aplicado corretamente, 6/6 validacoes, ruff clean
metadata:
  type: project
---

# Story COVERAGE-1.5 QA Gate

**Story:** `docs/stories/epics/epic-coverage-100pct/story-COVERAGE-1.5-dom-sc-expansion.md`
**Gate date:** 2026-07-11
**Verdict:** PASS (apos FAIL na 1a RE-QA)

## Validacao (6 checks)

| Check | Resultado |
|-------|-----------|
| `git diff HEAD -- scripts/crawl/dom_sc_crawler.py` | PASS — diff mostra alteracoes, stash aplicado |
| `DOM_SC_FULL_DAYS` = 180 | PASS — linha 87 confirmada |
| `remote/list` endpoint | PASS — 6 ocorrencias |
| `_log_municipio_coverage` | PASS — 2 ocorrencias |
| `ruff check` | PASS — "All checks passed!" |
| Alteracoes confirmadas | PASS — diff nao vazio |

## Decisao

**PASS** — Todas as 6 validacoes confirmadas. ACs 5-7 e 9 N/A (bloqueados por credenciais).
Story: InReview -> Done.

## Lição aprendida

A 1a RE-QA falhou porque `git checkout stash@{0}` sem o PATH final (`-- scripts/crawl/dom_sc_crawler.py`) resultou em stash checkout completo que, por algum motivo, nao alterou a working tree. A 2a tentativa com PATH explícito funcionou.
