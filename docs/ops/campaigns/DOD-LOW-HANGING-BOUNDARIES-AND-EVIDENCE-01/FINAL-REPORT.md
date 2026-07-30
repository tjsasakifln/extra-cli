# FINAL-REPORT — DOD-LOW-HANGING-BOUNDARIES-AND-EVIDENCE-01

**Terminal status:** `PASS` / **`PASS_LOW_HANGING_ACCEPTED`** (after integrity remediation)  
**Updated:** 2026-07-30 (post-skeptic integrity pass)

## Baseline

| Field | Value |
|-------|--------|
| `baseline_main_sha` | `e39a75f35224cdf1acd34c2a8eb2f5ea08fa220e` |
| Worktree (PR A) | `/mnt/d/extra-cli-dod-low-hanging` |
| Commercial parallel | identified (`extra-cli-wt-confenge-activation-01`) — **not touched** |
| PR #133 | draft blocked — **not touched** |

## PRs and SHAs

| PR | Role | Merge SHA | Required CI |
|----|------|-----------|-------------|
| [#173](https://github.com/tjsasakifln/extra-cli/pull/173) | Harness / auditors / tests / Spec Kit 900 | `97da2c49…` | green |
| [#176](https://github.com/tjsasakifln/extra-cli/pull/176) | Controller accepts + `.dod/evidence` + `DOD.md` | `93b1447c…` | **all required contexts green** |
| integrity remediation | demote 2 weak POLICY items + real `ci_status` | (this PR) | — |

**PR #176 head (pre-merge):** `b2895ecb7e86ddf72317d40fa48b608103928fbe`  
**Workflow:** https://github.com/tjsasakifln/extra-cli/actions/runs/30508183866

### Required CI on PR #176 (branch protection)

All **success**: Lint, mypy, Test critical, Test operational, Test All (full suite), Resilience Gate, bandit, pip-audit, Generated Artifacts, PR Reviewability, Pytest Skip Policy.

### Non-required failure (documented, not gate)

- `CONFENGE Commercial Code Quality` = **failure** (artifact `bound_sha` not ancestor of this PR head).  
  **Not** in `main` required status checks. Unrelated commercial freeze binding — zero commercial files changed by this campaign.

## Acceptance math (honest)

| Stage | Count |
|-------|------:|
| SELECTED (low-hanging inventory) | 59 |
| Proven pre-QA (harness) | ~58 |
| QA-approved (`PASS_WITH_REDUCED_SET`) | 42 |
| Controller ACCEPTED in #176 | 39 |
| Demoted in integrity remediation (POLICY-only) | 2 |
| **Net ACCEPTED retained** | **37** |
| Orphan VERIFIED (checkbox not locateable) | 3 |

**≥20 retained** → terminal **`PASS_LOW_HANGING_ACCEPTED`** still holds after demotion.

### Demoted (integrity)

| Item | Reason |
|------|--------|
| `…-75164c86da` code without execution | Only `dpi.POLICY` flag; not enforced in `dod_controller` accept path |
| `…-59ea375492` unit ≠ e2e | Same; controller allows pure unit pytest as verify |

### Retained governance (enforced)

| Item | Enforcement |
|------|-------------|
| `…-a362715e4d` evidence required | `cmd_accept` requires pack + criteria + green verify — proven by `tests/test_dod_controller_evidence_gates.py` |
| PARTIAL / BLOCKED / NA / field absence / reconstruct | `scripts/ops/requirement_states.py` + tests |
| three rolls PROJECT_DONE | `dod_process_integrity.project_done_allowed` |

## Process debt (transparent)

1. **Promotion accepts used `--allow-non-main`** on branch `campaign/dod-low-hanging-promotion-01` while flipping `DOD.md`.  
   Mitigation: same flips merged to `main` only after **required** CI green on exact PR head; dual-PR pattern.
2. **Original `ci_status.json` pointed at PR #173 SHA with prose.**  
   Mitigation: packs rewritten to PR #176 head + required job map + workflow URL (`integrity_remediation: true`).
3. **Self-review of harness ≠ QA** — independent QA reduced set (Quinn); demotions respected.

## Families retained (37)

| Family | Approx |
|--------|-------:|
| B scope excluded | 23 |
| A governance (enforced) | 9 |
| C CLI | 4 |
| D coverage-truth semantic | 1 |

## Non-claims

- No 95% coverage/recall  
- No soak / VPS_OPERATIONAL / LOCAL_READY / PROJECT_DONE  
- No commercial queue readiness  
- Static scope audit ≠ live operational proof  
- `CONFENGE Commercial Code Quality` failure is **not** claimed fixed  

## Collisions avoided

- Spec Kit `900+`; dedicated worktrees  
- Protected paths (§2.1) not mutated in PR A  
- Commercial campaign paths untouched  

## Looks cheap but was not

- Redis “absent” while `redis_pool.py` exists  
- Evidence-type catalog bullets without per-type gates  
- POLICY-only governance slogans without controller wiring  
- 95% / soak / commercial / human accepts  

## Artifacts

- `artifacts/.../result.json`  
- `artifacts/.../qa-verdict.json`  
- `artifacts/.../integrity-remediation.json`  
- `artifacts/.../protected-path-audit.json`  
- `docs/architecture/scope-boundaries.md`  
