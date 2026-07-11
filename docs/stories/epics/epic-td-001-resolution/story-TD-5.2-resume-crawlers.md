# Story TD-5.2: Sistema de Resume para Crawlers

**Status:** Done
**Epic:** EPIC-TD-001
**Executor:** @dev
**Quality Gate:** @architect
**Quality Gate Tools:** [coderabbit, pytest]
**Fase:** 5 -- Resiliencia & Observabilidade
**Estimativa:** 1 hora
**Prioridade:** P3

## Description

A tabela `ingestion_checkpoints` existe no schema mas tem 0 registros, indicando que os crawlers nao estao utilizando checkpoints para retomada de crawl. Para 2.085 orgaos publicos, uma falha no meio do ciclo pode significar perda de progresso e retrabalho.

Decidir: integrar a tabela nos crawlers como mecanismo de resume, ou remover a tabela se for conclusao que o design atual (crawls por orgao individual) torna checkpoints desnecessarios.

## Business Value

Crawlers sem resume para 2.085 orgaos publicos significa que falhas no meio de ciclos de crawl causam perda de progresso e retrabalho, impactando diretamente a cobertura e a atualidade dos dados de licitacoes. A decisao correta (implementar ou remover) elimina complexidade desnecessaria ou preenche uma lacuna de resiliencia.

## Acceptance Criteria

- [x] AC1: Dado o fluxo de crawl atual, Quando analisado o comportamento em caso de falha no meio de um ciclo, Entao a necessidade de resume esta documentada com justificativa tecnica
- [x] AC2: Dado que a decisao for implementar resume, Quando a tabela `ingestion_checkpoints` for integrada, Entao checkpoints sao escritos durante o crawl e lidos na retomada
- [x] AC3: Dado que a decisao for NAO implementar resume, Quando confirmado que crawls sao por orgao individual, Entao a tabela `ingestion_checkpoints` e removida ou documentada como NAO-UTILIZADA (N/A — decisao foi implementar)
- [x] AC4: Dado o documento de decisao criado, Quando revisado por um segundo desenvolvedor, Entao a justificativa tecnica e clara e a decisao e consistente com a arquitetura do sistema

## Scope

### IN
- Analise de necessidade de resume
- Implementacao de checkpoints OU remocao da tabela
- Documentacao da decisao

### OUT
- Implementacao de resume para crawlers especificos (apenas mecanismo generico)

## Dependencies

- Bloqueado por: NONE
- Bloqueia: NONE

## Risks

| Risco | Probabilidade | Impacto | Mitigacao |
|-------|---------------|---------|-----------|
| Decisao erronea de que resume e desnecessario | BAIXA | MEDIO | Validar com arquiteto antes de remover tabela; documentar razao |
| Complexidade adicional se implementado sem real necessidade | MEDIA | BAIXO | 1h de estimativa limita complexidade; keep it simple |
| Tabela removida e depois necessaria | BAIXA | ALTO | Manter migration de rollback; backup da DDL |

## Technical Notes

Referencia ao assessment: TD-DB-10 (MEDIUM) -- ingestion_checkpoints sem uso -- 1h
- Decisao do arquiteto: crawlers nao resumeveis para 2.085 orgaos = perda de eficiencia operacional real
- Se cada orgao e um crawl independente, checkpoints podem ser desnecessarios
- Se o crawl e batch-based, checkpoints sao essenciais

## Definition of Done

- [x] Decisao tomada e documentada
- [x] Implementacao ou remocao executada
- [ ] Teste de resume (se implementado) — requer ambiente com banco para validar upsert

## File List

- `scripts/crawl/checkpoint.py` (reescrito) — modulo de checkpoint compatível com schema real (migration 004)
- `scripts/crawl/orchestrator.py` (modificado) — integracao de checkpoints no crawl_source()
- `docs/td-001/resume-checkpoints.md` (novo) — documentacao da decisao e design
- `plan/self-critique-TD-5.2.json` (novo) — self-critique report

## Change Log

| Data | Mudanca | Autor |
|------|---------|-------|
| 2026-07-11 | Story criada | @pm |
| 2026-07-11 | Validated GO (10/10) — adicionado Business Value, Risks, Executor, QG, Prioridade; ACs convertidas para Given/When/Then | @po |
| 2026-07-11 | Development started (YOLO mode) — Status: Ready → InProgress | @dev |
| 2026-07-11 | Development complete — Status: InProgress → InReview | @dev |
| 2026-07-11 | QA Gate FAIL — Status: InReview → InProgress — Runtime errors: missing function is_crawl_completed_today, save_checkpoint signature mismatch | @qa |
| 2026-07-11 | QA fixes applied — BUG-001, BUG-002, DOC-001, TEST-001 — Status: InProgress → InReview | @dev |
| 2026-07-11 | 1.0.1 | QA Gate PASS — Status: InReview → Done | @qa |

## QA Results

### Review Date: 2026-07-11

### Reviewed By: Quinn (Guardian)

### Verdict: FAIL

The implementation has critical runtime errors that make the code non-functional:

1. **Missing function `is_crawl_completed_today`** (HIGH): The orchestrator imports and calls `is_crawl_completed_today(conn, source)` from `checkpoint.py`, but this function is not defined anywhere in the codebase. `checkpoint.py` only defines `get_last_checkpoint`, `save_checkpoint` (async), `mark_checkpoint_failed`, `create_ingestion_run`, and `complete_ingestion_run`. This will raise `ImportError` at module load time.

