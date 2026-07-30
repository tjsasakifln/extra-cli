# STATUS — CONFENGE-COMMERCIAL-ACTIVATION-AND-OUTCOME-LOOP-01

**Updated:** 2026-07-30T01:17Z (UTC)  
**Main (integrated):** `7243b87ff8158a8026ccba6c4690a42b09884b07` (#172)  
**Branch (PR B closeout):** `campaign/confenge-activation-pr-b`

## Terminal state (machine)

| Field | Value |
|-------|--------|
| campaign machine status | `PASS_ACTIVATION` |
| commercial status | `BLOCKED` |
| reason | `BLOCKED_INSUFFICIENT_HUMAN_LABELS` |
| handoff | `READY_FOR_TIAGO_REVIEW` |
| commercial_release_ready | `false` |
| precision_at_10 / _20 | `null` |
| labels_are_human | `false` |
| soak_non_interference | **PASS** |

**Only remaining commercial release blocker is human acceptance by Tiago Sasaki.**

## Evidence of real execution (post-merge on integrated SHA)

| Metric | Value |
|--------|--------|
| Source contracts (DB) | **4 467 364** |
| Observation window (publicação) | 2023-07-20 → 2026-07-29 |
| Snapshot canonical hash | `afef512ec0587283c5e8931347c97dbab102b670c9728241d0ae0395499325c1` |
| Discovery mode | `PREFILTERED_CANDIDATE_DISCOVERY` |
| Candidates | **22 882** |
| Full-history contracts expanded | **764 785** |
| Registry coverage (all / Top20) | **1.0 / 1.0** |
| Top20 post-merge ≡ pre-merge | **true** |
| Run ID | `cl-20260730T010931Z-1b0e4da2` |
| Signals catalog | **15** |

## PR reconcile

| PR | Action |
|----|--------|
| #171 | Merged → `e39a75f3` |
| #172 | **Merged** squash → `7243b87f` (PR A capability) |
| PR B | Closeout docs + post-merge/soak evidence (this branch) |
| #133 | **Untouched** |

## Non-claims

- No messages sent.
- No `VPS_OPERATIONAL` / `LOCAL_READY` / `PROJECT_DONE`.
- No fabricated precision or human labels.
- No VPS deploy of integrated SHA in this campaign.
- No bulk DOD `[x]` without controller ACCEPTED + human gates.

## How Tiago reviews

```bash
export CONFENGE_COMMERCIAL_STATE_DSN='postgresql://test:test@127.0.0.1:5433/confenge_commercial_activation'
export CONFENGE_COMMERCIAL_SNAPSHOT=artifacts/campaigns/CONFENGE-COMMERCIAL-ACTIVATION-AND-OUTCOME-LOOP-01/snapshot/snapshot-manifest.json
export CONFENGE_COMMERCIAL_OUT=artifacts/campaigns/CONFENGE-COMMERCIAL-ACTIVATION-AND-OUTCOME-LOOP-01/run-post-merge
make confenge-commercial-cycle
```

Open:

1. `run-post-merge/TIAGO-REVIEW.md` (or slim `post-merge/evidence-slim/TIAGO-REVIEW.md`)
2. `post-merge/evidence-slim/top20-slim.json`
3. Local `run-post-merge/top20-dossiers/` + `top5-outreach-kits/`
4. `user-acceptance.template.json` → only Tiago sets `ACCEPTED`

## Code entry

Canonical: `make confenge-commercial-cycle` → `python3 -m scripts.ops.confenge_commercial_cycle`
