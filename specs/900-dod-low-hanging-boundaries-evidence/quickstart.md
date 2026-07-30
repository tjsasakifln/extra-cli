# Quickstart

```bash
cd /path/to/extra-cli-dod-low-hanging
python3 tools/dod_controller.py scan
python3 -m scripts.ops.dod_low_hanging_audit \
  --campaign-id DOD-LOW-HANGING-BOUNDARIES-AND-EVIDENCE-01 \
  --out artifacts/campaigns/DOD-LOW-HANGING-BOUNDARIES-AND-EVIDENCE-01
python3 -m pytest \
  tests/test_scope_boundaries.py \
  tests/test_client_claim_boundaries.py \
  tests/test_dod_governance_invariants.py \
  tests/test_dod_low_hanging_audit.py \
  -q --tb=short --no-cov
```

Does **not** edit `DOD.md` or call `accept`.
