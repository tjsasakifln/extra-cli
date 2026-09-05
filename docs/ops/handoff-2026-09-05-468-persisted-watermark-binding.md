# #468 — persisted watermark binding correction

Status: VERIFIED locally; CI/merge/deploy pending. This is an intermediate gate
in the same REV-05 campaign, not incident acceptance.

## Cause and scope

At base `d2395642be0c91c21a2216dff005dfee306aecd7`, the artifact SHA verifier
passes. The runtime defect is separate: `_published_target_fit_snapshot`
replaces persisted CDC and per-decision watermarks with PNCP `source_observed_at`
when health is FRESH and the full reconcile timestamp is at least that recent.
The exporter then binds the result to telemetry without comparing it with CDC.
Existing tests encoded this rewrite and must instead enforce the persisted
binding required by DOD, ADR-039 and the founder checkpoint.

The previous read-only probe on real ec-prod state, with explicitly synthetic
health and no publication, returned `2026-09-05T18:12:44.301337+00:00` instead
of persisted `2026-09-05T05:24:26.408149+02:00`. The invalid rewrite was also
confirmed by an independent read-only code trace.

The smallest correction removes telemetry re-stamping and rejects absent CDC
before the exporter can substitute publication time. Classification,
membership, coverage thresholds, queue gates and outbound policy are unchanged.
No acquisition, data-release features, SMTP or dispatch changes are included.

## Evidence and validation

Test-first reproduction:

- `python3 -m pytest tests/test_pncp_outbound_decoupling.py tests/confenge_outreach_pipeline/test_pipeline.py -q --no-cov --tb=short -x`
  failed on the old FRESH-before-reconcile path: returned observation
  `2026-08-25T02:42:00Z`, expected persisted CDC `2026-08-24T03:26:43Z`.
- A missing-CDC regression failed before adding the guard (`DID NOT RAISE`);
  the old exporter fallback otherwise minted `generated_at` as the watermark.
- `python3 -m pytest tests/test_confenge_commercial_plane.py -k telemetry_watermark_restamp -q -o addopts= --tb=short`
  failed twice before the preflight correction: the old preflight allowed both
  CDC and decision-watermark replacement under FRESH.

After correction: 146 focused tests and 206 commercial tests passed with no
skips; repository Ruff and canonical mypy selections succeeded. Preflight
including host OnSuccess readback and campaign-plan linter succeeded.
The FRESH matrix actually passes observations before/equal/after full reconcile,
timezone-naive, missing and malformed timestamps; persisted CDC and decision
watermarks remain unchanged. Missing/blank CDC fails closed. Existing population,
coverage, unresolved-queue and rejected-publication tests still pass.

No changes to the artifact verifier, freeze policy or historical evidence are
needed: neither corrected runtime file belongs to the discovered frozen input
set. Verify the existing artifact binding again at the committed and deployed
SHA; do not claim historical freeze validation proves new runtime behavior.

The final PR/deployment record must provide exact HEAD, real required checks,
merged SHA, verifier result and the read-only runtime binding probe. Automated
CodeRabbit review was unavailable (CLI signed out); the delegated reviewer also
hit its usage limit. Neither is claimed as a completed review. Local code review
and actual repository gates remain required.

## Resume gate

The old checkpoint `5553292824` is invalid for changed code. After verified
merge/deploy, the founder must personally post a new checkpoint in #468 bound
to the deployed SHA. Until then CYCLE_1 and CYCLE_2 remain
`WAITING_NEW_FOUNDER_CHECKPOINT`; do not initiate commercial jobs or enable timers.

Previous aborted cohort: `target-confirmed-auto-20260905T181512Z`;
919 succeeded and 7059 cancelled, no jobs remaining active. Never reuse it as
acceptance evidence. Existing contact-cycle state still references this aborted
cohort; a future authorized execution must use fresh cycle state through the
existing `--state` option, not resume that cohort.

Preserve SHADOW, paused dispatch and auto-send=false. The previous feed manifest
SHA256 is `41faa0c3028f55c90f6e0865bec33bf765c4146d25ed14771696715a11f8e298`.
SMTP delta must remain zero. Backout is the prior immutable release pin;
no database migration is involved.
