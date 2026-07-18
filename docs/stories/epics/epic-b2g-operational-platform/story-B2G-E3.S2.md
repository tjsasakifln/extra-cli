---
story_id: B2G-E3.S2
title: "Checkpoint/resume unificado + DLQ smoke"
status: Done
priority: P0
risk_level: STANDARD
effort: M
agent: "@dev"
epic: EPIC-B2G-OPERATIONAL-PLATFORM
vertical: E3
depends_on: [B2G-E3.S1]
blocks: [B2G-E3.S3]
adr: [ADR-021, ADR-020]
po_closed: true
qa_verdict: CONCERNS
---

# Story B2G-E3.S2: Checkpoint/resume unificado + DLQ smoke

## Contexto

Checkpoints por fonte heterogêneos; resume nem sempre testado; falhas sem DLQ clara.

## Acceptance Criteria

1. **Given** job interrompido após N páginas, **When** resume, **Then** não reprocessa fatias success já checkpointadas.
2. **Given** rate_limited, **When** resume posterior, **Then** retoma fatia pendente.
3. **Given** registro poison, **When** DLQ, **Then** job principal não trava indefinidamente; smoke test documentado.

## DoD

- [x] Smoke resume documentado; testes unitários checkpoint

## Comandos de validação

```bash
pytest tests/ -k "checkpoint or resume or dlq" -v
```

## Change Log

| Data | Autor | Nota |
|------|-------|------|
| 2026-07-17 | Morgan (PM) | Draft |
| 2026-07-17 | Dex (Dev) | Checkpoint canônico atômico, resume idempotente, watermark fail-closed e DLQ com replay/smoke; Draft → InReview. |
| 2026-07-17 | Quinn (QA) | Independent review → **CONCERNS**. AC1–3 PASS focused (49). Residual chaos+DB noise non-blocking. Status stays InReview (PO close). |
| 2026-07-17 | Pax (@po) | **PO close** — accepted QA CONCERNS. Status InReview → **Done**. po_closed=true. ACs met (focused 49). No LOCAL_RESILIENCE_READY / PRE_VPS_FINAL_READY claim. Follow-ups: chaos fixture + opportunity DB exclusion. [closure-key: B2G-E3.S2:commit:a12190c8fca1af0c564de682d1dbc0f9d755e116] |

## Dev Agent Record

- Source of truth: `scripts/crawl/resilience/state.py`.
- Smoke/runbook: `make resilient-smoke` e `docs/operations/LOCAL-RESILIENCE-RUNBOOK.md`.
- Limite: DLQ local é filesystem; projeção PostgreSQL aditiva está na migration 054.

## QA Results

**Reviewer:** Quinn (@qa / adversarial-qa-auditor)  
**Independent:** true (≠ implementer delivery-engineer)  
**Date:** 2026-07-17  
**Verdict:** **CONCERNS**  
**Reviewed commit:** `a12190c` (product base `origin/main@4da296e`)  
**Gate file:** `squads/extra-dod-roi/state/qa/B2G-E3.S2-qa.json`

### AC traceability

| AC | Result | Evidence |
|----|--------|----------|
| AC1 resume não reprocessa success checkpointado | PASS | test_checkpoint + local_resilience resume |
| AC2 rate_limited resume retoma pendente | PASS | local_resilience + pipeline_fault |
| AC3 poison → DLQ sem travar job; smoke doc | PASS | test_dlq/dlq_sync + LOCAL-RESILIENCE-RUNBOOK |

### Tests (QA re-run)

- Focused: **49 passed** (checkpoint/dlq/local_resilience/pipeline_fault)
- Residual broad `-k`: chaos fixture drift + opportunity DB tables — **non-blocking** / fora da política no-DATABASE deste pack

### DoD notes (QA)

- [x] Smoke resume documentado; testes unitários checkpoint
- [x] AC1–3 verificados independentemente
- [x] Status Done — **fechado por @po** (2026-07-17) após CONCERNS aceitável
- [x] Sem inflação de selos READY operacionais

### Residual (não bloqueia PO close)

Broad suite noise (chaos `_cfg` + opportunity integration DB). Follow-up debt; não quebra AC.

### PO Close Acknowledgement

**PO:** Pax (@po)  
**Date:** 2026-07-17  
**Accepted verdict:** CONCERNS (independent Quinn)  
**Decision:** Close as Done — product ACs satisfied; residual is test/integration noise only.  
**Forbidden claims confirmed NOT made:** LOCAL_RESILIENCE_READY, PRE_VPS_FINAL_READY.  
**Follow-ups registered:**
1. `FU-E3-CHAOS-RESILIENCECONFIG` → owner @dev — fix chaos `_cfg` ResilienceConfig required fields.
2. `FU-E3-OPPORTUNITY-DB-MARK` → owner @dev — mark/exclude `tests/test_opportunity_integration.py` from default no-DB `-k` smoke (requires_db).