2. **`save_checkpoint` signature mismatch** (HIGH): The orchestrator calls `save_checkpoint(conn, source, last_date=date.today(), records_fetched=0)` synchronously with a psycopg2 connection object, but `checkpoint.py` defines `async def save_checkpoint(uf, modalidade, last_date, records_fetched, crawl_batch_id, source)` using the Supabase async client. The parameters are completely incompatible — `conn` vs `uf`, `source` vs `modalidade`, and the required `crawl_batch_id` is missing. Would raise `TypeError` at runtime.

3. **Documentation contradicts implementation** (MEDIUM): `docs/td-001/resume-checkpoints.md` describes a psycopg2-based API (`get_checkpoint(conn, source, scope_key)`, `delete_checkpoint(conn, source, scope_key)`, `is_crawl_completed_today(conn, source, scope_key)`) that does not match the actual `checkpoint.py` implementation, which uses async Supabase-based functions with different names and signatures.

4. **No tests pass** (MEDIUM): Test suite has 2 collection errors. No tests exist for `checkpoint.py` or the checkpoint integration in `orchestrator.py`.

### QC Results

| Check | Result | Detail |
|-------|--------|--------|
| Code Review | FAIL | Missing function import, signature mismatch, doc/code divergence |
| Unit Tests | FAIL | 0 tests for checkpoint module, existing tests fail to collect |
| Acceptance Criteria | FAIL | AC2 not met — checkpoints cannot be written or read due to runtime errors |
| No Regressions | N/A | orchestrator.py is a new file; no existing functionality affected |
| Performance | PASS | Checkpoints are lightweight upserts |
| Security | PASS | No security issues identified |
| Documentation | FAIL | Documents describe API that does not match implementation |

### AC Verification

| AC | Result | Evidence |
|----|--------|----------|
| AC1 | PASS | Decision document (`docs/td-001/resume-checkpoints.md`) thoroughly analyzes crawl architecture and justifies checkpoint need |
| AC2 | FAIL | orchestrator.py calls non-existent `is_crawl_completed_today()` and incompatible `save_checkpoint()` — would crash at runtime |
| AC3 | N/A | Decision was to implement, not remove |
| AC4 | PASS | Decision document is clear, well-structured, and consistent with batch-based architecture analysis |

### Root Cause

The `checkpoint.py` module was previously committed (in the initial platform commit) with an async Supabase-based design used by `bids_crawler.py`. The new `orchestrator.py` was written assuming a synchronous psycopg2-based interface that does not exist. Neither the self-critique nor the DoD report detected this interface mismatch.

### Required Fixes

1. Implement `is_crawl_completed_today(conn, source, scope_key="default")` in `checkpoint.py` using psycopg2, OR rewrite orchestrator.py to use existing async Supabase-based functions
2. Align `save_checkpoint` calls in orchestrator.py with the actual signature in checkpoint.py (async, correct parameters including `crawl_batch_id`)
3. Update documentation to match the actual implementation API
4. Add unit tests for checkpoint functions

### Gate Status (Previous — FAIL)

Gate: FAIL → `docs/qa/gates/td-5.2-resume-crawlers.yml`

---

### Re-review: 2026-07-11

### Reviewed By: Quinn (Guardian)

### Verdict: PASS

All 4 issues from the previous FAIL are resolved:

1. **BUG-001 (HIGH)** — RESOLVED: `is_crawl_completed_today(conn, source, scope_key="default")` implemented in `checkpoint.py` (lines 39-73) with psycopg2 synchronous API.
2. **BUG-002 (HIGH)** — RESOLVED: `save_checkpoint(conn, source, scope_key="default", last_date=None, records_fetched=0)` implemented in `checkpoint.py` (lines 76-126) with matching signature.
3. **DOC-001 (MEDIUM)** — RESOLVED: `docs/td-001/resume-checkpoints.md` now clearly documents both sync psycopg2 API and async Supabase API, accurately reflecting the dual design.
4. **TEST-001 (MEDIUM)** — RESOLVED: `tests/test_checkpoint.py` contains 15 unit tests covering all 4 sync functions (happy path, defaults, error handling), all passing.

### QC Results

| Check | Result | Detail |
|-------|--------|--------|
| Code Review | PASS | All imports verified; signatures match between orchestrator and checkpoint; parameterized SQL; consistent error handling |
| Unit Tests | PASS | 15/15 checkpoint tests pass (all 4 sync functions tested: is_crawl_completed_today, save_checkpoint, get_checkpoint, delete_checkpoint) |
| Acceptance Criteria | PASS | AC1 (decision doc): PASS. AC2 (checkpoints implemented): PASS. AC3: N/A. AC4 (document clear): PASS |
| No Regressions | PASS | Checkpoint calls are additive; pre-existing orchestrator flow unchanged; 34 pre-existing failures in unrelated test files |
| Performance | PASS | Lightweight upsert operations; single query per checkpoint |
| Security | PASS | Parameterized SQL prevents injection; no credentials exposed |
| Documentation | PASS | Decision doc, module docstring, and code comments all consistent and accurate |

### Issues Observed

| ID | Severity | Finding | Suggested Action |
|----|----------|---------|-----------------|
| MNT-001 | low | Top-level `from supabase_client import get_supabase, sb_execute` in checkpoint.py line 25 couples sync and async APIs. If `supabase_client` is unavailable, the entire module (including sync functions) fails to load. | Consider deferring the Supabase import inside async-only functions to isolate the sync API dependency. |

### Gate Status

Gate: PASS → `docs/qa/gates/td-5.2-resume-crawlers.yml`
