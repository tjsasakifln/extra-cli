# CLAIM_POLICY re-freeze note

Prior freeze: `345968bf0fac29105f3a064e44db4dbe69d5768d`
Prior `confenge_final_status` build SHA: `b72b7f0b1a4a368f87fcc38c3c2a0d2490fb9177`
New freeze / executed SHA: `8fc01192c499fc0d1616ded3c6ae8e84c56ca66a`

## Why a re-freeze was required

`story-outreach-claim-policy-01` (PR #532) adds `scripts/confenge_claim_policy/`
and rebinds two already-frozen modules. `discover_frozen_input_paths` performs a
transitive local-import closure under `scripts/`, so the new package and its
import closure become protected inputs automatically. Leaving the freeze at
`345968bf` would make `evaluate_post_freeze_diff` report
`BLOCKED_PROTECTED_INPUT_CHANGED` against the merged tree.

The freeze artifacts were **regenerated** with
`scripts.ops.confenge_code_freeze mark-final-integrity-freeze` and
`scripts.ops.confenge_final_status build`. No freeze JSON was hand-edited.

## What was NOT re-executed — explicit

Commercial discovery, scoring, ranking, offer sensitivity, corpus and registry
logic were **not re-run** for this freeze. Local commercial evidence gates
remain PASS from the prior campaign execution. Real-data CI remains
`NOT_EXECUTED` (DSN secrets absent) and is reported honestly.
`terminal_reason` stays `BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE`; human
blockers are unchanged. This re-freeze changes SHA binding and input digests
only — it makes no new claim about commercial results.

Same posture and precedent as `integrity-truth-re-freeze-note.md`.

## Manifest delta at this re-freeze

Inputs 162 -> 167. Zero removals.

Added (5):
- `scripts/confenge_claim_policy/__init__.py` — story
- `scripts/confenge_claim_policy/policy.py` — story
- `scripts/contracts_truth.py` — pulled in by import closure
- `scripts/crawl/observation_lineage.py` — transitive import closure
- `scripts/confenge_activation/commercial_authority.py` — pre-existing `main` drift

Rebound (9): `confenge_account_intelligence/message_spine.py` and
`confenge_contact_resolution/send_readiness.py` belong to this story. The other
seven (`confenge_activation/publish.py`, `confenge_target_fit/store.py`,
`decision_unit_intelligence/batch_projection.py`, `ops/confenge_contact_cycle.py`,
`ops/confenge_feed_cycle.py`, `warmbly_bridge/__init__.py`,
`warmbly_bridge/export.py`) plus `commercial_authority.py` are drift from work
**already merged into `main`** between `345968bf` and `2f0761e4` — every one was
verified to have commits in `345968bf..origin/main`. None originate from the
story branch. The freeze catches up to `main`; the story does not claim them.

## Merge order

`origin/main` is a strict ancestor of `8fc01192`, so the merged tree equals the
`8fc01192` tree and this freeze is valid post-merge. Merge PR #532 **first**,
then this PR, both with a **merge commit** — a squash orphans `8fc01192` and
reddens the freeze gates on `main` (precedent `57d5efbb` / #457).
