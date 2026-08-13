# Story: Critical Issues Wave 2

**Status:** InProgress
**Branch:** `agent/critical-issues-wave-2`
**Base:** `origin/main` at `2f89fb363abc2bc56568dd0ae11afe554cbcb4c4`
**Capability:** Durable, secure and continuously scheduled public-source crawl runtime

## Goal

Resolve the next ten open `priority:p0` + `risk:high` issues that form one
operational capability, have no assignee or open treatment PR, and can be
verified without claiming live coverage or `VPS_OPERATIONAL`:

1. #235 — discover and revalidate public surfaces for 1,093 entities
2. #236 — maintain the entity × applicable-source coverage matrix
3. #246 — persist the durable crawl queue in PostgreSQL
4. #247 — archive immutable raw HTTP envelopes with SHA-256
5. #268 — continuously schedule applicable entity/source pairs
6. #269 — execute concurrent leased workers with backpressure
7. #270 — centralize retry, rate-limit and circuit-breaker policy
8. #272 — persist document metadata and versions in PostgreSQL
9. #276 — harden crawler sandbox and secret handling
10. #279 — persist sanitized request/page failure diagnostics

The issues and their GitHub acceptance criteria are authoritative. This story
groups them because #268 directly depends on #235, #236 and #246, while the
queue, worker, raw evidence, resilience, document lineage, security and
diagnostics contracts must agree atomically.

## Acceptance criteria

### #235 — public-surface discovery

- [ ] Exactly the 1,093 IDs of the active universe have versioned discovery results.
- [ ] Institutional, procurement, transparency, gazette and cited-platform surfaces preserve canonical URL, domain, platform, anchor, method, HTTP and Sao Paulo timestamp.
- [ ] New domains remain `UNCLASSIFIED`; login/CAPTCHA/403 is `BLOCKED`; exhausted discovery is explicit.
- [ ] Revalidation records next check and history, invalidating stale bindings without deleting history.
- [ ] A stratified 30-entity wave is auditable before scale.

### #236 — continuous applicability/coverage

- [ ] Every applicable entity/source/capability pair has one current state and attempt history.
- [ ] `ZERO_CONFIRMED` requires a complete reconciled request with preserved empty raw evidence.
- [ ] Rows retain URL, applicability, timestamps, HTTPs, pages, records, freshness, evidence and next action.
- [ ] Every entity has an open-tender route scheduled or an explicit blocker/recheck.
- [ ] Excel, manifest and KPI derive from the same 1,093-ID authority.

### #246 — durable PostgreSQL queue

- [ ] `crawl_jobs` and `crawl_job_attempts` persist cursor, freshness, priority, lease and idempotency key.
- [ ] Transactional concurrency cannot duplicate a job; restart recovers pending and expired leases.
- [ ] CLI supports enqueue, inspect and requeue and reconciles applicable pairs.
- [ ] Migration, rollback and one-shot JSON migration are tested.

### #247 — immutable raw HTTP evidence

- [ ] Every successful or failed page has a sanitized request envelope and body pointer.
- [ ] SHA-256 is revalidatable and content-addressed storage deduplicates bodies.
- [ ] Partial runs retain completed pages; credentials/cookies are redacted.
- [ ] Bodies are absent from Git and PostgreSQL payload columns.

### #268 — continuous scheduler

- [ ] Deterministic dry-run reconciles exactly the active 1,093 entity IDs.
- [ ] Every applicable pair is queued/running or has an explicit reason and next check.
- [ ] Completion schedules the next policy-driven run; reruns do not duplicate jobs.
- [ ] `NOT_APPLICABLE`, `BLOCKED` and `FAILED` have versioned finite recheck policies.
- [ ] Source binding changes invalidate future jobs; lateness/freshness is exportable.
- [ ] A systemd timer survives reboot and leaves no entity without `next_run`.

### #269 — leased workers

- [ ] Two to four workers use `FOR UPDATE SKIP LOCKED` without processing one job twice.
- [ ] Expired leases return to the queue; SIGTERM saves cursor without false success.
- [ ] CPU, memory or disk pressure stops admission and domain limits apply.
- [ ] A 4,372-pair test has no starvation; every attempt records run and metrics.

### #270 — resilience policy

- [ ] Versioned per-domain policy covers timeout, `Retry-After`, jitter, attempts, breaker and budget.
- [ ] Tests cover 403, 429, 5xx, timeout and reset; permanent auth blocks never loop.
- [ ] Partial failure never closes a window; attempts, sleeps, latency and pages are measurable.
- [ ] No authentication or terms bypass is introduced.

