# PRE-VPS Final Adversarial Audit

**Date:** 2026-07-17  
**Branch:** `fix/pre-vps-final-truth-gate-20260717`  
**Hypothesis under attack:** `LOCAL_RESILIENCE_READY`  
**Method:** every claim below cites current code paths; no recycled narrative.

---

## Executive verdict

### Baseline (pre-fix)

```text
NOT_READY
```

`LOCAL_RESILIENCE_READY` was a **false green**. The resilient path was a parallel collector ending in filesystem JSON.

### Post-fix (this branch)

Implementation on `fix/pre-vps-final-truth-gate-20260717` addresses the P0 split-brain and honesty gaps:

| Gate | Result |
|------|--------|
| Unit/chaos resilience tests | 48 passed offline |
| Fixture cycle | `TEST_HEALTHY` (never operational `healthy`) |
| Live health without live evidence | exit 2 `no_live_evidence` |
| CI job `resilience-gate` | added (fail-closed) |
| Live canary with PostgreSQL | **not executed in this session** (no `DATABASE_URL`) |

```text
NOT_READY
```

Reason residual: live canary + real PostgreSQL vertical slice against production-shaped DSN not proven in this environment. Offline truth gates pass. Seal `LOCAL_RESILIENCE_READY` is **destroyed**. Do not claim `PRE_VPS_FINAL_READY` until live canary + DB evidence exist.

---

## F1 — Split brain: resilient path never writes PostgreSQL (P0)

| Field | Detail |
|-------|--------|
| **Symptom** | `resilient_cycle` reports `records_persisted` and `status=healthy` without any DB row |
| **Root cause** | Cycle stops at canonical JSON + FS evidence/watermark |
| **Business risk** | Scheduler using `extra-crawl-*.service` would look green while datalake/opportunities freeze |
| **File** | `scripts/ops/resilient_cycle.py:107-135` |
| **Evidence** | Pipeline: `fetch → normalize → _atomic(canonical JSON) → ledger.write → watermark`. Zero `psycopg` / upsert |
| **Contrast** | `scripts/crawl/monitor.py:841-901` does upsert → entity match → opportunities → coverage_evidence |

---

## F2 — Dual systemd runtimes (P0)

| Unit family | Entry point | Persistence |
|-------------|-------------|-------------|
| `extra-crawl-pncp.service` | `python -m scripts.ops.resilient_cycle --live --source pncp` | Filesystem only |
| `pncp-crawl-inc.service` | `monitor.py --source pncp` | PostgreSQL |

Enabling the “new official” units without DB projection produces operational silence with green health.

---

## F3 — Fixture masquerades as operational healthy (P0)

| Field | Detail |
|-------|--------|
| **Symptom** | `test_controlled_cycle_is_idempotent_and_health_is_single_command` asserts `health_code == 0` and `status == "healthy"` after fixtures |
| **Root cause** | `health.py` reads `latest.json` without filtering `mode` / environment |
| **Business risk** | Operators and CI confuse mechanics green with live operational green |
| **Files** | `scripts/ops/health.py:24-55`, `tests/test_local_resilience.py:244-258` |
| **Evidence** | Cycle sets `mode=controlled_fixture` and claim `resilience mechanics only`, but health ignores both |

---

## F4 — Freshness semantics are wrong (P0)

| Field | Detail |
|-------|--------|
| **Symptom** | Single `freshness` field; SLA hardcoded `pncp: 24` while registry has `4` |
| **Root cause** | `sla_hours = {"pncp": 24, ...}` in health; uses attempt time, not content max timestamp |
| **Business risk** | Stale content after a recent fetch is reported current; PNCP 4h SLA violated |
| **Files** | `scripts/ops/health.py:24-44`, `scripts/crawl/registry.py` (`pncp.freshness_sla_hours=4`) |
| **Also** | `last_success` is set to `attempted_at` only when satisfactory — failed runs overwrite context without preserving last real success history |

---

## F5 — Checkpoint schema silently ignored (P0)

| Field | Detail |
|-------|--------|
| **Symptom** | `except TypeError: pass` swallows invalid checkpoint dicts |
| **Root cause** | Ad-hoc `FetchResult.checkpoint` formats; PNCP sends `page_scopes` without CanonicalCheckpoint fields |
| **Business risk** | Resume/promotion fails silently; orphaned `raw_persisted` |
| **File** | `scripts/ops/resilient_cycle.py:119-126` |

---

## F6 — CIGA marks checkpoint success inside adapter (P0)

