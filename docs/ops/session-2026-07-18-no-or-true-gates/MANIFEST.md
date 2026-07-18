# Evidence — Nenhum gate obrigatório usa `|| true`

**Story:** `ROI-cand-dyn-slice-1e78666e2a21`  
**Cycle:** `cyc-2026-07-18T124230Z`  
**Branch:** `extra-roi/cand-no-or-true-gates`  
**Date:** 2026-07-18  
**DoD item:** §13.4 `Nenhum gate obrigatório usa \`|| true\`.`

## What was delivered

| Artifact | Role |
|----------|------|
| `scripts/ops/scan_mandatory_gates_failclosed.py` | Shipped scanner over explicit mandatory gate surface |
| `tests/test_mandatory_gates_no_or_true.py` | Unit + live-repo scan tests (no reimplementation of scanner) |
| `scan-report.json` / `scan.exit` | CLI run exit 0, 0 findings |
| `pytest.log` / `pytest.exit` | 6 passed, exit 0 |

## Mandatory gate surface scanned

1. `.github/workflows/ci.yml`
2. `scripts/ci_gate.sh`
3. `scripts/ci-check.sh`
4. `scripts/coverage_gate.py`
5. `scripts/freshness_gate.py`
6. `scripts/golden_path.py`
7. `squads/extra-dod-roi/scripts/enforce_aiox_path.py`

## Result

- `or_true` findings: **0**
- `continue_on_error_true` findings: **0**
- missing paths: **0**
- pytest: **6 passed**

## Out of scope (explicit)

- `|| true` in non-gate ops scripts (`backup-database.sh` notify path, bootstrap cleanup, deploy ufw cleanup) — not mandatory quality gates.
- Not claiming LOCAL_READY / VPS / 95% coverage.
- Not claiming full-repo free of `|| true`.

## Commands

```bash
python3 -m scripts.ops.scan_mandatory_gates_failclosed --json
python3 -m pytest tests/test_mandatory_gates_no_or_true.py -q -o addopts=
```

## Agents

- Implementer: delivery-engineer
- QA: adversarial-qa-auditor (independent)
