# MISSÃO DATA-FOUNDATION AIOX -- Spec

**Version:** 1.0
**Date:** 2026-07-16
**Author:** Bob (Strategist) / PM Agent
**Classification:** COMPLEX (score 23/25)
**Status:** Draft

---

## Table of Contents

1. Problem Statement
2. Functional Requirements (FRs)
3. Non-Functional Requirements (NFRs)
4. Constraints
5. Architecture Overview
6. Source Mapping
7. Data Layer Design
8. Operations Model
9. Quality Gates
10. Risks & Mitigations

---

## 1. Problem Statement

The Extra Consultoria B2G intelligence platform ingests public procurement data from 11 crawler sources across federal, estadual, and municipal spheres. The existing codebase has:

- **No Dead Letter Queue**: Pipeline failures result in silent data loss. Failed records are discarded with no replay mechanism.
- **Stub Proliferation**: 6 modules (metrics, redis_pool, supabase_client, clients/base, clients/pncp) are empty stubs -- production monitoring, connection pooling, and client abstractions do not exist.
- **No Provenance Tracking**: Records carry no lineage metadata -- cannot trace a bid back to which crawl run, at what time, with which parameters produced it.
- **No Fine-Grained Watermarks**: Checkpoints are date-based only. Mid-crawl failures restart from the beginning.
- **No Kill/Resume Semantics**: Long-running crawls cannot be safely interrupted and resumed.
- **No Chaos Testing**: No fault injection or resilience verification exists.

The mission is to build the data foundation that eliminates these gaps, making the crawler framework production-grade: resilient, observable, auditable, and recoverable.

---

## 2. Functional Requirements

### FR-1: Core Crawler Engine

| ID | Requirement | Priority | Source |
|----|-------------|----------|--------|
| FR-1.1 | Framework shall support 11+ sources via unified crawler interface (crawl/transform/upsert) | MUST | Codebase analysis |
| FR-1.2 | Each source shall declare metadata in registry.py (capabilities, auth, SLA) | MUST | Already exists |
| FR-1.3 | Framework shall enforce fail-closed semantics: unhandled exception stops pipeline, no partial commit | MUST | NFR-1 |
| FR-1.4 | Circuit breaker per source (already implemented) with real metrics (replace stub) | MUST | metrics.py stub |
| FR-1.5 | Each source shall have independent rate limiter configuration | MUST | rate_limiter.py exists |
| FR-1.6 | Framework shall support dry-run mode for ALL sources | SHOULD | Currently partial |

### FR-2: Data Layer

| ID | Requirement | Priority | Source |
|----|-------------|----------|--------|
| FR-2.1 | **Dead Letter Queue**: Failed records (parse/transform/persist errors) shall be routed to a DLQ table, not discarded. Max payload per entry: 100KB (truncate at 100KB with truncation flag). | MUST | Critical gap |
| FR-2.2 | **DLQ Console**: CLI command to inspect, replay, purge DLQ entries | MUST | FR-2.1 |
| FR-2.3 | **Provenance Tracking**: Every crawler run shall produce a provenance record (run_id, source, params, timing, counts) | MUST | No provenance exists |
| FR-2.4 | **Field-level Provenance**: Optional annotation of which crawl run produced each record | SHOULD | FR-2.3 |
| FR-2.5 | **Watermarks**: Fine-grained progress tracking per source (page-level, chunk-level) | MUST | Date-only today |
| FR-2.6 | **Resume from Watermark**: Mid-crash resume from last committed watermark, not from start | MUST | FR-2.5 |
| FR-2.7 | **Dedup Pipeline**: Central dedup layer (not per-crawler hashes) with configurable strategy | MUST | Per-crawler hashes today |
| FR-2.8 | **Freshness Monitor**: Runtime freshness evaluation tied to coverage state machine | MUST | Only in consulting_readiness.py |
| FR-2.9 | **Coverage Integration**: Coverage evidence writes shall be part of crawl pipeline, not optional | MUST | Currently optional |

### FR-3: Source-Specific

