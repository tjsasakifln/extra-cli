---
name: story-1.2-unify-schema-qa-gate
description: QA Gate CONCERNS verdict for Story 1.2 (Unify Schema) — schema unification, 7 migrations, canonical views, FK constraints, UNIQUE cnpj_8, set-based upsert
metadata:
  type: project
---

# Story 1.2 QA Gate — Unify Schema

**Verdict:** CONCERNS
**Status:** InReview -> Done
**Executor:** @data-engineer (Dex implementado como @dev via AIOX)
**Gate file:** `docs/qa/gates/story-1.2-unify-schema.yml`

## Summary

Core schema unification implementada: 7 migrations (030-036), 5 canonical views (`v_entities_canonical`, `v_open_opportunities_canonical`, `v_contracts_canonical`, `v_suppliers_canonical`, `v_value_observations_canonical`), FK constraints (DT-19, DT-20) como NOT VALID, UNIQUE `cnpj_8` (DT-06) com pre-check, upserts refatorados para set-based, baseline `db/current-schema.sql` com fingerprint SHA-256 verificado.

**Gates:**
- 14/14 tests passing (ruff clean)
- 0 suspicious SQL references (186 files scanned, 71 references)
- SHA-256 fingerprint verified (`b4ec407e30f8d1d25598972c3c0a22138d80dc42c7acbb641bc875cb7735b880`)
- `supabase/current-sql.sql` archivado em `supabase/archive/`

## Issues

| ID | Severity | Finding | Suggested Action |
|----|----------|---------|-----------------|
| **REQ-001** | medium | AC #10 (set-based <=30% row-by-row) only structurally verified — no performance benchmark | Criar benchmark test comparando timing dos 2 approachs |
| **DOC-001** | low | Views contract document tem drift da migration 030 real (`matched_bids`, `entity_cnpj_8`, `c.is_active`) | Sincronizar contract doc com implementacao |
| **TST-001** | low | AC #5/#6 (fresh install, upgrade) testados estruturalmente, nao com execucao real em DB | Adicionar teste CI com postgres:16-alpine |
| **TST-002** | low | AC #9 (concurrency metrics queries) nao testado explicitamente | Adicionar smoke test que executa metricas via canonical views |

## Security Observations

- `fn_purge_old_data` usa whitelist + `format()` com `%I` — SQL injection mitigado
- FKs usam NOT VALID + VALIDATE diferido — minimiza lock em producao
- Trigger de versionamento criado DISABLED — evita overhead desnecessario
- Bandit rule "S" adicionada ao ruff lint no `pyproject.toml`
- RLS nao implementado (fora de escopo — schema e operacional/local)
- `output/schema/schema-gap-report.json` nao foi gerado (apenas `.md`)

## Key Strengths

- Migrations 030-036 consistentes (BEGIN/COMMIT, idempotente, LOCK_TIMEOUT, rollback documentado)
- Views canonicas com COMMENT em todas as colunas
- Contract document com regras de evolucao (ADD=default NULL, REMOVE=proibido, RENAME=proibido)
- Zero regressoes confirmado pelo audit de 186 arquivos