| Field | Detail |
|-------|--------|
| **Symptom** | `CigaDomAdapter.fetch` saves checkpoint with terminal status before DB/evidence |
| **Root cause** | Adapter-local `checkpoints.save(cp)` with `status=success` |
| **Business risk** | Resume treats unfinished operational work as complete |
| **File** | `scripts/crawl/resilience/adapters.py:291-292` |

---

## F7 — SC Compras virtual pages mix snapshot risk (P0)

| Field | Detail |
|-------|--------|
| **Symptom** | Bulk download re-fetched every run; virtual pages resume independently |
| **Root cause** | No immutable snapshot hash binding chunks of one bulk |
| **Business risk** | Silent mix of old page slices with a new bulk order/content |
| **File** | `scripts/crawl/resilience/adapters.py:312-402` |
| **Note** | Incomplete bulk fail-closed is correct (partial), but snapshot integrity is not |

---

## F8 — HTTP config dual families (P0)

| Field | Detail |
|-------|--------|
| **Symptom** | `RESILIENCE_*` declared central; PNCP fetcher still uses `PNCP_*` |
| **Root cause** | Adapter loop uses `ResilienceConfig`; real HTTP client uses separate env vars |
| **Business risk** | Tuning resilience env does not change real retries/timeouts (decorative config) |
| **Files** | `scripts/crawl/resilience/config.py`, `scripts/crawl/pncp_crawler_adapter.py` |

---

## F9 — Circuit breaker in-memory only (P0)

| Field | Detail |
|-------|--------|
| **Symptom** | New process after open breaker hits the network again |
| **Root cause** | `PNCPAdapter._consecutive_failures` / `_circuit_opened_at` on instance only |
| **File** | `scripts/crawl/resilience/adapters.py:88-100` |

---

## F10 — CI does not run resilience gate (P0)

| Field | Detail |
|-------|--------|
| **Symptom** | `make resilience-gate` exists locally; `.github/workflows/ci.yml` never calls it |
| **Business risk** | PR can merge with broken resume/fail-closed contracts |
| **File** | `.github/workflows/ci.yml` (no `resilience-gate` job; mypy scope excludes resilience/ops) |

---

## F11 — No recoverable multi-stage protocol (P0)

Missing explicit stages:

```text
raw_persisted → normalized → db_committed → evidence_committed → watermark_committed
```

Crash after JSON canonical write can still write satisfactory evidence (when transport complete) without DB commit. Watermark gates on evidence, not on DB.

---

## F12 — No environment isolation (P0)

All modes share `RESILIENCE_STATE_PATH` / `output/resilience` for latest, checkpoints, watermarks, budgets, breakers. Fixture pollution of live state is possible.

---

## What already works (preserve)

1. `FetchResult` fail-closed contract (HTTP failures never empty).
2. Partial pagination blocks coverage_satisfactory.
3. Atomic raw/checkpoint JSON with SHA-256 dedup; secrets stripped from headers.
4. Watermark refuses incomplete/unsatisfactory evidence.
5. SC incomplete bulk → partial (post adversarial fix).
6. CIGA zero ambiguous → partial.
7. Migration 054 CHECK for future DB evidence projection.
8. Makefile local `resilience-gate` skeleton.
9. Registry SLA for PNCP is correctly 4h (health ignores it).

---

## Required target architecture

```text
SourceAdapter.fetch
  → raw immutable (FS)
  → normalize pure
  → persist_canonical (PostgreSQL upsert)
  → reconcile / entity match
  → project business outputs (opportunities / acts when applicable)
  → evidence satisfactory (env+mode tagged)
  → complete checkpoint (state machine)
  → commit watermark
  → health (live-only by default)
```

Failure at any stage: no operational evidence, no checkpoint completion, no watermark advance, non-zero exit, resume from last confirmed stage.

---

## Fix plan (implementation order)

1. Env isolation (`RESILIENCE_ENV`) + artifact metadata.
2. Stage machine + run progress ledger.
3. Extract persistence services from monitor; wire into cycle.
4. Honest health + freshness matrix + registry SLA.
5. Checkpoint schema + remove TypeError swallow; CIGA/SC fixes.
6. SC snapshot strategy; persistent CB; HttpResiliencePolicy.
7. Tests: fixture≠live, freshness, resume, CB persistence, vertical PG slice.
8. CI `resilience-gate` job + Makefile `pre-vps-final-gate*`.

---

## Seal policy

If conflict arises between preserving `LOCAL_RESILIENCE_READY` and describing system truth: **destroy the seal**.

Post-implementation verdict will be only:

```text
PRE_VPS_FINAL_READY
```

or

```text
NOT_READY
```