| ID | Requirement | Priority | Source |
|----|-------------|----------|--------|
| FR-3.1 | PNCP: Maintain existing adapter, add DLQ + watermark | MUST | Primary source |
| FR-3.2 | PCP: Replace stub client, add full DLQ/watermark/provenance | MUST | clients/pncp is stub |
| FR-3.3 | ComprasGov: Integrate DLQ + watermark into existing adapter | MUST | Already validated |
| FR-3.4 | CIGA CKAN: Coverage-only source -- ensure DLQ coverage | SHOULD | Already validated |
| FR-3.5 | TCE-SC/DOE-SC/DOM-SC: Add provenance + watermark to existing crawlers | MUST | Existing crawlers |
| FR-3.6 | Replace ALL 6 stub modules with real implementations | MUST | Stub proliferation |
| FR-3.6.1 | metrics.py: Real Prometheus counters/histograms | MUST | Stub |
| FR-3.6.2 | redis_pool.py: Real Redis connection pool manager | MUST | Stub |
| FR-3.6.3 | supabase_client.py: Real Supabase client with connection lifecycle | MUST | Stub |
| FR-3.6.4 | clients/base: Real base HTTP client with retry/timeout/metrics | MUST | Stub |
| FR-3.6.5 | clients/pncp: Real PNCP API client using base client | MUST | Stub |

### FR-4: Operations

| ID | Requirement | Priority | Source |
|----|-------------|----------|--------|
| FR-4.1 | **Bootstrap**: Command to initialize a new source (create schema, set watermark, register in registry) | MUST | Missing |
| FR-4.2 | **Backfill**: Existing backfill mode shall write watermarks (currently only mode flag) | MUST | monitor.py exists |
| FR-4.3 | **Resume**: `--resume` flag resumes from last watermark for any source | MUST | Missing |
| FR-4.4 | **Kill**: `SIGTERM` handler for graceful shutdown at page boundary, saving progress | MUST | Missing |
| FR-4.5 | **Kill+Resume**: Combine kill handler + watermark for clean kill-then-resume lifecycle | MUST | FR-4.3 + FR-4.4 |
| FR-4.6 | **Idempotency Guarantee**: Re-running a completed watermark range produces zero duplicate data | MUST | Dedup (FR-2.7) |
| FR-4.7 | **Status CLI**: `monitor.py --status` shows live progress per source (pages, watermarks, DLQ count) | MUST | Missing |
| FR-4.8 | **Timeout Chain Validation**: Existing startup validation (retry.py) extended to cover all sources | SHOULD | PNCP only today |

### FR-5: Quality Infrastructure

| ID | Requirement | Priority | Source |
|----|-------------|----------|--------|
| FR-5.1 | HTTP 429 handling: All HTTP sources shall have rate-limit detection + backoff. Expected: retry 3x with backoff, then DLQ with error_code='rate_limited'. Circuit breaker shall NOT trip on 429. | MUST | Partial |
| FR-5.2 | HTTP 500 handling: Retry with exponential backoff (base 60s, multiplier 5, max 3). Expected: DLQ after 3 failures with error_code='server_error'. Circuit breaker tripped after threshold consecutive 500s. | MUST | retry.py exists |
| FR-5.3 | Timeout simulation: Tests verify behavior under connect/read timeouts. Expected: retry with backoff, DLQ after max retries. | MUST | Missing |
| FR-5.4 | Connection reset: Tests verify recovery from TCP reset (ConnectionResetError). Expected: retry, then DLQ. | MUST | Missing |
| FR-5.5 | Invalid JSON: Tests verify handling of truncated/extra-token/encoding errors. Expected: DLQ with error_code='parse_failed', do NOT retry (response received but unparseable). | MUST | Missing |
| FR-5.6 | Schema drift: Tests verify detection of missing/new/changed fields. Expected: DLQ with error_code='schema_drift', Sentry alert. | MUST | Missing |
| FR-5.7 | Duplicate injection: Same record submitted twice. Expected: second returns 'unchanged', no duplicate row in target table. | MUST | Per-crawler only |
| FR-5.8 | Upsert failure: DLQ routing when DB persist fails (connection lost, unique/FK violation). Expected: DLQ entry with original payload preserved. | MUST | Missing |
| FR-5.9 | Chaos test suite: tests/chaos/ module with shared fault injection fixtures. pytest marker: @pytest.mark.chaos. Each scenario asserts specific outcome (DLQ entry, retry count, CB state, alert). | MUST | Missing |
| FR-5.10 | Kill/Resume integration test: Step 1: crawl known dataset. Step 2: send SIGTERM. Step 3: verify watermark committed. Step 4: resume. Step 5: verify no duplicates or gaps. | MUST | Missing |

