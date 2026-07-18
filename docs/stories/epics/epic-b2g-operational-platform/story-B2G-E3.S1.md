---
story_id: B2G-E3.S1
title: "Adapter contract + PNCP 429 fail-closed"
status: Done
priority: P0
risk_level: HIGH-RISK
effort: L
agent: "@dev"
epic: EPIC-B2G-OPERATIONAL-PLATFORM
vertical: E3
depends_on: []
blocks: [B2G-E3.S2, B2G-E3.S3]
adr: [ADR-021]
po_closed: true
qa_verdict: CONCERNS
---

# Story B2G-E3.S1: Adapter contract + PNCP 429 fail-closed

## Contexto

PNCP e outros adapters reportam sucesso parcial sob 429; dual content_hash; status semântico inconsistente. ADR-021 define fail-closed.

## Valor de negócio

Elimina falsos “success” que inflacionam coverage e corrompem briefings.

## Escopo

**IN:** Enum `FetchResult.status`; PNCP (e preferencialmente SC Compras/CIGA) emitindo status; 429→rate_limited; teste com mock 429; unificar content_hash canônico pós-normalize.

**OUT:** Reescrever todos os 14 crawlers; VPS provision.

## Acceptance Criteria

1. **Given** resposta HTTP 429, **When** adapter PNCP fetch, **Then** `status=rate_limited` e **não** grava evidence success da fatia.
2. **Given** pages_fetched < pages_expected, **When** finaliza, **Then** `status=partial` (não success).
3. **Given** 0 records com empty confirmado pela API, **When** finaliza, **Then** `empty_confirmed` permitido.
4. **Given** normalize, **When** hash, **Then** um contrato de hash documentado (sem dual silencioso).

## Fontes de dados

PNCP API (mocks em teste).

## Riscos

HIGH — muda semântica de jobs existentes; exigir feature flag se necessário.

## Testes

Unit mocks 429/partial/empty; contract tests adapter.

## DoD

- [x] AC1–4; pytest; nota ADR-021 no módulo

## Comandos de validação

```bash
pytest tests/ -k "pncp and (429 or rate_limit or fail_closed or FetchResult)" -v
```

## Change Log

| Data | Autor | Nota |
|------|-------|------|
| 2026-07-17 | Morgan (PM) | Draft |
| 2026-07-17 | Dex (Dev) | Contrato canônico nos três adapters prioritários, fail-closed, raw/hash/evidence e testes; Draft → InReview. |
| 2026-07-17 | Quinn (QA) | Independent review → **CONCERNS**. AC1–4 PASS focused (24). Residual chaos fixture drift non-blocking. Status stays InReview (PO close). |
| 2026-07-17 | Pax (@po) | **PO close** — accepted QA CONCERNS. Status InReview → **Done**. po_closed=true. ACs met (focused 24). No LOCAL_RESILIENCE_READY / PRE_VPS_FINAL_READY claim. Follow-up: chaos ResilienceConfig fixture debt → @dev. [closure-key: B2G-E3.S1:commit:a12190c8fca1af0c564de682d1dbc0f9d755e116] |

## Dev Agent Record

- Implementação: `scripts/crawl/ingestion/_base/crawler.py`, `scripts/crawl/resilience/`, `scripts/crawl/monitor.py`.
- Testes: `tests/test_fetch_result.py`, `tests/test_local_resilience.py`, `tests/test_crawler_pncp.py`.
- Limite: validação local; nenhuma VPS ou cobertura de 95% declarada.

## QA Results

**Reviewer:** Quinn (@qa / adversarial-qa-auditor)  
**Independent:** true (≠ implementer delivery-engineer)  
**Date:** 2026-07-17  
**Verdict:** **CONCERNS**  
**Reviewed commit:** `a12190c` (product base `origin/main@4da296e`)  
**Gate file:** `squads/extra-dod-roi/state/qa/B2G-E3.S1-qa.json`

### AC traceability

| AC | Result | Evidence |
|----|--------|----------|
| AC1 429 → rate_limited | PASS | FetchResult fail-closed + focused local_resilience/pncp |
| AC2 pages_fetched < expected → partial | PASS | FetchResult.__post_init__ + test_partial_pagination |
| AC3 empty_confirmed guard | PASS | test_fetch_result (7) + empty_confirmed ValueError |
| AC4 hash contract canônico | PASS | pipeline sha256_json / adapters content_hash + ADR-021 |

### Tests (QA re-run)

- Focused: **24 passed** (`test_fetch_result` + `test_crawler_pncp` + `test_local_resilience` filter)
- Residual: chaos `test_429_rate_limit` TypeError `ResilienceConfig` fixture drift — **non-blocking** (fora do AC suite focado)

### DoD notes (QA)

- [x] AC1–4 verificados independentemente
- [x] pytest focado verde
- [x] Nota ADR-021 no módulo
- [x] Status Done — **fechado por @po** (2026-07-17) após CONCERNS aceitável
- [x] Sem inflação de `LOCAL_RESILIENCE_READY` / `PRE_VPS_FINAL_READY`

### Residual (não bloqueia PO close)

Corrigir `_cfg` em `tests/chaos/test_429_rate_limit.py` para campos obrigatórios de `ResilienceConfig` (follow-up debt).

### PO Close Acknowledgement

**PO:** Pax (@po)  
**Date:** 2026-07-17  
**Accepted verdict:** CONCERNS (independent Quinn)  
**Decision:** Close as Done — product ACs satisfied; residual is test fixture debt only.  
**Forbidden claims confirmed NOT made:** LOCAL_RESILIENCE_READY, PRE_VPS_FINAL_READY.  
**Follow-up registered:** `FU-E3-CHAOS-RESILIENCECONFIG` → owner @dev — fix chaos `_cfg` to pass required `ResilienceConfig` fields (`environment`, `execution_mode`, `state_root`, `breaker_path`) or use `for_tests`/`from_env`.
