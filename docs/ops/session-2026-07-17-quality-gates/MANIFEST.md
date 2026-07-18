# Quality gates evidence — §13.4

**Story:** ROI-cand-quality-gates-evidence  
**Date:** 2026-07-18 (revalidated on clean main)

## Results (integration audit)

| Check | Result | Note |
|-------|--------|------|
| `ruff check scripts/` | exit 0 | CI scope; full-repo ruff still has framework debt (not claimed) |
| bandit `-lll` production scripts | exit 0 | 0 HIGH |
| pytest critical (main audit) | 300 passed, 5 skipped | full critical list from CI |
| pre-commit config + smoke | config present; smoke PASS | existence alone insufficient — smoke executed |
| continue-on-error:true (YAML key) | absent | comments mention the ban only |
| `|| true` in non-comment workflow lines | absent | set +e used only to assert exit 2 on live health |
| slow markers | pytest.ini `slow` + default `-m "not slow"` | present |
| critical suite external deps | mocked in smoke tests | no live network in critical suite |
| QA independence | process + separate reviewer fields | not implementer-only |

## Authorized DoD flips (exactly 8)

See `proposed-flips.txt`.

## Explicitly NOT flipped

- ruff passa no código alterado
- mypy passa no caminho crítico
- pip-audit (passed in audit session; not in this PR's authorized flip list)
- Nenhum gate obrigatório usa `|| true` (kept open; set +e pattern documented separately)