---

## 3. Non-Functional Requirements

### NFR-1: Resilience

| ID | Requirement | Target | Verification |
|----|-------------|--------|-------------|
| NFR-1.1 | Fail-closed: unhandled exception in any pipeline phase shall abort the run with no partial data commit | 100% | Integration test |
| NFR-1.2 | Circuit breaker shall prevent cascading failures across sources | < 5% false positives | Load test |
| NFR-1.3 | Retry with exponential backoff: max 3 attempts, base 60s, multiplier 5 | Per config | Assertion test |
| NFR-1.4 | DLQ shall never lose data: failed records are durable once written | 100% durability | Integration test |
| NFR-1.5 | Graceful shutdown within 30s of SIGTERM | < 30s | Integration test |
| NFR-1.6 | Resume from watermark shall not skip or duplicate records | Exactly-once semantics | Integration test |

### NFR-2: Observability

| ID | Requirement | Target | Verification |
|----|-------------|--------|-------------|
| NFR-2.1 | Prometheus metrics: crawl_duration, records_fetched, records_persisted, errors, cb_state per source | All sources | metrics.py impl |
| NFR-2.2 | DLQ monitoring: dlq_count, dlq_replayed, dlq_purged metrics | All sources | metrics.py impl |
| NFR-2.3 | Structured logging: JSON format with run_id, source, phase, duration | All pipeline phases | Logging audit |
| NFR-2.4 | Provenance table queryable: "what crawled what, when, with what result" | For each run | Integration test |

### NFR-3: Data Integrity

| ID | Requirement | Target | Verification |
|----|-------------|--------|-------------|
| NFR-3.1 | Dedup: identical records from same source produce single row | 0 duplicates | Assertion test |
| NFR-3.2 | Provenance chain: each record traceable to its producing run | 100% | Test query |
| NFR-3.3 | Watermark progress is durable: committed before data writes | WAL-style | Integration test |

### NFR-4: Performance

| ID | Requirement | Target | Verification |
|----|-------------|--------|-------------|
| NFR-4.1 | DLQ write overhead < 5% of total crawl time | p95 < 5% | Benchmark |
| NFR-4.2 | Watermark commit overhead < 100ms per page | p99 < 100ms | Benchmark |
| NFR-4.3 | Existing crawl throughput preserved (no regression). Baseline must be measured before implementation via `monitor.py --source pncp --mode dry-run --benchmark` and recorded in docs/benchmarks/baseline-2026-07-16.json | Baseline parity | Comparison test |

### NFR-5: Maintainability

| ID | Requirement | Target | Verification |
|----|-------------|--------|-------------|
| NFR-5.1 | Zero stub modules after implementation | 0 | Code audit |
| NFR-5.2 | All new modules shall have >= 80% test coverage | >= 80% | Coverage report |
| NFR-5.3 | All new public functions shall have type annotations | 100% | mypy --strict |

---

## 4. Constraints

| ID | Constraint | Impact |
|----|------------|--------|
| CON-1 | PostgreSQL as primary DB (existing) | DLQ, provenance, watermark tables must use PG |
| CON-2 | Supabase free tier limits: 20 connections, 500MB | Need batching, connection pooling |
| CON-3 | Existing 1326 test functions must not regress | All new code must pass existing tests |
| CON-4 | No LLM dependency in data path | DLQ routing must be deterministic, not AI-based |
| CON-5 | Existing crawler interfaces must remain backward-compatible | New features opt-in |
| CON-6 | Redis when available (graceful fallback when not) | redis_pool stub already has this pattern |
| CON-7 | 11 sources with different auth models | DLQ/watermark must be source-agnostic |

