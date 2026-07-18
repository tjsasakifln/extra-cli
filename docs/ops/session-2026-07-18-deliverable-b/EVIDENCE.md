# Evidence — ROI-cand-dyn-slice-f7e09f20fb21 (Entregável B)

## Commands
```bash
python3 -m scripts.ops.deliverable_b_competitors fixture --out docs/ops/session-2026-07-18-deliverable-b/fixture-b.json
python3 -m scripts.ops.deliverable_b_competitors insufficient-demo --out docs/ops/session-2026-07-18-deliverable-b/insufficient-b.json
python3 -m scripts.ops.deliverable_b_competitors audit-fixture
python3 -m pytest tests/test_deliverable_b_competitors.py -q --tb=short --no-cov
```

## Results
- fixture: 15/15 OK with reproducible SelectionRule
- insufficient-demo: 3 valid, status INSUFFICIENT, no padding
- audit: 13/13 PASS
- live DSN: 0 supplier contracts — market list not fabricated

## Residual
Live PG empty; datalake_helper.top_competitors available when contracts exist.
