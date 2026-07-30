# HANDOFF — DOD-LOW-HANGING-BOUNDARIES-AND-EVIDENCE-01

## State

- **PR A branch:** `campaign/dod-low-hanging-boundaries-evidence-01`
- **Baseline SHA:** `e39a75f35224cdf1acd34c2a8eb2f5ea08fa220e`
- **QA:** `PASS_WITH_REDUCED_SET` — **42** promotion-eligible items
- **DOD.md:** not modified in PR A

## Promote list (PR B)

See `artifacts/.../qa-verdict.json` → `surviving_proven_item_ids` (42 IDs).

## Commands

```bash
# PR A validation
python3 -m scripts.ops.dod_low_hanging_audit \
  --campaign-id DOD-LOW-HANGING-BOUNDARIES-AND-EVIDENCE-01 \
  --out artifacts/campaigns/DOD-LOW-HANGING-BOUNDARIES-AND-EVIDENCE-01
python3 -m pytest tests/test_scope_boundaries.py tests/test_client_claim_boundaries.py \
  tests/test_dod_governance_invariants.py tests/test_dod_low_hanging_audit.py -q --no-cov

# After PR A on main — PR B
git fetch origin && git checkout main && git pull --ff-only
git checkout -b campaign/dod-low-hanging-promotion-01
python3 tools/dod_controller.py scan
python3 -m scripts.ops.dod_low_hanging_audit --out artifacts/campaigns/DOD-LOW-HANGING-BOUNDARIES-AND-EVIDENCE-01/reproof
# then per item: start → verify → accept --update-dod
```

## Do not

- Touch commercial campaign worktree/files  
- Accept redis/k8s item without ADR proving need  
- Accept demoted IDs from QA without new proofs  
- Mutate VPS / crawl live / soak  

## Residual debt

- Optional governance evidence-type per-kind gates  
- Document Redis CON-6 need or remove unused pool  
- Classifier false-rejects “comercial” inside liability disclaimer text  
