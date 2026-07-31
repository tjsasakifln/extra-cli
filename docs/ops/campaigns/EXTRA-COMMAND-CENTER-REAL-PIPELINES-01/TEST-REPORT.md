# TEST-REPORT

## HEAD re-gated

```text
a71957500dd798a368e14e3f9a48ac76bbdcf0fc
```

## Python

```bash
python3 -m pytest tests/command_center/ -q --tb=line --no-cov
```

| Metric | Value |
|--------|-------|
| Result | **97 passed** |
| Baseline mission start | 71 passed |
| Scratch log | `{SCRATCH}/pytest-cc-final.txt` |

Coverage added this mission:

- `test_real_adapters.py` — data_mode, argv safety, preflight block, harness REAL, no silent fallback
- `test_adversarial_security.py` — injection, path/symlink, secrets, formula, no-fallback, cwd leak, workspace filter, REAL overlay regen
- `test_use_fixture_false_is_real_fail_closed` — REAL fail-closed sem DSN

## Playwright

```bash
cd apps/command-center && npm run build && CC_OPEN_BROWSER=0 npm run test:e2e
```

| Metric | Value |
|--------|-------|
| Result | **28 passed** |
| Baseline mission start | 26 passed |
| Scratch log | `{SCRATCH}/pw-e2e-final.txt` |

Cases A–H (objetivo):

| ID | Cobertura |
|----|-----------|
| A | preflight REAL READY exposto na UI quando ambiente permite |
| B | preflight REAL BLOCKED_* honesto sem DSN |
| C | MODO DEMONSTRAÇÃO explícito (banner + data_mode) |
| D | harness REAL sem marca FIXTURE_DEMO |
| E | PDF/XLSX abertos na UI (task1–4) |
| F | review + regenerate (task3) com overlay; REAL parent preservado em unit test |
| G | mobile 390×844 |
| H | sem credenciais no DOM |

## Local policy (pre-push)

```bash
python3 -m scripts.ops.check_generated_artifacts_policy --base origin/main
python3 -m scripts.ops.check_pr_reviewability --base origin/main
```

Esperado: PASS (revalidar no tip).
