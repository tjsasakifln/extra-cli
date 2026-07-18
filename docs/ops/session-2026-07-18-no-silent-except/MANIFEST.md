# Evidence §27 no silent except Exception: pass

Story ROI-cand-dyn-slice-73ed151d3946

- Replaced 25× `except Exception: pass` with logged warnings (exc_info=True)
- Gate: n_total bare pass = 0 under scripts/

```bash
python3 -m scripts.ops.code_organization_gate --json
python3 -m pytest tests/test_code_organization_gate.py tests/test_golden_path_canonical.py -q --no-cov -o addopts=
```
