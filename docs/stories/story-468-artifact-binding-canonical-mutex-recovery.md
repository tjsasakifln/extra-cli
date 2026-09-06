# #468 — Recover artifact binding and canonical commercial mutex

Status: Ready for Review

## Story

As the operator of founder-authorized commercial cycles, I need an unambiguous
binding between versioned code, evidence, deployment and the running process,
and one atomic execution authority shared by every commercial-cycle entrypoint,
so an invalid checkpoint cannot be executed concurrently or resumed through an
alternate state path.

## Authority and scope

The founder permanently invalidated checkpoint
`96f1bea8fa5f2a44d9563943f9875b350da3ccc4` for new cycles and authorized only
technical recovery. No C1/C2, contact/feed promotion, dispatch, SMTP or issue
closure is authorized by this story.

Scope is limited to the two causal defects: stale/non-authoritative artifact
binding after protected code changes, and the lack of one real mutex at the
shared commercial operation boundary. PNCP remains asynchronous telemetry.
Classification, targeting, population, transport and pipeline architecture are
unchanged.

## Acceptance criteria

1. Root cause identifies why the default artifact verifier cannot bind the
   authorized SHA and the versioned recovery produces `ARTIFACT_BINDING=PASS`.
2. All manual, CLI, systemd/timer, scheduler and worker entrypoints capable of
   starting or restarting a commercial operation are inventoried and covered.
3. Two concurrent starts yield one authority; the loser fails before mutation
   or promotion and an authorized retry does not create a second cycle.
4. The canonical mutex is atomic, fail-closed and observable with operation,
   owner, acquisition time and safe live/stale diagnosis. Recovery never takes
   over a live lock.
5. A crashed/aborted operation is recovered explicitly and its cohort is never
   reused.
6. Adversarial tests prove no partial contact/feed promotion, last-good feed
   preservation, paused dispatch and `SMTP_DELTA=0`.
7. The minimal code PR is adversarially reviewed and merged, followed by a
   canonical artifact-only rebind, immutable deployment and proof that
   `origin/main == DEPLOYED_SHA == RUNNING_SHA`.
8. Stop before C1; leave #468 open and return the exact checkpoint candidate
   SHA only after all recovery proofs pass.

## Tasks

- [x] Reproduce and root-cause artifact binding and concurrent execution at
      public boundaries. (AC 1, 3)
- [x] Inventory every production and operator entrypoint and identify the
      smallest shared mutation boundary. (AC 2)
- [x] Add adversarial regressions before implementing the mutex/recovery fix.
      (AC 3–6)
- [x] Implement the minimal canonical authority and aborted-cohort behavior.
      (AC 2–5)
- [x] Run focused, commercial, full and repository governance gates without
      waivers or threshold changes. (AC 6–7)
- [ ] Review adversarially, merge, rebind artifacts, deploy and collect live
      proof without starting a commercial cycle. (AC 1, 7–8)

## Dev Agent Record

### Debug log

- `verify_confenge_artifact_binding --head 96f1bea8...` deterministically fails:
  `result.json` and `queue-summary.json` remain bound to `e9858a14...`, while
  #571 changed protected `batch_queue.py`.
- Multiple independently named systemd/transient contact-cycle units accepted
  arbitrary state paths after the invalid checkpoint. Each unit could create a
  fresh cohort because existing locks are stage-local and ephemeral.

### Completion notes

- Artifact root cause includes both stale five-field result/queue binding after
  #571 and missing freeze discovery coverage for mutating CLIs. The recovery
  requires code integration first and artifact-only rebind second. Main enforces
  linear history, so the code PR is squash-merged; the second PR binds that
  integrated SHA, and its own squash adds only artifacts while leaving the bound
  SHA in main ancestry.
- Canonical authority uses one host path, nonblocking kernel `flock`, atomic
  fsynced state, durable terminal history, process identity and explicit stale
  recovery. No naming convention selects the lock domain.
- Contact resumes only `RUNNING` state from the same operation. Every direct
  enqueue/retry/resume/publish/export requires inherited live contact authority.
- Focused matrix: 204 passed. Full suite: 6,604 passed, 380 skipped, 11
  deselected. The first full attempt exposed an empty local
  `sc_public_entities`; the canonical public seed fixed the test prerequisite,
  and the unmodified suite then passed.
- CodeRabbit CLI required interactive OAuth and was unavailable; manual
  adversarial review found and fixed durable-history and cohort-name bypasses.
- The canonical deploy previously always used `enable --now` for commercial
  timers. `--preserve-timer-state` now pins and verifies the immutable release
  without changing a founder-paused schedule, failing on concurrent state drift.
- The live inventory found the versioned DUI worker template outside the
  immutable pin set. It is now pinned with the rest of the mutating chain so a
  post-deploy `RUNNING_SHA` cannot hide old worker code.
- Merge, artifact-only rebind, deployment and live-host proof remain the final
  unchecked task. No C1/C2 was run.

### File list

- `DOD.md`
- `deploy/confenge/pin_release.py`
- `deploy/confenge/cut_release.sh`
- `deploy/systemd/extra-confenge-{target-fit-refresh,target-fit-reconcile,contact-cycle,feed-cycle}.service`
- `docs/architecture/adr/ADR-039-confenge-pncp-outbound-decoupling.md`
- `docs/ops/confenge-commercial-plane-authority.md`
- `docs/ops/handoff-2026-09-05-468-artifact-binding-canonical-mutex-recovery.md`
- `docs/stories/story-468-artifact-binding-canonical-mutex-recovery.md`
- `scripts/confenge_activation/cli.py`
- `scripts/confenge_target_fit/{cli,hook_after_datalake}.py`
- `scripts/decision_unit_intelligence/cli.py`
- `scripts/ops/{check_confenge_commercial_plane,confenge_commercial_mutex,confenge_commercial_plane,confenge_contact_cycle,confenge_feed_cycle,confenge_frozen_inputs}.py`
- `tests/test_confenge_{commercial_mutex,commercial_plane,contact_cycle,release_pin}.py`
- `tests/test_contact_discovery_batch.py`
- `tests/test_source_maintenance_health.py`

## Change Log

| Date | Version | Description | Author |
|---|---:|---|---|
| 2026-09-05 | 0.1.0 | Story prepared from explicit founder recovery authority; Status: Ready | @sm |
| 2026-09-05 | 0.1.1 | Development started (autonomous diagnosis/TDD); Status: Ready → InProgress | @dev |
| 2026-09-06 | 0.2.0 | Minimal mutex/binding recovery implemented and full suite green; Status: InProgress → Ready for Review | @dev |