---

## 5. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    OPERATIONS LAYER                          │
│  bootstrap │ backfill │ resume │ kill │ status │ replay     │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                    CRAWL ENGINE                              │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐  │
│  │ PNCP    │ │ PCP      │ │ComprasGov│ │ ... (8 more)   │  │
│  │ Adapter │ │ Client   │ │ Crawler  │ │                │  │
│  └────┬────┘ └────┬─────┘ └────┬─────┘ └───────┬────────┘  │
│       │           │            │                │           │
│  ┌────▼───────────▼────────────▼────────────────▼────────┐  │
│  │              BASE CLIENT (real, not stub)              │  │
│  │   retry │ timeout │ circuit breaker │ metrics         │  │
│  └───────────────────────────────────────────────────────┘  │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                    DATA LAYER                                │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐  │
│  │ DLQ      │ │Watermark │ │Provenance│ │ Freshness      │  │
│  │ Table    │ │ Table    │ │ Table    │ │ Evaluator     │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────┬────────┘  │
│                                                  │           │
│  ┌──────────┐ ┌──────────┐ ┌────────────────────▼────────┐  │
│  │ Dedup    │ │ Coverage │ │ Coverage Evidence           │  │
│  │ Pipeline │ │ State    │ │ (existing 9-state model)   │  │
│  └──────────┘ └──────────┘ └─────────────────────────────┘  │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                    INFRASTRUCTURE                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐  │
│  │PostgreSQL│ │  Redis   │ │Prometheus│ │ Sentry         │  │
│  │ (exist)  │ │ (enable) │ │ (enable) │ │ (exist)        │  │
│  └──────────┘ └──────────┘ └──────────┘ └────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. Source Mapping

| Source | Authority | Type | Priority | Current State | DLQ Needed | Watermark Granularity |
|--------|-----------|------|----------|---------------|------------|----------------------|
| pncp | federal | bids | P0 | Production | Yes | Date + Page |
| dom_sc | municipal | bids | P0 | Production | Yes | Date |
| pcp | multi | bids | P0 | Production | Yes | Date + Page |
| compras_gov | federal | bids | P0 | Production | Yes | Date + Page |
| sc_compras | estadual | bids | P0 | Production | Yes | Date |
| contracts | federal | contracts | P0 | Production | Yes | Date + Page |
| transparencia | municipal | bids | P1 | Development | Yes | Entity |
| tce_sc | estadual | bids | P1 | Production | Yes | Date |
| doe_sc | estadual | bids | P1 | Production | Yes | Date |
| ciga_ckan | municipal | coverage | P2 | Production | No | N/A (coverage only) |
| mides_bigquery | estadual | bids | P2 | Development | Yes | Full refresh |

---

## 7. Data Layer Design

### 7.1 DLQ Table

```sql
CREATE TABLE IF NOT EXISTS dlq_entries (
    id              BIGSERIAL PRIMARY KEY,
    source          TEXT NOT NULL,
    run_id          TEXT NOT NULL,
    phase           TEXT NOT NULL,  -- 'fetch', 'transform', 'persist'
    payload         JSONB,
    error_code      TEXT,
    error_message   TEXT,
    error_traceback TEXT,
    failed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    replayed_at     TIMESTAMPTZ,
    replayed_by     TEXT,            -- run_id that replayed this
    purge_after     TIMESTAMPTZ      -- auto-purge deadline
);

CREATE INDEX idx_dlq_source ON dlq_entries(source);
CREATE INDEX idx_dlq_unreplayed ON dlq_entries WHERE replayed_at IS NULL;
```

### 7.2 Watermark Table