### #272 — document lineage

- [ ] Canonical document, version, fetch and process-link tables reference entity/process/run/attempt.
- [ ] Source/official/version and SHA uniqueness preserve new content as a new immutable version.
- [ ] Job success requires both blob and metadata confirmation.
- [ ] Queries and restore preserve procurement/entity lineage.

### #276 — crawler security

- [ ] `file://`, loopback/private redirects and path traversal are rejected.
- [ ] ZIP/PDF size and expansion limits fail closed.
- [ ] Units use a non-root user and a mode-0600 environment file.
- [ ] CAPTCHA/login becomes `BLOCKED`; DSNs, tokens and cookies never reach logs/evidence.
- [ ] `systemd-analyze security` meets a documented threshold.

### #279 — structured diagnostics

- [ ] Failures preserve sanitized source, URL, stage, page/cursor, class, HTTP, attempt and next action.
- [ ] Transient and permanent classes are distinct and feed retry/DLQ/alerts.
- [ ] Tests cover 403, 404 drift, 429, 504, parse and PostgreSQL persistence.

## Tasks

- [x] Wave A: central resilience policy and sanitized structured diagnostics (#270, #279).
- [x] Wave B: durable queue, leased workers and continuous scheduler (#246, #268, #269).
- [x] Wave C: immutable raw evidence and canonical document lineage (#247, #272).
- [x] Wave D: discovery, applicability/coverage and crawler sandbox (#235, #236, #276).
- [ ] Apply and rollback migrations on disposable PostgreSQL 16 + pgvector.
- [ ] Run focused tests after every wave and the canonical full suite at completion.
- [x] Run strict golden path and preserve any external failure as `PARTIAL`/`BLOCKED`.
- [ ] Run CodeRabbit, generated-artifact and Ready reviewability policies.
- [ ] Publish one draft PR, then make the exact PR HEAD fully green.

## Non-goals and truth ceiling

- No dashboard control plane; CLI remains authoritative.
- No claim of 95% coverage, `LOCAL_READY`, live freshness or `VPS_OPERATIONAL` from fixtures/unit tests.
- No DOD checkbox becomes accepted before exact-HEAD CI and merge to `main`.
- Unrelated user work in the original checkout is not part of this branch.

## Dev Agent Record

### Agent Model Used

- Codex GPT-5

### Debug Log References

- Focused regression: 132 passed, 3 integration tests deselected.
- Real PostgreSQL: diagnostics, concurrent queue/lease recovery/domain limit,
  1,093 × 4 deterministic scheduler, and immutable document versions passed.
- Disposable DB: migrations 078–083 applied and rollbacks 083–078 passed;
  local PostgreSQL image lacks pgvector, so the pgvector-qualified gate remains open.
- Static runtime: Ruff clean, compileall clean, systemd validator clean, new
  scheduler/worker hardening score 100%.
- Canonical suite attempt 1: 2,353 passed before a new real-DB test exposed the
  repository's opt-in DB isolation contract; fixed and all six explicit PG proofs passed.
- Canonical suite attempt 2: 1,851 passed before the legacy hygiene gate hit
  host `OSError 12` with 655 MiB free; that gate passed alone in 9.47 seconds.
- Strict golden path: migrations/seeds/universe passed and PNCP fetched 804;
  final status `PARTIAL` because PCP hit a pre-existing content-hash conflict,
  `compras_gov` returned verified zero, contracts were stale and one local
  coverage evidence row lacked identity. The provenance counter bug exposed
  during this run is fixed by the rebased upstream terminal-persistence contract.
- CodeRabbit pass 1: five actionable findings; all addressed (binary/header
  redaction, recursive secret-key CHECK, legacy duplicate preflight, terminal
  partial discovery state, destructive rollback warning). The immediate rerun
  was rate-limited by the free CLI allowance before analysis.
- Final focused regression: 101 passed / 8 explicit-DB tests reserved; all six
  selected PostgreSQL proofs then passed with `RESILIENCE_REQUIRE_DB=1`.
- PR policy preflight: generated-artifacts and draft reviewability both passed
  with zero violations. Scheduler and worker hardening both scored 1.0.
- Exact-HEAD CI pass 1: every fast/quality/security/resilience gate passed;
  both jobs containing the canonical full suite found the same test-setup gap:
  a fresh database had the 1,093 seeded entities but no materialized
  `target_universe_entities` snapshot. The test now invokes the existing
  canonical materializer when and only when the active snapshot is empty.
- Exact-HEAD CI pass 2: 27/28 checks passed, including one canonical full-suite
  execution. The duplicate full-suite job exposed an intermittent queue claim:
  PostgreSQL could evaluate the advisory-lock predicate before `LIMIT` and lock
  a domain belonging to a row that worker never claimed. The short admission
  transaction is now serialized, with materialized candidate selection and
  per-domain capacity ranking; leased job execution remains concurrent.
- Queue race regression after the fix: 200/200 concurrent repetitions passed
  (100 distinct-domain claims and 100 shared-domain-limit claims); the 92-test
  focused suite with all PostgreSQL proofs also passed. Draft generated-artifact
  and reviewability policies remain green with zero violations.

### Completion Notes

- The implementation preserves the 1,093 canonical IDs even though they map to
  1,090 distinct legacy database roots; queue uniqueness is canonical-ID based.
- Entity-wide `ZERO_CONFIRMED` remains fail-closed when an adapter only proves a
  municipality/source-wide empty response.
- No live coverage, VPS or `LOCAL_READY` claim is made by these tests.

### File List

- `config/crawl-domain-policies.json`
- `config/crawl-schedule-policies.json`
- `db/migrations/078_crawl_failure_events.sql`
- `db/migrations/079_crawl_runtime_queue.sql`
- `db/migrations/080_raw_http_archive.sql`
- `db/migrations/081_canonical_document_lineage.sql`
- `db/migrations/082_public_surface_coverage.sql`
- `db/migrations/083_crawl_queue_canonical_entity.sql`
- `db/rollback/078_crawl_failure_events_rollback.sql`
- `db/rollback/079_crawl_runtime_queue_rollback.sql`
- `db/rollback/080_raw_http_archive_rollback.sql`
- `db/rollback/081_canonical_document_lineage_rollback.sql`
- `db/rollback/082_public_surface_coverage_rollback.sql`
- `db/rollback/083_crawl_queue_canonical_entity_rollback.sql`
- `deploy/systemd/extra-crawl-scheduler.service`
- `deploy/systemd/extra-crawl-scheduler.timer`
- `deploy/systemd/extra-crawl-worker@.service`
- `docs/ops/crawler-runtime-security.md`
- `docs/stories/story-critical-issues-wave-2.md`
- `scripts/crawl/pncp_crawler_adapter.py`
- `scripts/crawl/resilience/adapters.py`
- `scripts/crawl/resilience/config.py`
- `scripts/crawl/resilience/diagnostics.py`
- `scripts/crawl/resilience/domain_policy.py`
- `scripts/crawl/resilience/http_policy.py`
- `scripts/crawl/resilience/pipeline.py`
- `scripts/crawl/resilience/state.py`
- `scripts/crawl/runtime_queue.py`
- `scripts/crawl/scheduler.py`
- `scripts/crawl/security.py`
- `scripts/crawl/worker.py`
- `scripts/ops/resilient_cycle.py`
- `scripts/ops/validate_crawler_runtime_security.py`
- `scripts/process_documents/persistence.py`
- `scripts/process_documents/storage.py`
- `scripts/source_registry/continuous_inventory.py`
- `scripts/source_registry/discovery.py`
- `tests/test_crawl_failure_diagnostics.py`
- `tests/test_crawl_runtime_queue.py`
- `tests/test_crawl_security_wave2.py`
- `tests/test_document_lineage.py`
- `tests/test_local_resilience.py`

## Change log

| Date | Scope | State | Evidence |
|---|---|---|---|
| 2026-08-13 | Story/selection | READY_FOR_DEV | GitHub: ten open P0/high, state ready, no assignee/comments/open PR |
| 2026-08-13 | 0.1.0 | IN_PROGRESS | Development started (autonomous execution) — Status: Ready → InProgress |
| 2026-08-13 | 0.2.0 | IN_PROGRESS | Waves A–D implemented; focused + PostgreSQL evidence passed; full gates pending |
| 2026-08-13 | 0.3.0 | IN_PROGRESS | CodeRabbit findings fixed; fresh 001–083 migration and reverse 083–078 rollback passed; strict golden path preserved as PARTIAL |
| 2026-08-13 | 0.4.0 | IN_PROGRESS | Rebased onto current main; retained upstream fail-closed provenance contract and dropped the superseded local wrapper change |
| 2026-08-13 | 0.5.0 | IN_PROGRESS | Exact-HEAD CI setup gap fixed without weakening the 1,093/4,372 assertion; CI rerun pending |
| 2026-08-13 | 0.6.0 | IN_PROGRESS | Exact-HEAD CI isolated an advisory-lock-before-limit race; the short claim admission transaction is now deterministic while leased execution stays concurrent |
