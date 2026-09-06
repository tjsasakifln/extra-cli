# #468 — Recovery handoff: artifact binding + canonical mutex

Status: IN PROGRESS — recovery only; C1/C2 forbidden.

## Root causes

Artifact binding failed at `96f1bea8...` because #571 changed protected
`scripts/decision_unit_intelligence/batch_queue.py`, but regenerated only freeze
marks/manifest. The default verifier obtains its five authoritative SHA fields
from `result.json` and `queue-summary.json`; both remained bound to `e9858a14...`.
Generating a binding inside a code PR is also unsafe under the repository's
squash merge practice: the branch SHA is not an ancestor of the resulting main.
The deterministic recovery is code merge first, then a separate artifact-only
rebind to that integrated parent SHA.

The protected-input discovery also omitted the mutating target-fit, activation
and DUI CLIs, so it could not prove the exact execution surface even after a
nominal rebind. They are now explicit freeze seeds; the discovered protected
set includes every canonical mutex boundary.

Concurrency was possible because the four production stages used four distinct,
process-lifetime `flock` files and contact accepted arbitrary state paths.
There was no durable operation identity spanning stages, no completed-stage
deduplication and no safe live/stale owner record. Contact additionally resumed
every non-`COMPLETED` state, including `FAILED`, reusing an aborted cohort.

## Minimal correction

- One kernel `flock` boundary plus atomic durable
  `confenge.commercial.authority.v1` record for all mutating entrypoints.
- Cycle scope reserves one operation across the four ordered stages; timer scope
  preserves ADR-039 independent cadence.
- PID start ticks + boot ID prevent PID-reuse mistakes; no automatic stale
  takeover. Explicit stale recovery requires a dead owner and exact operation ID.
- Completed retry stops before mutation. `FAILED`/different contact operation
  generates a new cohort; only `RUNNING` from the same operation can resume.
- Every direct enqueue/retry/resume/publish/export requires descent from the
  active contact owner, independent of cohort naming. Direct feed publication
  acquires the feed boundary.

## Evidence ledger

- Focused adversarial/contract matrix: `204 passed`.
- Full repository suite: `6604 passed, 380 skipped, 11 deselected`.
- `check_confenge_commercial_plane`: PASS including `CANONICAL_MUTEX=PASS`.
- Generated-artifact policy and draft reviewability: PASS.
- Real incident evidence: an independently named static systemd unit restarted
  the invalidated 96f cycle with an arbitrary state path and created cohort
  `target-confirmed-auto-20260906T020732Z`. It was stopped, its 7,978 jobs were
  contained to 3,960 succeeded + 4,018 cancelled, and its unit file was moved
  recoverably to `/var/lib/extra-consultoria/incidents/468/quarantined-units/`.
  It never reached contact/feed promotion.
- PRs, merged SHA, artifact rebind, deployment equality, real-host mutex/stale
  proof, current feed, dispatch and SMTP delta remain pending. This document
  does not authorize a commercial cycle and must stop before C1.
