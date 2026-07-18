# Evidence §27 code organization (first 5)

Story ROI-cand-dyn-slice-55dc8958c51c
Module scripts/ops/code_organization_gate.py

| Item | Proof |
|------|-------|
| Module names consistent | package snake_case policy + gate ok |
| sys.path policy | inventory; only project-root bootstrap allowed |
| Public docstrings | sample critical modules docstring_pct |
| Type hints critical | return_hint_pct on public API sample |
| Specific exceptions | critical path 0× except Exception: pass |

```bash
python3 -m scripts.ops.code_organization_gate --json
python3 -m pytest tests/test_code_organization_gate.py -q --no-cov -o addopts=
```
