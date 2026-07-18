# Evidence — ROI-cand-dyn-slice-b9dd47d02782 (Entregável D)

```bash
python3 -m scripts.ops.deliverable_d_prices fixture --out docs/ops/session-2026-07-18-deliverable-d/fixture-d.json
python3 -m scripts.ops.deliverable_d_prices audit-fixture
python3 -m pytest tests/test_deliverable_d_prices.py -q --tb=short --no-cov
```

- Comparability rule documented (tipo/unidade/lote/porte/região + período temporal)
- n, median, p25, p75, min/max; outliers flagged not hidden
- INSUFFICIENT_SAMPLE when n < min_sample
- Semantics estimado|homologado|contratado|pago only
- Forbidden: "preço real praticado" for heterogeneous globals
- Residual: live DSN empty — no fabricated market prices
