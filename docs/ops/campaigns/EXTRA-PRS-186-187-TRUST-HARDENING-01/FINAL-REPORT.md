# FINAL REPORT — EXTRA-PRS-186-187-TRUST-HARDENING-01

**Captured:** 2026-07-31T22:45:00Z  
**Operator:** implementer  
**No merge. No deploy. No VPS/crawler changes.**

## 1. HEADs (origin tips at pin time)

| Ref | Original | Final (origin tip before this pin commit) |
|-----|----------|-------------------------------------------|
| PR #186 | `0913b2f5c7fef41ae830c40478342822d5737767` | `82cb1097af445534183342db36b7cf5130135d41` |
| PR #187 | `f2b54588304cad76c70fa1ea6cb40ac2b52ca1bd` | `d37b2fa99476fa894863405751aa153f9b36fe22` |
| main | `1718d6389c4e772bf3c5a45ac059871c32d83afc` | unchanged |

## 2. Mandatory evidence — PR #186 A16 (re-run at tip)

Executed in isolated worktree; tip after evidence docs:

| Command | Exit | Exact result | Log |
|---------|------|--------------|-----|
| logo SHA-256 vs web-cfg | 0 | `e6af0125…505b` match 800×208 | `logs/a16-full-rerun-pytest.txt` |
| `pytest tests/command_center/ -q --tb=line --no-cov` | 0 | **105 passed** in 11.83s | same |
| `npm run build` | 0 | vite build ok | `logs/a16-full-rerun-build.txt` |
| `npm run test` | 0 | **10 passed** | `logs/a16-full-rerun-unit.txt` |
| `CC_OPEN_BROWSER=0 npm run test:e2e` | 0 | **58 passed** (3.6m) | `logs/a16-full-rerun-e2e.txt` |
| `npm run test:routes` | 0 | **16 passed** | `logs/a16-full-rerun-routes.txt` |

Branch docs: `PR-186-TEST-REPORT.md`, `PR-186-VISUAL-QA.md`, `PR-186-ACCESSIBILITY.md`.

## 3. Mandatory evidence — PR #187 B12 (this session, post B7/B9)

| Command | Exit | Exact result | Log |
|---------|------|--------------|-----|
| `pytest tests/pseo/ -q --tb=line --no-cov` | 0 | **64 passed** | `logs/b12-evidence-pytest.txt` |
| `python -m scripts.pseo.export_web_cfg --fixture … --validate` | 0 | ok; `CANDIDATE`; `indexable=false`; `classifier_gate.ok=true` | `logs/b12-evidence-export.txt` |
| `ruff check scripts/pseo/ tests/pseo/` | 0 | clean (after Path import fix) | `logs/b12-evidence-ruff.txt` |
| synthetic 250k | 0 | 250000 rows, fetchall=0 | `logs/pseo-250k-benchmark.json` |

### Skeptic-required fixes landed this session
- **B7:** removed `cli_export.py` short-circuit in `validation.py`; always enforce commit+entrypoint
- **B7 tests:** `test_bogus_source_commit_sha_rejected_even_when_cli_export_exists`, `test_unknown_source_commit_sha_rejected`
- **B9:** `run_gold_classifier_gate` / `evaluate_classifier` on export path before `PUBLISH_READY`
- **B9 tests:** gate blocks publish even with valid approval; gold helper asserts `publish_ok`

### Other green gates
- Approval artifact binds `dataset_hash` → PUBLISH_READY only if classifier also ok
- Atomic mid-failure preserves prior
- Fail-closed (no silent strip)
- Segment precision >= 0.95
- Consumer schema contract PROVEN; render `CONSUMER_INTEGRATION_NOT_PROVEN`

## 4. Per-PR status (honest)

| PR | Status | Why |
|----|--------|-----|
| **#186** | **PASS_MERGE_READY** | Full A16 captured green at tip `82cb1097…`; logo canonical; GET reviews pure; concurrent enqueue safe; visual matrix expanded; FIXTURE e2e including PDF. Residual non-claim only: no LIVE REAL DSN proof. |
| **#187** | **PARTIAL_BLOCKED** (not MERGE_READY) | Export fail-closed + atomic + human gate + **classifier gold on promote path** + SQLite staging + nested public models + read-only web-cfg verifier + 250k synthetic extract + e2e CI bench. Still blocked for merge-ready: no web-cfg `pseo:build` render run, no live RO Postgres 250k, no production human approval artifact. |

### Status vocabulary (do not conflate)

| Term | Scope | Default |
|------|-------|---------|
| **CANDIDATE** | Export `snapshot_status` without dual gates | **Fail-closed default** |
| **PUBLISH_READY** | Export snapshot after human approval **and** classifier gold gate | Not a PR merge claim |
| **MERGE_READY / PASS_MERGE_READY** | PR-level merge recommendation only | Independent of `PUBLISH_READY` |
| **indexable** | Manifest flag for editorial indexing | Requires PUBLISH_READY path |

`PUBLISH_READY` ≠ `MERGE_READY`. A fixture export remaining `CANDIDATE` / `indexable=false` is expected and correct without approval.

## 5. Non-claims
- LIVE_READY / VPS_OPERATIONAL
- web-cfg Netlify publish / production tree write
- human APPROVED for production indexability (only unit/e2e of gate)
- million-row production DSN scale
- absolute zero FP outside gold set
- merge of either PR
- `PUBLISH_READY` as evidence of PR merge readiness

## 6. Isolation
Maintained throughout: CC files only on #186; pSEO only on #187.
