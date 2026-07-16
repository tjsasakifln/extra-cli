# Operations Guide — Data Foundation Components

**Version:** 1.0.0
**Epic:** DATA-FOUNDATION
**Date:** 2026-07-16

## Overview

This guide covers the new data foundation components added during the DATA-FOUNDATION epic: Dead Letter Queue (DLQ), Watermark Engine, Provenance Tracking, Freshness Evaluator, and the source adapter enhancements.

---

## 1. Dead Letter Queue (DLQ)

### Sync Interface (for legacy sync adapters)

```python
from scripts.crawl.dlq_sync import dlq_write, dlq_count, dlq_list, dlq_replay, dlq_purge

# Write a failed record to DLQ
dlq_write(source="pncp", error_code="fetch_failed", error_message="HTTP 500", payload={...})

# Count pending entries
count = dlq_count(source="pncp")

# List entries
entries = dlq_list(source="pncp", limit=50)

# Replay entries
replayed = dlq_replay(source="pncp", limit=50)

# Purge old entries
purged = dlq_purge(source="pncp", older_than_days=90)
```

### Async Interface (for new async adapters)

```python
from scripts.crawl.dlq import DurableDLQ
from scripts.crawl.pipeline import DLQRecord, PipelineStage

dlq = DurableDLQ(conn_string=DEFAULT_DSN)
entry_id = await dlq.push(DLQRecord(source="pncp", run_id="r1", ...))
count = await dlq.pending_count(source="pncp")
```

### TTL Policy
- Pending entries: retained indefinitely (until replayed or purged)
- Dead entries: auto-purged after 90 days (configurable via `dlq_purge(older_than_days=N)`)
- Max payload: 100KB (truncated with truncation_flag=True)

---

## 2. Watermark Engine

### Sync Interface

```python
from scripts.crawl.watermark_sync import watermark_commit, watermark_read, watermark_next_page, watermark_reset

# Commit progress after page fetch
watermark_commit(source="pncp", scope_key="page", value="42", run_id="run-1")

# Read last committed value
last = watermark_read(source="pncp", scope_key="page")

# Get next page for resume (with 1-page overlap)
next_page = watermark_next_page(source="pncp", overlap=1)

# Reset watermark
watermark_reset(source="pncp")
```

### Resume Support

All source adapters now accept an optional `resume=True` parameter:

```python
# First run: normal crawl
crawl("full")

# Second run: resumes from last watermark
crawl("full", resume=True)
```

Source adapters with resume support:
- `pncp_crawler_adapter.crawl(mode, resume=False)`
- `pcp_crawler.crawl(mode, resume=False)`
- `compras_gov_crawler.crawl(mode, resume=False)`
- `tce_sc_crawler.crawl(mode, resume=False)`
- `doe_sc_crawler.crawl(mode, resume=False)`
- `dom_sc_crawler.crawl(mode, resume=False)`
- `ciga_ckan_crawler.crawl(mode, resume=False)`

---

## 3. Provenance Tracking

### Sync Interface

```python
from scripts.crawl.provenance_sync import provenance_start, provenance_complete, provenance_fail

# Start a run
run_id = provenance_start(source="pncp", mode="full")

# Complete a run
provenance_complete(run_id, "pncp", records_fetched=100)

# Fail a run
provenance_fail(run_id, "pncp", error_message="Network error")
```

All source adapters with provenance:
- PCP, TCE-SC, DOE-SC, DOM-SC, CIGA CKAN

---

## 4. Freshness Evaluator

```python
from scripts.crawl.freshness import evaluate_freshness, format_freshness_report

# Evaluate per-source freshness
results = evaluate_freshness(conn)

# Generate human-readable report
report = format_freshness_report(conn)
print(report)
```

Expected output:
```
Freshness Report
============================================================
  OK pncp                fresh           last=2026-07-15...   coverage=45.2%  SLA=24h
  OK pcp                 fresh           last=2026-07-16...   coverage=12.1%  SLA=48h
  STALE compras_gov      stale           last=2026-06-01...   coverage=38.5%  SLA=48h
  ?   ciga_ckan          never_crawled   last=never             coverage=0.0%  SLA=168h
============================================================
  2 fresh  |  2 stale/never  |  4 total sources
```

---

## 5. New CLI Commands

### DLQ Commands (via `--dlq-*` flags on monitor.py)

| Flag | Description | Example |
|------|-------------|---------|
| `--dlq-list` | List pending DLQ entries | `python monitor.py --dlq-list` |
| `--dlq-list --source pncp` | List for specific source | `python monitor.py --dlq-list --source pncp` |
| `--dlq-replay` | Replay all pending entries | `python monitor.py --dlq-replay` |
| `--dlq-purge` | Purge entries older than TTL | `python monitor.py --dlq-purge` |

### Source-agnostic Commands (already in monitor.py)

| Flag | Description |
|------|-------------|
| `--resume` | Resume from last watermark (opt-in) |
| `--freshness` | Show freshness report per source |
| `--status` | Show per-source crawl status |

---

## 6. Stub Status

| Module | Status | Notes |
|--------|--------|-------|
| `scripts/crawl/redis_pool.py` | REPLACED | Real redis.asyncio pool with fallback |
| `scripts/crawl/supabase_client.py` | REPLACED | Real supabase-py client with health check |
| `scripts/crawl/clients/pncp/async_client.py` | STUB | References scripts/crawl/async_client.py |
| `scripts/crawl/clients/pncp/_parallel_mixin.py` | STUB | References scripts/crawl/_parallel_mixin.py |
| `scripts/crawl/clients/pncp/retry.py` | STUB | References scripts/crawl/retry.py |
| `scripts/crawl/clients/base/base.py` | REAL | BaseHTTPClient with retry + CB |

---

## 7. SLA Matrix

| Source | SLA (hours) | Freshness Window |
|--------|-------------|------------------|
| PNCP | 24 | Daily full + 3x incremental |
| PCP | 48 | Full 365d + incremental |
| ComprasGov | 48 | Full 30d + incremental |
| TCE-SC | 72 | Full 90d + incremental |
| DOE-SC | 72 | Full 90d + incremental |
| DOM-SC | 72 | Full 180d + incremental |
| CIGA CKAN | 168 (weekly) | Full coverage scan |
| SC Compras | 48 | On-demand |
| Contracts | 48 | On-demand |

---

## 8. Monitoring

### DB Tables

| Table | Purpose |
|-------|---------|
| `dlq_entries` | Dead Letter Queue records |
| `pipeline_watermarks` | Per-source page/date watermarks |
| `pipeline_runs` | Provenance records per crawl run |
| `record_hashes` | Content-hash dedup records |
| `entity_coverage` | Per-source entity coverage state |

### Key Metrics

- `dlq_entries WHERE status='pending'` — stale count should remain low
- `pipeline_watermarks` — should advance per source regularly
- `pipeline_runs WHERE status='failed'` — indicates chronic issues
