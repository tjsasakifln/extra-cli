# Story: Never-worked VALIDATE promote-or-defer (#252 #254 #255 #260 #334 #335)

**Status:** InProgress
**Branch:** `feat/never-worked-validate-measure`
**Base:** `origin/main` (includes #411 promote-or-defer consumer)
**Capability:** in-repo promote-or-defer measurement only

## Goal

Record promote-or-defer decisions for the six remaining never-worked
VALIDATE issues, consumed from the existing #346 ranking. No adapters.

## Locked issues

1. #252 Compras.gov OCDS
2. #254 DOE-SC
3. #255 TCE-SC
4. #260 PCP
5. #334 Joinville
6. #335 e-Publica

## Scope

### IN

- Extend `scripts/coverage/promote_or_defer.py` ISSUE_SOURCES
- Tests that drive `load_ranking` / `decide_all` / CLI `main`
- Preserve seed evidence; record ranking hash

### OUT

- New crawler/adapter modules
- Coverage engineering or live ops
- Storage/backup (#271 #277) — other PR
- Auto-close of GitHub issues

## Residual

Rewriting the issue to a measured residual or closing it still needs the
ranking evidence plus a human promotion decision.