```sql
CREATE TABLE IF NOT EXISTS pipeline_watermarks (
    source          TEXT NOT NULL,
    scope_key       TEXT NOT NULL DEFAULT 'default',
    watermark_type  TEXT NOT NULL,  -- 'page', 'date', 'entity', 'chunk'
    watermark_value TEXT NOT NULL,
    committed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    run_id          TEXT NOT NULL,
    PRIMARY KEY (source, scope_key, watermark_type, watermark_value)
);
```

### 7.3 Provenance Table

```sql
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id          TEXT PRIMARY KEY,
    source          TEXT NOT NULL,
    mode            TEXT NOT NULL,      -- 'full', 'incremental', 'backfill'
    params          JSONB,              -- crawl parameters snapshot
    started_at      TIMESTAMPTZ NOT NULL,
    completed_at    TIMESTAMPTZ,
    status          TEXT NOT NULL,       -- 'running', 'completed', 'failed', 'killed'
    records_fetched    INT DEFAULT 0,
    records_transformed INT DEFAULT 0,
    records_persisted  INT DEFAULT 0,
    records_dlq        INT DEFAULT 0,
    error_message   TEXT,
    watermarks_committed INT DEFAULT 0
);
```

### 7.4 Dedup Layer

Central dedup via content hash across all sources, using existing per-crawler hash functions as input:

```sql
CREATE TABLE IF NOT EXISTS record_hashes (
    content_hash    TEXT PRIMARY KEY,
    source          TEXT NOT NULL,
    run_id          TEXT NOT NULL,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    seen_count      INT NOT NULL DEFAULT 1
);
```

### 7.5 Freshness Evaluator

Runtime integration with coverage state machine (existing `scripts/coverage/states.py`):
- After each crawl run, evaluate freshness per source/entity
- Update coverage_evidence state based on `evaluate_freshness()`
- Expose via `monitor.py --freshness` CLI

---

## 8. Operations Model

### 8.1 Bootstrap

```bash
python scripts/crawl/monitor.py --source pncp --bootstrap
```

Creates watermark at current date, registers in pipeline_runs, validates credentials.

### 8.2 Backfill (enhanced)

```bash
python scripts/crawl/monitor.py --source pncp --mode backfill --start-date 2025-01-01 --end-date 2025-06-30
```

Writes watermarks per chunk (existing chunking enhanced with watermark commits).

### 8.3 Resume

```bash
python scripts/crawl/monitor.py --source pncp --resume
```

Reads last committed watermark, resumes from that point.

### 8.4 Kill + Resume

Process:
1. Crawl process receives SIGTERM
2. Signal handler sets `shutdown_requested` flag
3. At next page boundary, crawl loop checks flag
4. Commits current watermark
5. Exits cleanly (no partial data in target tables)
6. Next run with `--resume` continues from watermark

### 8.5 DLQ Operations

```bash
# Inspect
python scripts/crawl/monitor.py --dlq-list --source pncp

# Replay
python scripts/crawl/monitor.py --dlq-replay --source pncp --limit 100

# Purge
python scripts/crawl/monitor.py --dlq-purge --source pncp --older-than 7d
```

### 8.6 Status

```bash
python scripts/crawl/monitor.py --status --source pncp
# Output: source, status, watermark, dlq_count, freshness, last_run_at
```

---

## 9. Quality Gates

### 9.1 Pre-Merge Gates

| Gate | Check | Enforced By | Tool |
|------|-------|-------------|------|
| G-9.1 | No new stubs introduced | CI | grep for "# STUB" |
| G-9.2 | All DLQ tables have UNLOGGED or proper durability | CI | migration audit |
| G-9.3 | Watermark writes in same transaction as data writes | CI | code review |
| G-9.4 | Chaos tests pass (min 5 scenarios) | CI | pytest -m chaos |
| G-9.5 | Kill/resume integration test passes | CI | pytest -m kill_resume |
| G-9.6 | No regression in existing 1326 tests | CI | pytest |

### 9.2 Test Categories

