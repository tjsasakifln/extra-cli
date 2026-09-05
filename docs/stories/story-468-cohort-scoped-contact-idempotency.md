# #468 — Scope contact-discovery idempotency to a cohort

Status: InReview

## Story

As the operator of consecutive REV-05 commercial cycles, I need contact job
idempotency to deduplicate retries within one cohort while allowing a later,
independent cohort to process the same contract, so an aborted cohort cannot
block a fresh authorized cycle.

## Authority and scope

Founder authorization was provided after the fail-closed CYCLE_1 evidence in
issue #468. Base code and production SHA:
`23cb416cf3f3555d7e070942191940ddeca40d51`.

Only `contact_discovery_jobs.idempotency_key` scoping and directly necessary
tests/documentation are authorized. Do not reassociate, reuse or reactivate old
jobs/cohorts. Classification, target-fit, coverage, feed semantics, PNCP, SMTP,
dispatch, mailbox, volume, rate, cadence and architecture remain unchanged.

## Acceptance criteria

1. The same execution contract enqueued repeatedly into the same cohort creates
   one logical job and returns the same job identity.
2. The same execution contract in two different cohorts creates distinct jobs.
3. A prior aborted/cancelled cohort cannot block a new cohort using the same
   execution contract.
4. Concurrent replay in one cohort creates only one job.
5. A failed contact cycle cannot change contact `current` or publish a partial
   projection.
6. Existing schema remains usable without reassociating or mutating historical
   jobs, and no migration is introduced unless proven unavoidable.
7. Relevant regressions, commercial-plane preflight, artifact binding and all
   required GitHub checks pass before merge.
8. The merged SHA is deployed immutably; the prior feed, paused dispatch and
   SMTP delta zero are revalidated. No new REV-05 cycle starts before a new
   founder checkpoint for that deployed SHA.

## Tasks

- [x] Reproduce the cross-cohort collision against the public queue API before
      changing production code. (AC 2, 3)
- [x] Add same-cohort sequential and concurrent replay regressions. (AC 1, 4)
- [x] Apply the smallest cohort-scoping change to the idempotency contract and
      its direct callers. (AC 1–4, 6)
- [x] Lock down fail-closed `current` preservation through the contact-cycle
      public boundary. (AC 5)
- [x] Run focused, commercial and repository quality gates without adding
      skips, waivers or threshold changes. (AC 7; GitHub required checks remain
      the merge gate)
- [x] Update evidence, file list and status after validation. (AC 7, 8)

## Test seams

- Public queue seam: `ContactDiscoveryQueue.upsert_cohort`, `enqueue`,
  `inspect`, and `progress`, using the repository's real PostgreSQL test seam.
- Coordinator seam: `scripts.ops.confenge_contact_cycle.run_cycle`, observing
  only returned/raised behavior and the atomic `current` filesystem boundary.

## Dev Agent Record

### Debug log

- Production repro: new cohort metadata declared 7,978 members but received
  zero jobs because all global keys belonged to aborted cohort
  `target-confirmed-auto-20260905T181512Z`.
- The original key and the active partial unique index both omitted `cohort_id`.
  Migration 107 changes only that index shape; it does not update historical
  rows. Enqueue recognizes a legacy key only when it belongs to the requested
  same cohort, preserving retry idempotency across the deployment boundary.
- First real-PostgreSQL run reproduced the concurrent replay race as
  `UniqueViolation` on `uq_contact_discovery_jobs_active_identity`; broadening
  the insert conflict target to `ON CONFLICT DO NOTHING` makes the existing
  scoped lookup return the one logical job. The targeted green result was 6
  passed; the full focused queue/coordinator result was 34 passed.
- An isolated execution of the pre-change global contract returned
  `legacy_second_inserted=False`, `legacy_global_fallback_id=1`, and
  `legacy_global_fallback_cohort=old-aborted` for a second cohort, matching the
  production collision without touching production data.
- Review regressions: the first scoped implementation incorrectly normalized
  stored cohort bytes (`"c"` and `" c"` collided), and migration 107 removed the
  old index before constructing its replacement. The final contract validates
  `strip()` only for emptiness while hashing the exact stored `cohort_id`; fresh
  schema creates `uq_contact_discovery_jobs_active_identity_v2`, and upgrade
  creates that v2 index before dropping the legacy name. A deliberately injected
  create failure leaves the legacy active index present.

### Completion notes

- Contact-cycle atomic-current regression: 8 passed (`tests/test_confenge_contact_cycle.py`).
- PostgreSQL queue/coordinator regression: 36 passed, including cross-cohort,
  cancelled predecessor, same-cohort concurrent replay, legacy replay without
  row mutation, exact legacy-cancelled predecessor, stored-byte cohort identity,
  and fresh/upgrade/reapply/fail-safe migration coverage.
- Broader local suite: 6,806 passed. Its only failure was the unrelated
  cluster-global role rollback test running against a PostgreSQL cluster already
  shared by disposable databases; the exact failed test passed 1/1 after all
  migrations were applied to a new isolated PostgreSQL 16 cluster. The canonical
  clean GitHub run remains mandatory before merge.

### File list

- `docs/stories/story-468-cohort-scoped-contact-idempotency.md`
- `db/migrations/093_contact_discovery_batch.sql`
- `db/migrations/107_contact_discovery_cohort_scoped_identity.sql`
- `scripts/decision_unit_intelligence/batch_queue.py`
- `tests/test_contact_discovery_batch.py`
- `tests/test_confenge_contact_cycle.py`

## Change Log

| Date | Version | Description | Author |
|---|---:|---|---|
| 2026-09-05 | 0.1.0 | Story prepared from explicit founder acceptance criteria; Status: Ready | @sm |
| 2026-09-05 | 0.1.1 | Development started (autonomous TDD); Status: Ready → InProgress | @dev |
| 2026-09-05 | 0.1.2 | Scoped new keys and active identity index by cohort; retained same-cohort legacy replay lookup; PostgreSQL focused regressions green | @dev |
| 2026-09-05 | 0.1.3 | Reviewer fixes: exact stored cohort bytes, v2 index created before legacy removal, failure-preservation and legacy-cancelled regression | @dev |
| 2026-09-05 | 0.1.4 | Local focused/commercial/migration gates complete; isolated rollback triage green; Status: InProgress → InReview | @dev |
