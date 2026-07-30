# FINAL-REPORT — DOD-LOW-HANGING-BOUNDARIES-AND-EVIDENCE-01

## Baseline

| Field | Value |
|-------|--------|
| `baseline_main_sha` | `e39a75f35224cdf1acd34c2a8eb2f5ea08fa220e` |
| Branch (PR A) | `campaign/dod-low-hanging-boundaries-evidence-01` |
| Worktree | `/mnt/d/extra-cli-dod-low-hanging` |
| `DOD.md` SHA-256 | `bc2f4b6f6d33eea05a080e5de2224e6a2d1a730e097945276b6bae5e8f304c25` |
| Open items (unchecked) | 1011 |
| ACCEPTED (controller) | 441 / 1462 |
| Parallel commercial | **identified** (`extra-cli-wt-confenge-activation-01`) |
| PR #133 | draft blocked (untouched) |

## Delivery (PR A)

Harness + boundaries (no `DOD.md` accept):

- `config/scope_boundaries.yaml`
- `scripts/ops/audit_scope_boundaries.py`
- `scripts/ops/audit_client_claim_boundaries.py`
- `scripts/ops/dod_low_hanging_audit.py`
- tests: scope / claims / governance / harness
- Spec Kit `specs/900-dod-low-hanging-boundaries-evidence/`
- `docs/architecture/scope-boundaries.md`
- campaign artifacts under `artifacts/campaigns/DOD-LOW-HANGING-BOUNDARIES-AND-EVIDENCE-01/`

## Inventory

| Decision | Count |
|----------|------:|
| SELECTED | 59 |
| REJECTED_NOT_LOW_HANGING | 1308 |
| REJECTED_HUMAN | 39 |
| REJECTED_PARALLEL_CONFLICT | 20 |
| REJECTED_INSUFFICIENT_EVIDENCE | 33 |
| REJECTED_LIVE_DEPENDENCY | 3 |

## Proof → QA

| Stage | Count |
|-------|------:|
| Proven pre-QA (harness) | 58–59 |
| Demoted by independent QA | 17 |
| **Promotion-eligible post-QA** | **42** |

### Surviving by family

| Family | Count |
|--------|------:|
| A_GOVERNANCE | 11 |
| B_SCOPE_EXCLUDED | 23 |
| C_CLI_UX | 4 |
| D_COVERAGE_TRUTH | 4 |

### Notable demotions

- Redis/K8s item: `redis_pool.py` present without need-proven ADR → not accepted  
- Evidence-type catalog bullets: shared doc keyword, not per-type enforcement  
- Three-rolls sub-bullets / hardcoded optional policy  
- Weak CLI claims (help ≠ idempotency)  
- Coverage items self-labeled “Code-ready (not accepted)” in DOD text  

## Tests

```text
31 passed — test_scope_boundaries, test_client_claim_boundaries,
            test_dod_governance_invariants, test_dod_low_hanging_audit
```

## QA

- Verdict: **`PASS_WITH_REDUCED_SET`**
- Reviewer: Quinn (independent) — `ADVERSARIAL-REVIEW.md`
- Protected paths: **OK** (no DOD.md / commercial / crawl / Makefile / README / DEVELOPMENT / systemd)

## Terminal status (after PR A only)

`PROOF_COMPLETE` / awaiting PR A merge + PR B promotions.

If all 42 promote on main with green CI:

- **`PASS_LOW_HANGING_ACCEPTED`** (≥20)

If fewer promote due to controller/CI collision:

- **`PASS_WITH_REDUCED_SET`** with honest count

## Non-claims

- No 95% coverage/recall  
- No VPS_OPERATIONAL / LOCAL_READY / PROJECT_DONE  
- No commercial queue readiness  
- Static boundary proof ≠ live soak  
- No fabricated human accepts  

## Collisions avoided

- Dedicated worktree/branch; Spec Kit `900+`  
- Commercial campaign paths untouched  
- PR #133 untouched  
- `DOD.md` not edited in PR A  

## Next (PR B)

1. Merge PR A to `main`  
2. Fresh branch from main  
3. Re-run audit + re-proof  
4. Promote only intersection: still-open ∩ QA-approved ∩ still-proven  
5. Controller `start` → `verify` → `accept --update-dod` one-by-one  

## Looks cheap but was not

- 95% coverage / recall / soak / VPS  
- CONFENGE commercial queue outcomes  
- Redis “no infra” while `redis_pool.py` exists  
- Evidence-type checklist lines without type-specific gates  
- Backup/restore without complete pre-existing restore evidence  
