# PR #131 — Human Acceptance Pack (~10 minutes)

**For:** Tiago Sasaki  
**PR:** https://github.com/tjsasakifln/extra-cli/pull/131  
**Rule:** Only you may set `user-acceptance.json` → `ACCEPTED`. Agents will not do it.

**Classification (current):** `READY_FOR_ACTUAL_HUMAN_PRODUCT_REVIEW`  
**Not claimed:** `INTEGRATION_COMPLETE` · `PROJECT_DONE` · `ACCEPTED`

## Frozen release candidate (identity)

| Field | Value |
|-------|--------|
| `run_id` | `live-pack-20260724-220350-da3bee0b` |
| `product_rc_sha` | `be96c8bc8eb2b017e491bfafe8cf99f81e321267` |
| Campaign status | `PENDING_HUMAN` |
| `accepted_by` / `accepted_at` | `null` (must stay null until you accept) |

Later documentation commits on the PR branch **do not** change `product_rc_sha`. Binding always uses the freeze / pack-manifest identity, not `HEAD`.

## GitHub Actions artifact (product for review)

| Item | Value |
|------|--------|
| **Artifact name** | `client-ready-frozen-rc` |
| **Workflow** | CI → job **Client-ready frozen RC artifact** |
| **Classification** | `HUMAN_REVIEW_ARTIFACT` |
| **production_touched** | `false` |
| **soak_touched** | `false` |

### How to download

1. Open the PR: https://github.com/tjsasakifln/extra-cli/pull/131  
2. Open the latest green **CI** run (Checks tab or Actions).  
3. At the bottom of the run page → **Artifacts** → download **`client-ready-frozen-rc`**.  
4. Unzip locally (e.g. `~/Downloads/client-ready-frozen-rc/`).

CLI alternative (after a successful CI run id):

```bash
gh run download <RUN_ID> -n client-ready-frozen-rc -D /tmp/client-ready-frozen-rc
```

### What the artifact contains (only these)

- `executive-report.pdf` — open this  
- `consulting-pack.xlsx` — open this  
- `executive-summary.md`  
- `pack-manifest.json`  
- `checksums.json`  
- `package-reconciliation.json`  
- `claims.json`  
- `non-claims.json`  
- at most one representative dossier (`dossiers/dossier-opp-1.json`)  
- `ARTIFACT-IDENTITY.json` — run_id, product_rc_sha, per-file SHA-256, freeze date, isolation flags, classification  

Binaries are **not** re-versioned in Git. The job never silently regenerates a different RC; if exact freeze bytes are missing it fails with `BLOCKED_MISSING_FROZEN_RC_OUTPUTS`.

## Files Tiago should open

1. **`executive-report.pdf`** (from the artifact)  
2. **`consulting-pack.xlsx`** (from the artifact)  
3. **`executive-summary.md`** + **`ARTIFACT-IDENTITY.json`** (sanity: run_id / product_rc_sha)  
4. **`non-claims.json`** + **`claims.json`** (what we do / do not claim)  
5. **`package-reconciliation.json`** (PDF ↔ XLSX consistency)  
6. This pack + campaign `REVIEW-FOR-TIAGO.md`  

Do **not** review hundreds of dossier files.

## Expected checksums (freeze)

From `user-acceptance.json` → `package_checksums` (must match artifact bytes):

| File | SHA-256 |
|------|---------|
| `executive-report.pdf` | `eb0690fae0a9d5326da1c6dd1d3598640b2ceaf477ffb5de8e51998a4846da9a` |
| `consulting-pack.xlsx` | `ca4ebbe84078e3b4b7e367ab0f443a677f6ca6225b5bc471d835372e41cce741` |
| `pack-manifest.json` | `787fcee3ce3cd0700c665794869e80a89ded04996957703f61a21bfad2070fcf` |
| `executive-summary.md` | `250131255b77183868d096dfd4bd1c569e6169fd28be0add688a3451f43df617` |

## verify-accept (before and after human decision)

### Without local binaries (expected **failure** today)

Git pack/ deliberately omits PDF/XLSX. This must fail closed:

```bash
python -m scripts.ops.client_ready_consulting_cycle verify-accept \
  --out artifacts/campaigns/CLIENT-READY-RECURRING-CONSULTING-CYCLE-01
```

**Expected before accept (no artifact pack-dir):** non-zero exit, JSON with  
`status=BLOCKED_MISSING_FROZEN_RC_OUTPUTS` / `missing_required_frozen_binaries`.

### With downloaded artifact (recommended)

```bash
python -m scripts.ops.client_ready_consulting_cycle verify-accept \
  --out artifacts/campaigns/CLIENT-READY-RECURRING-CONSULTING-CYCLE-01 \
  --pack-dir /path/to/extracted/client-ready-frozen-rc
```

**Expected before accept (with artifact):**

- Exit code **2** (`BLOCKED` — human still pending)  
- `acceptance` = `PENDING_HUMAN`  
- `accepted_by` / `accepted_at` remain null  
- Required binaries present; binding identity uses freeze `run_id` + `product_rc_sha`  
- **Not** `PASS`, **not** `ACCEPTED`

**Expected after you set ACCEPTED** (same command, same freeze checksums):

- Exit code **0** and terminal `PASS` only if:
  - `status=ACCEPTED`
  - `accepted_by` is your real name (not `agent` / `auto` / `system`)
  - `run_id` / `rc_sha` / identity file checksums match the freeze pack
- Agents cannot flip status to ACCEPTED; agent `accepted_by` is demoted to `PENDING_HUMAN`

## How to register ACCEPTED

Edit **only** if you agree with **this** frozen RC (open the PDF/XLSX first):

`artifacts/campaigns/CLIENT-READY-RECURRING-CONSULTING-CYCLE-01/user-acceptance.json`

```json
{
  "status": "ACCEPTED",
  "accepted_by": "Tiago Sasaki",
  "accepted_at": "<ISO-8601 UTC>",
  "notes": "Accepted frozen RC live-pack-20260724-220350-da3bee0b / be96c8bc8eb2b017e491bfafe8cf99f81e321267"
}
```

Keep `package_checksums`, `run_id`, `rc_sha`, and freeze fields **unchanged**.

Then re-run:

```bash
python -m scripts.ops.client_ready_consulting_cycle verify-accept \
  --out artifacts/campaigns/CLIENT-READY-RECURRING-CONSULTING-CYCLE-01 \
  --pack-dir /path/to/extracted/client-ready-frozen-rc
```

## How to register REJECTED / CHANGES_REQUESTED

```json
{
  "status": "REJECTED",
  "accepted_by": "Tiago Sasaki",
  "accepted_at": "<ISO-8601 UTC>",
  "notes": "<why>"
}
```

or `"status": "CHANGES_REQUESTED"` with the required changes in `notes`.

## What the system does (context)

On an **isolated** Postgres snapshot (not VPS/production), it builds consulting cycle **A–E** plus canonical entity linkage (migration 061). Recurrence demo is **labeled deterministic replay**, not two independent live temporal snapshots.

## Limitations / residual risks

- Not LOCAL_READY / VPS_OPERATIONAL / PROJECT_DONE  
- Not live dual-snapshot recurrence  
- Not legal advice; linkage heuristics need human review when not exact  
- CNPJ8 aggregation in intel views can collapse branches (intel only)  
- Stale ACCEPT if freeze checksums change — re-accept required  

## Scope guard

- Do not merge this PR as a substitute for human product review  
- VPS, production, and soak remain untouched by this acceptance flow  
- Final allowed classification while pending: **`READY_FOR_ACTUAL_HUMAN_PRODUCT_REVIEW`**
