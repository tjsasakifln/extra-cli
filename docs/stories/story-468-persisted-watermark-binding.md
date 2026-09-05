# #468 — Preserve persisted watermarks in commercial binding

Status: Ready for Review

## Scope and authority

The founder authorized the smallest causal correction after the REV-05 Phase A
abort at `d2395642be0c91c21a2216dff005dfee306aecd7`. PNCP health is telemetry;
commercial bindings must identify persisted Data Lake state. The old checkpoint
is invalid for changed code. No cycles until a new founder checkpoint is posted.

This fix changes only invalid binding provenance. Classification, target-fit
membership, coverage, commercial policy, SMTP and dispatch are outside scope.
No data-release features or other PR patches belong in this change.

## Acceptance

- Reproduce a FRESH telemetry observation replacing persisted CDC and decision
  watermarks before the fix; preserve both persisted values after the fix.
- Adversarial tests cover telemetry before/equal/after the full reconcile,
  absent/malformed telemetry, and invalid Data Lake states without weakening gates.
- Artifact binding verifier and commercial-plane preflights pass; required
  GitHub checks actually succeed on the final PR HEAD before merge.
- Deploy the merged SHA immutably, recheck runtime provenance and binding,
  preserve the feed and paused outbound, and return the exact new checkpoint text.
- #468 acceptance remains pending two wholly new post-checkpoint cycles.

## File ownership

- Implementation: `scripts/confenge_outreach_pipeline/pipeline.py` and directly
  affected regression tests.
- Coordinator: DOD, ADR-039, this story, operational handoff, PR and deployment.

## Validation

Red reproduced telemetry replacement of persisted CDC and acceptance of absent
CDC. Green: 146 focused regression tests plus 206 commercial tests; repository
Ruff and canonical mypy selections succeed. Commercial-plane preflight including
host OnSuccess readback succeeds. CI, merge, deployment and a new founder
checkpoint remain pending; this story does not accept #468.
