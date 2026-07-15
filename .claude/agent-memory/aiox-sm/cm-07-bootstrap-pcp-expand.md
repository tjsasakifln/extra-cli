---
name: cm-07-bootstrap-pcp-expand
description: Story CM-07 criada — bootstrap DB local, correcao SOURCE_BLOCKERS PCP, expansao PCP 365 dias
metadata:
  type: project
---

**Story ID:** CM-07
**Titulo:** Bootstrap Local DB e Expansao de Cobertura PCP
**Epic:** EPIC-COVERAGE-MAX-200KM (Onda 2)
**Status:** Draft
**Criada:** 2026-07-15
**Path:** `docs/stories/CM-07-bootstrap-pcp-expand.md`

### Escopo
- Migrations ao banco `pncp_datalake`
- Corrigir `bootstrap_local.sh`: `python` → `python3`, path `scripts/db/` → `db/seed/`
- Remover entrada `'pcp'` do `SOURCE_BLOCKERS` em `coverage_truth.py` (linha 48)
- Expandir PCP crawl de 30 para 365 dias
- Executar PCP crawl completo e medir metricas

**Why:** DB local estava offline (container tmpfs), PCP classificado como blocked incorretamente (API e aberta), janela de 30 dias subotima.

**How to apply:** Esta story habilita o golden path de ingestao — e prerequisito para stories que dependem de banco local e metricas de cobertura precisas.
