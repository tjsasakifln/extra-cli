# Story: Critical Issues Wave 3

**Status:** InProgress
**Branch:** `agent/critical-issues-wave-3`
**Base:** `origin/agent/critical-issues-wave-2` at `c60cc94a902112dd4675f648cb39668b3789faa1`
**Capability:** Canonical public truth plane with complete, fail-closed reporting projections

## Goal

Deliver one bounded, reviewable wave toward the ten open `priority:p0`
issues that were still `state:ready` and had no assignee, comment, commit or
pull-request work event at the 2026-08-13 triage cutoff:

1. #356 — eliminate sampled national supplier histories
2. #355 — eliminate silent 1,000-row analytical truncation
3. #354 — publish a versioned SELECT-only SmartLic read contract
4. #348 — resolve PCP `content_hash` collision without false success
5. #289 — persist canonical bitemporal public entities/events/observations
6. #287 — close client-independent canonical snapshots
7. #275 — expose fail-closed truth-plane SLOs and public-reader isolation
8. #274 — persist a transactional DLQ with selective replay
9. #273 — prove idempotent multifonte deduplication and N:N lineage
10. #244 — reconfirm shortlisted tenders against official source state

The GitHub issue bodies and acceptance criteria are authoritative. A PR may
reference an issue only when residual live, cross-repository or infrastructure
criteria remain. It may close an issue only when every criterion has direct,
reproducible evidence.

## Acceptance contract

### Report integrity (#355, #356)

- [x] Supplier history is loaded from the canonical PostgreSQL lake by typed
  supplier identity; it never scans a few national API pages and filters later.
- [x] Analytical count/sum/mean/percentiles run server-side over the complete
  filtered population and are invariant to presentation page size.
- [x] Detail listings use stable keyset pagination with total count, cursor,
  unique tiebreak, snapshot/run, freshness and explicit completeness state.
- [x] A real-PostgreSQL fixture above 1,501 rows reconciles exact totals,
  percentiles, annual chart and detailed rows.

### Public truth plane (#273, #289, #287, #354)

- [x] Canonical client-independent IDs preserve source observations, aliases,
  N:N lineage, ambiguous conflicts and immutable bitemporal revisions.
- [x] Reprocessing and source-order permutations preserve IDs, counts and
  hashes; later corrections remain queryable as-of.
- [x] Canonical snapshots bind universe/policy/schema/adapter hashes,
  watermarks and factual revisions without `client_id` or `profile_hash`.
- [x] `public_read_v1` is versioned and SELECT-only, exposes provenance,
  freshness and completeness, and denies internal-schema/write access.
- [x] Migration/rollback, permission, repeatable-read and contract-diff proofs
  run against real PostgreSQL.

### Runtime truth (#348, #274, #275)

- [x] Duplicate `content_hash` values within a PCP batch or against persisted
  rows follow one deterministic identity rule without aborting the batch.
- [x] Persisted inserted/updated/deduplicated/DLQ counts reconcile, and a
  transform/upsert failure cannot leave the global run terminally completed.
- [x] The PostgreSQL DLQ moves a failed job once, blocks infinite retry,
  preserves history on selective replay and filters by source/entity/class.
- [x] SLI output defines denominator/window/UNKNOWN for every stage, including
  public-reader freshness/load, cost, alerts and kill-switch state.

### Official status reconfirmation (#244)

- [x] Every shortlisted tender has an America/Sao_Paulo reconfirmation timestamp
  and official evidence; missing evidence blocks the shortlist.
- [x] Terminal events or expired deadlines exclude open status, while ambiguous
  status remains `REVIEW`/`NO_GO` with blocker and next action.
- [x] One source failure remains attributable and does not erase other source
  results or fabricate a successful reconfirmation.

## Execution waves

- [x] Wave A: #348 deterministic PCP persistence and terminal lineage.
- [x] Wave B: #355/#356 complete server-side contract analytics.
- [x] Wave C: #274 durable DLQ and #275 truth-plane SLI contract.
- [x] Wave D: #273/#289 canonical identities, observations and revisions.
- [x] Wave E: #287 canonical snapshot and #354 `public_read_v1` projection.
- [x] Wave F: #244 official status reconfirmation.
- [x] Apply and rollback migrations on disposable PostgreSQL 16 + pgvector.
- [ ] Run focused tests after each wave, then canonical full suite and strict
  golden path without promoting partial/live failures.
- [ ] Run CodeRabbit, generated-artifact and ready reviewability policies.
- [ ] Publish a draft PR and make the exact PR HEAD fully green.

## Truth ceiling

- No 95% coverage, `LOCAL_READY`, `VPS_OPERATIONAL` or public-read production
  claim follows from fixtures, migration tests or green CI.
- SmartLic consumer/cutover and combined production soak remain cross-repo/live
  evidence and cannot be fabricated in this repository.
- DOD checkboxes remain unchanged until evidence is accepted from merged `main`.
- The original mixed checkout and every other worktree remain out of scope.

## Dev Agent Record

### Agent Model Used

- Codex GPT-5

### Debug Log References

- Triage: exactly ten open P0 `state:ready` issues; zero assignees/comments and
  zero commit/PR timeline events at cutoff.
