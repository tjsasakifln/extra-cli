# HANDOFF — DOD-LOW-HANGING-BOUNDARIES-AND-EVIDENCE-01

## Final state (post integrity)

| Field | Value |
|-------|--------|
| Terminal | `PASS_LOW_HANGING_ACCEPTED` (37 net accepts after demote) |
| PR A | #173 → `97da2c49` |
| PR B | #176 → `93b1447c` |
| PR head B | `b2895ecb` |
| Integrity branch | `campaign/dod-low-hanging-integrity-remediation-01` |

## What is done

- Scope boundary config + auditors + claim guard  
- Campaign harness (no accept in harness)  
- QA reduced set; 37 items remain ACCEPTED with evidence packs  
- Required CI green on PR #176  
- Weak POLICY-only accepts demoted  
- `ci_status.json` rewritten with real required-job map  

## Residual / follow-ups

1. Wire `code_without_execution` / `unit≠e2e` into controller gates if those DOD lines should stay closed.  
2. Fix CONFENGE commercial freeze binding (unrelated; fails on non-commercial PRs).  
3. Three ROL-1 orphan fingerprints still VERIFIED without checkbox.  
4. Optional: re-accept demoted items only after real controller enforcement exists.

## Do not

- Re-accept demoted items with POLICY-only proof  
- Touch commercial / crawl / VPS  
- Claim commercial CI fixed  

## Commands

```bash
python3 -m scripts.ops.dod_low_hanging_audit --out artifacts/campaigns/DOD-LOW-HANGING-BOUNDARIES-AND-EVIDENCE-01
python3 -m pytest tests/test_scope_boundaries.py tests/test_client_claim_boundaries.py \
  tests/test_dod_governance_invariants.py tests/test_dod_low_hanging_audit.py \
  tests/test_dod_controller_evidence_gates.py -q --no-cov
python3 tools/dod_controller.py status
```
