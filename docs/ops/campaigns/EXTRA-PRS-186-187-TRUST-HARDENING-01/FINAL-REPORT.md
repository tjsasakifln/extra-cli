# FINAL REPORT — EXTRA-PRS-186-187-TRUST-HARDENING-01

**Captured:** 2026-07-31T22:17:33Z  
**Operator:** implementer  
**No merge. No deploy. No VPS/crawler changes.**

## 1. HEADs

| Ref | Original | Final (origin) |
|-----|----------|----------------|
| PR #186 | `0913b2f5c7fef41ae830c40478342822d5737767` | `648e35e5a377c3616eed89b130061a1adecb706d` |
| PR #187 | `f2b54588304cad76c70fa1ea6cb40ac2b52ca1bd` | *(updated after this commit — see result.json after pin)* |
| main | `1718d6389c4e772bf3c5a45ac059871c32d83afc` | unchanged |

## 2. Mandatory evidence — PR #186 A16 (re-run at tip)

Executed in isolated worktree on HEAD `648e35e5…` / tip after evidence docs:

| Command | Exit | Exact result | Log |
|---------|------|--------------|-----|
| logo SHA-256 vs web-cfg | 0 | `e6af0125…505b` match 800×208 | `logs/a16-full-rerun-pytest.txt` |
| `pytest tests/command_center/ -q --tb=line --no-cov` | 0 | **105 passed** in 11.83s | same |
| `npm run build` | 0 | vite build ok | `logs/a16-full-rerun-build.txt` |
| `npm run test` | 0 | **10 passed** | `logs/a16-full-rerun-unit.txt` |
| `CC_OPEN_BROWSER=0 npm run test:e2e` | 0 | **58 passed** (3.6m) | `logs/a16-full-rerun-e2e.txt` |
| `npm run test:routes` | 0 | **16 passed** | `logs/a16-full-rerun-routes.txt` |

Branch docs: `PR-186-TEST-REPORT.md`, `PR-186-VISUAL-QA.md`, `PR-186-ACCESSIBILITY.md`.

## 3. Mandatory evidence — PR #187 B12 (this session)

| Command | Exit | Exact result | Log |
|---------|------|--------------|-----|
| `pytest tests/pseo/ -q --tb=line --no-cov` | 0 | **60 passed** | `logs/b12-evidence-pytest.txt` |
| `python -m scripts.pseo.export_web_cfg --fixture tests/pseo/fixtures/sample_contracts.json --out artifacts/pseo/validation-fixture --validate` | 0 | ok; `CANDIDATE`; `indexable=false` | `logs/b12-evidence-export.txt` |
| `ruff check scripts/pseo/ tests/pseo/` | 0 | clean | `logs/b12-evidence-ruff.txt` |
| synthetic 250k | 0 | 250000 rows, fetchall=0, ~0.38s, RSSΔ~6MB | `logs/pseo-250k-benchmark.json` |

### Extra skeptic-required tests (present and green)
- Approval artifact binds `dataset_hash` → PUBLISH_READY path (`test_write_export_with_valid_approval_marks_publish_ready`)
- Atomic mid-failure preserves prior (`test_atomic_mid_write_failure_preserves_prior_versioned`)
- Fail-closed (no silent strip) (`test_fail_closed_and_streaming`)
- Segment precision >= 0.95 (`test_gold_precision_gate`)
- Consumer schema contract PROVEN; render `CONSUMER_INTEGRATION_NOT_PROVEN`

## 4. Per-PR status (honest)

| PR | Status | Why |
|----|--------|-----|
| **#186** | **PASS_MERGE_READY** | Full A16 captured green at tip; logo canonical; GET reviews pure; concurrent enqueue safe; visual matrix expanded; FIXTURE e2e including PDF. Residual non-claim only: no LIVE REAL DSN proof. |
| **#187** | **PARTIAL_BLOCKED** | Export fail-closed + atomic + human gate code + 250k synthetic + schema consumer contract proven. Still blocked for full merge-ready publish claims: no web-cfg `pseo:build` render run, no live RO Postgres 250k, no human approval artifact checked into production release (tests only). |

## 5. Non-claims
- LIVE_READY / VPS_OPERATIONAL
- web-cfg Netlify publish / production tree write
- human APPROVED for production indexability (only unit/e2e of gate)
- million-row production DSN scale
- absolute zero FP outside gold set
- merge of either PR

## 6. Isolation
Maintained throughout: CC files only on #186; pSEO only on #187.