- Wave A: migration 085 applied, rolled back and reapplied on isolated real
  PostgreSQL; 31 PCP tests passed with deterministic intra-batch/existing-hash
  collision, update, order-invariance and deferred terminal-lineage proofs.
- Wave B: migration 086 rollback/reapply and migration-runner apply passed on
  isolated PostgreSQL. A 1,503-row fixture passed exact count/sum/percentiles,
  17-vs-1,000 page-size invariance, stable keyset pagination and annual/detail
  reconciliation; 28 focused tests passed with the real DB gate enabled.
- Wave C: migration 087 rollback/reapply and migration-runner apply passed.
  PostgreSQL poison/BLOCKED/replay/resolve and fail-closed SLI/last-valid/
  alert-route/cost/kill-switch proofs passed against the isolated database.
- Wave D: migration 088 rollback/reapply passed. Real-PostgreSQL permutations
  proved two-source N:N lineage, stable IDs/counts/hashes, valid-time as-of,
  document versions, a second event type, ambiguity without auto-merge,
  indexed lookup plans, merge/split history and immutable revisions.
- Wave E: migration 089 rollback/reapply and migration-runner apply passed.
  Repeatable-read/concurrent-revision tests preserved the closed snapshot;
  private and factual invalidation scopes diverged correctly; the versioned
  role denied internal reads, writes and DDL while bounded public queries ran.
- Wave F: every scored shortlist candidate now passes through a source-specific
  final read. PNCP uses the official structural endpoint; PCP re-reads the
  publication-date result set. Three deterministic tests prove Sao Paulo
  timestamps/evidence, terminal/expired/ambiguous blocking and per-source
  failure isolation without fabricated GO decisions.
- Integrated migration gate: a dedicated PostgreSQL 16.14 + pgvector 0.8.4
  container applied migrations 001-089, rolled back 089-085 in reverse order,
  reapplied all five from the ledger, then passed 67 focused tests against the
  fresh schema.
- Canonical full-suite entrypoint applied all 89 migrations in `fresh` mode,
  seeded 2,085 entities (1,093 active) and 459 aliases, then completed 4,426
  passes and 141 declared skips. Its only failure was an undeployed local
  dependency (`pypdf`); the failed PDF reconciliation test passed after
  installing `pypdf 6.16.0`, satisfying the repository's declared
  `pypdf>=6.15.0` requirement that CI installs.
- Strict live golden path remained honestly `PARTIAL`: PNCP returned HTTP 422,
  contract freshness was stale and one evidence row was outside the identity
  map. PCP persisted data, reports were generated, and no readiness/coverage
  claim is promoted from that run.

### File List

- `docs/stories/story-critical-issues-wave-3.md`
- `db/migrations/085_pncp_content_hash_collision.sql`
- `db/rollback/085_pncp_content_hash_collision_rollback.sql`
- `db/migrations/086_contract_analytics_complete.sql`
- `db/rollback/086_contract_analytics_complete_rollback.sql`
- `db/migrations/087_runtime_truth_dlq_sli.sql`
- `db/rollback/087_runtime_truth_dlq_sli_rollback.sql`
- `db/migrations/088_canonical_public_events.sql`
- `db/rollback/088_canonical_public_events_rollback.sql`
- `db/migrations/089_canonical_snapshot_public_read_v1.sql`
- `db/rollback/089_canonical_snapshot_public_read_v1_rollback.sql`
- `docs/contracts/public-read-v1.md`
- `scripts/crawl/monitor.py`
- `scripts/crawl/pcp_crawler.py`
- `scripts/datalake_helper.py`
- `scripts/collect_report_data.py`
- `scripts/official_status_reconfirmation.py`
- `scripts/crawl/runtime_queue.py`
- `scripts/ops/truth_plane_sli.py`
- `scripts/ops/canonical_snapshot.py`
- `tests/test_crawl_runtime_queue.py`
- `tests/test_canonical_public_events.py`
- `tests/test_datalake_helper.py`
- `tests/test_pcp_crawler.py`
- `tests/test_official_status_reconfirmation.py`

## Change log

| Date | Scope | State | Evidence |
|---|---|---|---|
| 2026-08-13 | Story/selection | IN_PROGRESS | GitHub labels, issue bodies and timeline audit |
| 2026-08-13 | #348 | VERIFIED_LOCAL | PostgreSQL migration/rollback/reapply; 31 tests pass |
| 2026-08-13 | #355/#356 | VERIFIED_LOCAL | PostgreSQL 1,503-row completeness, pagination and report reconciliation proof |
| 2026-08-13 | #274/#275 | VERIFIED_LOCAL | Transactional poison DLQ and fail-closed SLI authority on PostgreSQL |
| 2026-08-13 | #273/#289 | VERIFIED_LOCAL | Multifonte order/idempotency, revisions, conflicts and merge/split on PostgreSQL |
| 2026-08-13 | #287/#354 | VERIFIED_LOCAL | Snapshot barrier, repeatable read, invalidation scopes and SELECT-only role |
| 2026-08-13 | #244 | VERIFIED_LOCAL | Official PNCP/PCP close gate; timezone/evidence, terminal/expiry/ambiguity and isolated source-failure tests |
