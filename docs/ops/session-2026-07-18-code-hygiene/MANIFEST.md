# Evidence §27 hygiene (metrics, legacy, TODOs, dry-run, destructive)

Story ROI-cand-dyn-slice-e845e4e64aba

## Artifacts
- docs/ops/METRIC-DEFINITION-POLICY.md
- docs/ops/LEGACY-REMOVAL-PLAN.md
- scripts/ops/code_hygiene_gate.py
- golden_clean_env --confirm-drop / --dry-run

## Commands
```bash
python3 -m scripts.ops.code_hygiene_gate --json
python3 -m pytest tests/test_code_hygiene_gate.py -q --no-cov -o addopts=
python3 -m scripts.ops.golden_clean_env --dry-run
# destructive requires: --confirm-drop
```
