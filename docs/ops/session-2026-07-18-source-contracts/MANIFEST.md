# Evidence §13.3 source contracts (first 8)

Story ROI-cand-dyn-slice-fb519704765b
Module scripts/ops/source_contract_tests.py

Offline: 8/8 ok. Live: pncp_endpoint may fail (403/network) — not claimed green live.

```bash
python3 -m pytest tests/test_source_contract_tests.py -q --no-cov -o addopts=
python3 -m scripts.ops.source_contract_tests --json
# optional: --live
```
