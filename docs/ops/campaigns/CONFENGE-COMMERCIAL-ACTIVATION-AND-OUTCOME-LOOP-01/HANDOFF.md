# HANDOFF — CONFENGE-COMMERCIAL-ACTIVATION-AND-OUTCOME-LOOP-01

**To:** Tiago Sasaki (sole commercial acceptance authority)  
**From:** Campaign closeout (PR B)  
**Date (UTC):** 2026-07-30  

## One-line status

Machine commercial loop on **full history is live on main** (`7243b87f`); **only your human review/accept blocks** `commercial_release_ready`.

## What you get

| Artifact | Path |
|----------|------|
| Review pack | `artifacts/.../run-post-merge/TIAGO-REVIEW.md` (local; re-run if missing) |
| Top20 slim (committed) | `artifacts/.../post-merge/evidence-slim/top20-slim.json` |
| Acceptance template | `.../post-merge/evidence-slim/user-acceptance.template.json` |
| Soak proof | `.../post-merge/soak-non-interference.json` (**PASS**) |
| Final report | `docs/ops/campaigns/.../FINAL-REPORT.md` |

Heavy dossiers/kits/HTML live under local `run-post-merge/` (gitignored bulk). Re-generate with the cycle command below if the worktree is clean of that folder.

## Reproduce (local isolated DB)

```bash
export CONFENGE_COMMERCIAL_STATE_DSN='postgresql://test:test@127.0.0.1:5433/confenge_commercial_activation'
export CONFENGE_COMMERCIAL_SNAPSHOT=artifacts/campaigns/CONFENGE-COMMERCIAL-ACTIVATION-AND-OUTCOME-LOOP-01/snapshot/snapshot-manifest.json
export CONFENGE_COMMERCIAL_OUT=artifacts/campaigns/CONFENGE-COMMERCIAL-ACTIVATION-AND-OUTCOME-LOOP-01/run-post-merge
make confenge-commercial-cycle
```

Requires the activation DB still populated (~4.47M `pncp_supplier_contracts` on port 5433).

## Your actions (only remaining commercial blockers)

1. Review Top20 for profile fit (engineering/construction/design — not pure materials without service).  
2. Spot-check dossiers for contract evidence links.  
3. Use outreach kits as **manual** copy/paste only — **do not** auto-send.  
4. If usable: set acceptance template to `ACCEPTED` with your name/date.  
5. If not: document `REJECTED` reasons; machine will stay `BLOCKED` honestly.  

## Do not claim

- `VPS_OPERATIONAL` / `LOCAL_READY` / `PROJECT_DONE`  
- Precision@k without your labels  
- RFB zip-only registry authority for this run  
- That soak calendar “7 days” completed (not claimed; non-interference only)

## Optional ops follow-up (not required for human review)

- Deploy main `7243b87f` to Netcup **without** resetting soak timers.  
- Keep PR #133 draft untouched until public corpus exists.

## Contacts / authority

| Role | Owner |
|------|--------|
| Commercial accept | Tiago only |
| Machine cycle | `make confenge-commercial-cycle` |
| Freeze/gates CONFENGE READY-01 | unchanged freeze tip `f68882ed` (code); evidence lag free |
