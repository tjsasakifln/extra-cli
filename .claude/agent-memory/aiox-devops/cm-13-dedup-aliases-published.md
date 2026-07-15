---
name: cm-13-dedup-aliases-published
description: CM-13 pushes para epic-coverage-max-200km — entity aliases + cross-source dedup publicados
metadata:
  type: project
---

# CM-13: Deduplicacao Multicanal e Aliases de Compradores

**Status:** Publicado (pushed to origin/epic-coverage-max-200km)
**Data:** 2026-07-15
**Wave:** 2

**Commits:**
- `707db9c` chore: handoff CM-13 Wave 2 -- @devops push
- `58e5c88` chore: CM-13 governance -- reviewed_commit bb4cad0 + epic sync
- `bb4cad0` feat: CM-13 -- entity aliases + cross-source dedup + resolver integration

**Why:** Resolver matching CNPJ (280+ entes com recall 0% por secretaria publicar com CNPJ da prefeitura). Tabela entity_aliases com 459 aliases + hash cross-source deterministico + DedupEngine.

**QA:** CONCERNS (2 HIGH resolvidos, 3 MEDIUM follow-ups registrados para CM-14 e backlog).

**How to apply:** Branch epic-coverage-max-200km contem CM-13 + baseline EPIC-COVERAGE-MAX-200KM. Proximos passos: CM-06 (Ready, score 95).
