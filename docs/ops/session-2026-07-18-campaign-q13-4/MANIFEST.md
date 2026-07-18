# Campaign evidence — §13.4 residual + unit extensions

**Story:** ROI-cand-dyn-slice-44e18f3702d5  
**Cycle:** cyc-2026-07-18T004325Z  
**Branch:** extra-roi/campaign-dod-50-20260718T003950Z  
**Date:** 2026-07-18  

## §13.4 Qualidade mínima — authorized flips

| DoD item | Result | Evidence |
|----------|--------|----------|
| `ruff` passa no código alterado | EXIT 0 | `ruff.exit`, `ruff.log` (`ruff check scripts/lib/universe.py scripts/lib/value_semantics.py`) |
| `mypy` passa no caminho crítico definido | EXIT 0 | `mypy-critical.exit`, path in `mypy-critical-path.txt` |
| `pip-audit` sem HIGH/known untreated | EXIT 0 | `pip-audit.exit` — "No known vulnerabilities found" |
| Nenhum gate obrigatório usa `\|\| true` | 0 hits | `gate-patterns.txt` on `.github/workflows/ci.yml` |
| Testes fonte real sob demanda | markers | `external-markers.txt` + `pytest.ini` (`integration`, `e2e`) |
| Coverage mínimo caminhos críticos | threshold 80 | `coverage-gate.txt` / `.coveragerc` `[coverage_gate]` |
| Código crítico sem teste com justificativa | registry | `02-critical-skip-reasons.txt` + full-suite debt MANIFEST |

## §13.1 extensions (same evidence session)

| DoD item | Result | Evidence |
|----------|--------|----------|
| Normalização de IBGE | 2 new unit tests | `normalize_codigo_ibge` in `scripts/lib/universe.py`; `tests/test_universe.py` |
| Semântica de valores | 7 unit tests | `tests/test_value_semantics.py` + existing module |

## pytest

```
python3 -m pytest tests/test_value_semantics.py tests/test_universe.py -q -o addopts=
# 20 passed, EXIT 0 — see pytest-unit.exit
```

## Explicit non-claims

- Not claiming full-repo mypy green (golden_path/health still have errors).
- Not claiming coverage_gate *measured* 80% achieved — only that minimum **is defined**.
- Not claiming live restore / VPS / 95% coverage.
- Not claiming AEC classification or live edital→contrato chain.

## Implementer vs QA

- Implementer: delivery-engineer (campaign orchestrator implement path)
- QA: adversarial-qa-auditor (separate agent / verdict file)


## mypy artifact honesty (remediation)

- `mypy-critical.exit` EXIT:0 is the **only** claim for §13.4 critical path.
- `mypy.exit` / old `mypy.log` superseded: full multi-file path had **76 errors** → `mypy-fullpath-FAILED-76-errors.log`.
