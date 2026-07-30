# Spec: DOD Low-Hanging Boundaries & Evidence

**Feature ID:** `900-dod-low-hanging-boundaries-evidence`  
**Campaign:** `DOD-LOW-HANGING-BOUNDARIES-AND-EVIDENCE-01`  
**Capability:** `dod_scope_boundaries_and_existing_evidence`

## Problem

Many open `DOD.md` items are already true in the repository (negative scope, governance policy modules, dual-coverage semantics, CLI usability) but remain unchecked because no fail-closed, per-item evidence harness binds them to proofs.

## What “low-hanging” means

An item is low-hanging only when **all** of:

1. Currently open in `DOD.md` / controller manifest  
2. No human decision wait  
3. No multi-day soak  
4. No 95% coverage/recall target  
5. No unstable external source  
6. No new dataset  
7. No VPS mutation  
8. No commercial campaign collision  
9. Provable via existing code, small test, static audit, or executable docs  
10. No material product scope expansion  
11. Touches at most one central capability  

## Families

| Family | Focus |
|--------|--------|
| A | DOD governance / states / evidence types |
| B | Negative product scope (excluded capabilities) |
| C | CLI / single-user UX |
| D | Dual coverage truth semantics (code-ready) |
| E | Backup/restore only if complete pre-existing evidence |

## Minimum evidence strength

Each `PROVEN` item requires an individual proof object: definition, surfaces, commands, exit codes, findings, false-positive handling, conclusion, limitations, unique evidence hash. Generic “grep found nothing” across many items is invalid.

## Negative proof rules

- Documentation of a prohibition ≠ implementation  
- Disclaimer / fixture / test ≠ product surface  
- “aditivo” admin monitoring ≠ physical execution addendum management  
- Local HTML/CLI ≠ public multi-tenant interface  
- Transitive mention ≠ production dependency  

## Non-collision

- Reserved Spec Kit range `900+`  
- Dedicated worktree/branch  
- Protected paths (commercial, crawl, VPS, Makefile, README, DEVELOPMENT, DOD.md in PR A)  

## PR strategy

1. **PR A** — harness, config, tests, campaign docs (no DOD accept)  
2. **PR B** — controller start→verify→accept per proven item after main re-proof  

## Terminal states

`PASS_LOW_HANGING_ACCEPTED` (≥20 accepts) · `PASS_WITH_REDUCED_SET` (1–19) · `BLOCKED_*` · `FAIL_*`

## Non-claims

No coverage/recall/VPS/commercial/LOCAL_READY/PROJECT_DONE gains from this campaign.
