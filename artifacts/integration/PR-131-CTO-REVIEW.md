# PR #131 — CTO Adversarial Review

**Reviewer role:** CTO / integration owner  
**Branch tip reviewed (pre-integration commits):** `dd20c37d7b92cbe93774f1e7b4b0e53921f4b21c`  
**Date:** 2026-07-25T00:57:04Z  
**Main base:** `5d906f631f444dd803e92bb88b7c98972297f8d4`

## Scope reviewed

- Migrations 060, 061 vs main 059
- Isolation / production fail-closed
- Linkage identity (CNPJ14 vs root)
- Consulting pack A–E + dossiers + recurrence claims
- Generated artifacts volume
- Honesty of acceptance docs

---

## Findings

### BLOCKER

| ID | Finding | Status |
|----|---------|--------|
| B1 | PR diff ~748k lines / 283 files with large reproducible pack outputs (PDF/XLSX/dossiers/pack-full) makes human review impractical and risks private-scale data in Git | **FIXED** — removed 140 heavy generated paths (~28 MB); policy + CI gate added |

### HIGH

| ID | Finding | Status |
|----|---------|--------|
| H1 | `PASS.md` claimed “Human ACCEPT: Tiago Sasaki” while `user-acceptance.json` is `PENDING_HUMAN` | **FIXED** — PASS.md demoted to PASS_TECHNICAL; acceptance remains PENDING_HUMAN |
| H2 | Duplicate pack-rc / pack-verify trees re-version same run outputs | **FIXED** — removed from Git; regeneration documented |

### MEDIUM

| ID | Finding | Status |
|----|---------|--------|
| M1 | `scripts/linkage/isolation.py` `campaign_id` still labels CANONICAL-ENTITY-LINKAGE-01 when used by client-ready cycle | **OPEN** — cosmetic/metadata; isolation ports include 5436/5439 |
| M2 | Views 060 aggregate on CNPJ8 root — multi-branch CNPJs collapse | **ACCEPTED_RISK** — documented as intel_product footprint, not legal identity; linkage 061 prefers CNPJ14 with unique index |
| M3 | Recurrence labeled deterministic replay, not dual temporal snapshot | **OPEN** — correctly listed in non-claims; keep labels honest |
| M4 | Main branch has no GitHub branch protection | **OPEN** — proposal documented; not silently applied |

### LOW

| ID | Finding | Status |
|----|---------|--------|
| L1 | Large Makefile surface for campaigns | Open — acceptable for ops |
| L2 | HTML operational reports were versioned | Fixed by removal |

### ACCEPTED_RISK

| ID | Risk | Rationale |
|----|------|-----------|
| R1 | Analytical views over multi-million contract table | Views filter `is_active`; app layer must paginate; RC proven on isolated dump only |
| R2 | Heuristic linkage classifications | Explicit `ambiguous`/`unresolved` + review queue; non-claims on participation |
| R3 | Human may accept stale freeze | Binding fields in user-acceptance.json; agent forbidden to rebind ACCEPT |

---

## Migrations

| # | File | Notes |
|---|------|-------|
| 059 (main) | `059_coverage_evidence_canonical_entity_unique.sql` | Present on main — **do not reuse number** |
| 060 (#131) | `060_national_contracts_intelligence_layers.sql` | CREATE OR REPLACE VIEW only — additive, no fact-table mutation |
| 061 (#131) | `061_canonical_entity_linkage.sql` | Tables + indexes; BEGIN/COMMIT; IF NOT EXISTS; unique natural keys per run_id |
| 059 (#121) | `059_national_contracts_intelligence_layers.sql` | **Collision** — superseded by 060 on #131 |

**Idempotency:** 060 views replaceable; 061 uses IF NOT EXISTS / unique constraints.  
**Rollback:** drop views 060; drop 061 tables in reverse FK order (document in ops if needed).  
**Order:** apply after main 059; 060 then 061.

## Linkage / identity

- Strong keys: CNPJ14 unique partial index on suppliers; organs unique `canonical_key`.
- Conflicting strong keys must not auto-merge (design comments + classifications).
- Unresolved/ambiguous persist (first-class classifications).
- Opportunity→contract links carry `claim_level` and non-claims arrays (no invented participation).

## Isolation

- Forbidden host markers: ec-prod, vps, production, soak paths.
- Allowed hosts: localhost only; preferred ports 5436/5438/5439.
- Fail-closed on missing DSN / non-local / production markers.
- **production_touched** and soak markers checked; this integration work did not SSH VPS.

## Claims / non-claims

Non-claims include LOCAL_READY, VPS_OPERATIONAL, PROJECT_DONE, live dual-snapshot recurrence, win rate without denominator. Keep user-acceptance PENDING until Tiago decides.

## Residual open items (not blocking technical merge readiness after gates)

- M1, M3, M4
- Human decision on frozen RC
- Post-merge rebase of #132–#134

## Verdict

**BLOCKER/HIGH resolved on integrator branch.**  
Technical path: complete local/CI gates → `READY_FOR_HUMAN_ACCEPTANCE`.  
**Not** PROJECT_DONE. **Not** auto-merged.
