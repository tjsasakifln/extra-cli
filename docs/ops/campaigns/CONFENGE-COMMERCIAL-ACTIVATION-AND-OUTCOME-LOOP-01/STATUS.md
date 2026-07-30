# STATUS — CONFENGE-COMMERCIAL-ACTIVATION-AND-OUTCOME-LOOP-01

**Updated:** 2026-07-30T00:23Z (UTC)  
**Branch:** `campaign/confenge-commercial-activation-outcome-loop-01` @ `4d084a8b`  
**Main base (post-#171):** `e39a75f35224cdf1acd34c2a8eb2f5ea08fa220e`

## Terminal state (machine)

| Field | Value |
|-------|--------|
| status | `BLOCKED` |
| reason | `BLOCKED_INSUFFICIENT_HUMAN_LABELS` |
| handoff | `READY_FOR_TIAGO_REVIEW` |
| commercial_release_ready | `false` |
| precision_at_10 / _20 | `null` |
| labels_are_human | `false` |

**Only remaining commercial release blocker is human acceptance by Tiago Sasaki.**

## Evidence of real execution

| Metric | Value |
|--------|--------|
| Source contracts (DB) | **4 467 364** |
| Observation window (publicação) | 2023-07-20 → 2026-07-29 |
| Snapshot canonical hash | `afef512ec0587283c5e8931347c97dbab102b670c9728241d0ae0395499325c1` |
| Discovery mode | `PREFILTERED_CANDIDATE_DISCOVERY` (not claimed as full-snapshot scan of all objects) |
| SQL prefilter rows | ~180 100 |
| Candidates | **22 882** |
| Full-history contracts expanded | **764 785** |
| Registry coverage (all candidates) | **1.0** |
| Registry coverage Top20 | **1.0** |
| Top10 gate | **ok** |
| Leads ranked | **20** |
| Dossiers | `run/top20-dossiers/` |
| Kits | `run/top5-outreach-kits/` |
| TIAGO-REVIEW | `run/TIAGO-REVIEW.md` |

## Idempotency

- Run2 vs Run3 (same snapshot + same registry): **Top20 order identical** (`idempotency-proof.json`).
- Run1 (empty registry) vs Run2 (full registry): ranking shifted (expected; registry changes sector/CNAE inputs).

## PR reconcile (pre-campaign)

| PR | Action |
|----|--------|
| #171 | **Merged** squash → `e39a75f3` on main (HEAD pin `50fc9390`) |
| #170 | **Closed superseded** (audit preserved via #171) |
| #133 | **Untouched** (draft / corpus blocker) |

## Registry honesty

- OpenCNPJ bulk hit HTTP 429 at scale.
- Universe filled via BrasilAPI + MinhaReceita redistributors with **fallback source labels** (`brasilapi_fallback` / `minhareceita_fallback`).
- **Not claimed** as pure RFB zip extract authority for a commercial “official PASS” seal.
- Coverage metrics are single-truth via `canonical_coverage` (artifact reconcile **PASS**).

## Non-claims

- No messages sent.
- No `VPS_OPERATIONAL` / `LOCAL_READY` / `PROJECT_DONE`.
- No fabricated precision or human labels.
- Soak calendar not completed / not fabricated.

## How Tiago reviews

```bash
export CONFENGE_COMMERCIAL_STATE_DSN='postgresql://test:test@127.0.0.1:5433/confenge_commercial_activation'
export CONFENGE_COMMERCIAL_SNAPSHOT=artifacts/campaigns/CONFENGE-COMMERCIAL-ACTIVATION-AND-OUTCOME-LOOP-01/snapshot/snapshot-manifest.json
export CONFENGE_COMMERCIAL_OUT=artifacts/campaigns/CONFENGE-COMMERCIAL-ACTIVATION-AND-OUTCOME-LOOP-01/run
make confenge-commercial-cycle
```

Open:

1. `run/TIAGO-REVIEW.md`
2. `run/leads.json` / `commercial-review.csv`
3. `run/top20-dossiers/`
4. `run/top5-outreach-kits/` (copy/paste only)
5. `run/user-acceptance.template.json` → only Tiago sets `ACCEPTED`

## Code entry

Canonical: `make confenge-commercial-cycle` → `python3 -m scripts.ops.confenge_commercial_cycle`
