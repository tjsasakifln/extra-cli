# TIAGO-REVIEW — CONFENGE commercial activation

**Authority:** only Tiago Sasaki may set ACCEPTED.  
**Updated:** 2026-07-30T04:30:00Z

## Package location

Primary (VPS live): `artifacts/campaigns/CONFENGE-COMMERCIAL-ACTIVATION-AND-OUTCOME-LOOP-01/vps-live/package/`

Also: `artifacts/.../review-package/`

## Contents

1. Top 20 dossiers (`top20-dossiers/`)
2. Top 5 outreach kits (`top5-outreach-kits/`) — **manual send only**
3. Holdout calibration (`holdout-review.json` / `.csv` / `.md`) — ≥10 near-cut + ≥10 excluded/negative
4. `user-acceptance.template.json` — leave PENDING until you decide
5. Queue / coverage summaries

## Critical limitation (read first)

- **Official RFB cadastro on Top10 does not pass §8.1** on the VPS package (retrospective gate: 10/10 failures; many dossiers show CNAE/situação/registry as NOT_AVAILABLE).
- Sector label `CONFIRMED_ENGINEERING` alone is **not** commercial publication quality.
- `official_registry_coverage` ≈ **0.029** — not 1.0.
- Treat this package as **calibration / review**, not commercial release.

## Your checklist

- [ ] Spot-check Top10 for real engineering/construction fit
- [ ] Spot-check 2–3 dossiers for contract evidence
- [ ] Optional: label holdout rows (near-cut / negatives)
- [ ] Kits: copy/paste only if you choose to contact — no automation
- [ ] Acceptance template: ACCEPTED only if you accept despite residual technical limits, or wait for RFB bulk + re-cycle

## Non-claims

Do not treat agent output as human labels. precision@k stays null until you label.
