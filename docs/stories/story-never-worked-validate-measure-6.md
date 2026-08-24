# Story: Never-worked VALIDATE promote-or-defer (#252 #254 #255 #260 #334 #335)

**Status:** Ready for Review
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

## Evidence boundary

- The versioned corpus contains 11 rows, not the unavailable real 197-row XLS.
- Joinville (#334) and e-Publica (#335) each have one measured ranked miss and
  remain below the material threshold.
- Compras.gov OCDS (#252), DOE-SC (#254), TCE-SC (#255), and PCP (#260) have no
  ranked row in this corpus. Their metrics are serialized as `null`, never as a
  measured zero; `DEFER` means insufficient promotion evidence.
- No issue is closed and no operational or coverage claim is promoted here.
