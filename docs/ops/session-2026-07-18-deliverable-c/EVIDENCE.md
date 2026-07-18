# Evidence — ROI-cand-dyn-slice-f07132d1a059 (Entregável C)

```bash
python3 -m scripts.ops.deliverable_c_expiring fixture --out docs/ops/session-2026-07-18-deliverable-c/fixture-c.json
python3 -m scripts.ops.deliverable_c_expiring audit-fixture
python3 -m pytest tests/test_deliverable_c_expiring.py -q --tb=short --no-cov
```

- Window 90–180d configurable
- Missing vigencia excluded (not silent)
- Aditivos update effective end
- CONTRATUAL vs ESTIMADO
- Relicitação evidence class, no fabricated %
- Live DSN empty residual
