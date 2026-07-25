# PR #131 — Human Acceptance Pack (~10 minutes)

**For:** Tiago Sasaki  
**PR:** https://github.com/tjsasakifln/extra-cli/pull/131  
**Rule:** Only you may set `user-acceptance.json` → `ACCEPTED`. Agents will not do it.

## What the system does

On an **isolated** Postgres snapshot (not VPS/production), it builds a **consulting cycle A–E**:

- **A** — opportunity / market framing from national contracts intelligence layers  
- **B** — agency / organ ranking and context  
- **C** — windowed hits / workspace views  
- **D** — competitor / supplier panels from **observed historical winners** only  
- **E** — package export (PDF/XLSX/CSV/JSON) + optional dossiers  

Plus **canonical entity linkage** (migration 061): auditable opportunity → organ → contract → supplier links with exact / deterministic / heuristic / ambiguous / unresolved.

## Deliverables (regenerate; not all kept in Git)

| Deliverable | How to obtain |
|-------------|----------------|
| Executive PDF / XLSX pack | Run pack on isolated DSN; see campaign `REPRODUCIBLE-OUTPUTS.md` |
| Checksums freeze | `artifacts/campaigns/CLIENT-READY-RECURRING-CONSULTING-CYCLE-01/pack/checksums.json` |
| Claims / non-claims | `claims.json`, `non-claims.json` |
| Linkage quality | `linkage-quality.json` |
| Reconciliation | `package-reconciliation.json` |

## Data used

- Public PNCP-derived contracts in an **isolated local** database (campaign RC ports 5436/5438/5439).  
- **Not** production VPS.  
- Recurrence demo is **labeled deterministic replay**, not two independent live temporal snapshots.

## Main metrics to glance at

1. `isolation.json` / run notes: `production_touched=false`, soak untouched  
2. `linkage-quality.json` — unresolved/ambiguous rates  
3. `package-reconciliation.json` — PDF vs XLSX vs JSON consistency  
4. `non-claims.json` — what we explicitly do **not** claim  
5. CI: all required jobs green on the PR  

## Sample review set (maximum)

1. This file + `REVIEW-FOR-TIAGO.md` (campaign)  
2. `user-acceptance.json` (status + freeze checksums)  
3. `non-claims.json` + `claims.json`  
4. `package-reconciliation.json`  
5. `artifacts/integration/PR-131-CTO-REVIEW.md`  
6. `artifacts/integration/PR-131-FINAL-GATE.json`  
7. One regenerated PDF **or** XLSX (local/CI artifact — not required in Git)

Do **not** review hundreds of dossier files.

## Limitations

- Not LOCAL_READY / VPS_OPERATIONAL / PROJECT_DONE  
- Not live dual-snapshot recurrence  
- Not legal advice; linkage heuristics need human review when not exact  
- Experimental follow-on packs (#133) are separate  

## Residual risks

- CNPJ8 aggregation in intel views can collapse branches (intel only)  
- Heuristic links may be wrong — use review queue  
- Stale ACCEPT if freeze checksums change — re-accept required  

## Exact commands (local isolated)

```bash
export LOCAL_DATALAKE_DSN='postgresql://USER:PASS@127.0.0.1:5439/DB'  # isolated only
python -m scripts.ops.apply_migrations --dsn "$LOCAL_DATALAKE_DSN"
# campaign Makefile targets for client-ready pack (see Makefile / campaign docs)
python -m scripts.ops.check_generated_artifacts_policy --base origin/main
pytest tests/unit/test_generated_artifacts_policy.py -q
```

## How to register ACCEPTED

Edit **only** if you agree with the frozen RC:

`artifacts/campaigns/CLIENT-READY-RECURRING-CONSULTING-CYCLE-01/user-acceptance.json`

```json
{
  "status": "ACCEPTED",
  "accepted_by": "Tiago Sasaki",
  "accepted_at": "<ISO-8601 UTC>",
  "notes": "Accepted frozen RC <run_id> / <rc_sha>"
}
```

Keep `package_checksums` and freeze fields unchanged unless you intentionally re-freeze.

## How to register REJECTED

```json
{
  "status": "REJECTED",
  "accepted_by": "Tiago Sasaki",
  "accepted_at": "<ISO-8601 UTC>",
  "notes": "<why>"
}
```

## How to register CHANGES_REQUESTED

```json
{
  "status": "CHANGES_REQUESTED",
  "accepted_by": "Tiago Sasaki",
  "accepted_at": "<ISO-8601 UTC>",
  "notes": "<list of required changes>"
}
```

Commit on the PR branch or comment on the PR with the same decision.  
**Agents must not flip status to ACCEPTED.**