| Category | Count (target) | Framework | Coverage |
|----------|---------------|-----------|----------|
| Unit (DLQ logic) | 30 | pytest | FR-2.1, FR-2.2 |
| Unit (Watermark) | 20 | pytest | FR-2.5, FR-2.6 |
| Unit (Provenance) | 15 | pytest | FR-2.3 |
| Unit (Dedup) | 20 | pytest | FR-2.7 |
| Unit (Freshness) | 10 | pytest | FR-2.8 |
| Integration (DLQ) | 10 | pytest | NFR-1.4 |
| Integration (Kill/Resume) | 5 | pytest + signal | NFR-1.5, NFR-1.6 |
| Chaos (429) | 5 | pytest + mock | FR-5.1 |
| Chaos (500) | 5 | pytest + mock | FR-5.2 |
| Chaos (timeout) | 5 | pytest + mock | FR-5.3 |
| Chaos (reset) | 5 | pytest + mock | FR-5.4 |
| Chaos (invalid JSON) | 5 | pytest + mock | FR-5.5 |
| Chaos (drift) | 5 | pytest + mock | FR-5.6 |
| Chaos (duplicate) | 5 | pytest + mock | FR-5.7 |
| Chaos (upsert fail) | 5 | pytest + mock | FR-5.8 |
| **Total new tests** | **140+** | | |

### 9.3 Stub Replacement Gates

| Stub Module | Replacement | Verification |
|-------------|-------------|--------------|
| metrics.py | PrometheusClient with Counter/Histogram/Gauge | Exists, exported, testable |
| redis_pool.py | RedisPool with connection lifecycle, retry, fallback | Tests for each path |
| supabase_client.py | SupabaseClient with connection management, health check | Integration test |
| clients/base/ | BaseHTTPClient with retry/timeout/metrics/cb | Unit tests |
| clients/pncp/ | PNCPClient inheriting BaseHTTPClient | Integration test |

---

## 10. Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Stub replacement breaks existing code | Medium | High | Keep backward-compatible imports; run full test suite before/after |
| DLQ table size grows unbounded | Medium | Low | Auto-purge policy (configurable TTL), dlq-purge command |
| Kill/Resume leaves inconsistent state | Low | Critical | Test with fault injection; watermark committed before data write |
| Redis circuit breaker migration fails | Low | Medium | Graceful fallback to local CB (already implemented) |
| Performance regression from DLQ writes | Medium | Medium | Benchmark before/after; DLQ write is async where possible |
| Existing 1326 tests require updates | Medium | High | Make all new features opt-in; existing interfaces unchanged |
| Schema migration conflicts with existing 50 migrations | Medium | High | New tables only; no ALTER of existing tables |

---

## APPENDIX A: Traceability Matrix

| FR ID | Source | Priority | Tests | Dependencies |
|-------|--------|----------|-------|-------------|
| FR-1.1 | Codebase analysis | MUST | Existing test suite | Registry |
| FR-1.3 | NFR-1 | MUST | Chaos suite | New engine |
| FR-2.1 | Gap analysis | MUST | 30 unit + 10 integ | DLQ table |
| FR-2.3 | Gap analysis | MUST | 15 unit | pipeline_runs table |
| FR-2.5 | Gap analysis | MUST | 20 unit | pipeline_watermarks table |
| FR-2.7 | Gap analysis | MUST | 20 unit | record_hashes table |
| FR-3.6 | Gap analysis | MUST | Per-module tests | Phase A: metrics + base client. Phase B: redis_pool + supabase_client. Phase C: clients/pncp |
| FR-4.1 | Operations | MUST | Integration | Bootstrap flow |
| FR-4.4 | Operations | MUST | 5 integ | Signal handler |
| FR-5.9 | Quality | MUST | 35 chaos tests | Mock infrastructure |

## APPENDIX B: Glossary

| Term | Definition |
|------|------------|
| DLQ | Dead Letter Queue -- durable storage for failed pipeline records |
| Watermark | Progress marker indicating how far a crawl has progressed |
| Provenance | Lineage metadata linking records to their producing crawl run |
| Fail-closed | Pipeline aborts on error, leaving no partial data |
| Kill/Resume | Lifecycle for safe interruption and continuation of crawls |
| Stub | Placeholder module with no real implementation |
