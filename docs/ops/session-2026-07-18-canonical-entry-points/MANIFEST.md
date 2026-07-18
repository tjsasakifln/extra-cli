# Evidence §32.1 entry-point alignment

Story ROI-cand-dyn-slice-34174823e54a · QA PASS

```bash
python3 -m pytest tests/test_canonical_entry_points.py -q --no-cov -o addopts=
python3 -m scripts.ops.canonical_entry_points --json
```
