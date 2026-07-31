# FINAL REPORT — EXTRA-PRS-186-187-TRUST-HARDENING-01

**Date:** 2026-07-31 (B12 scale + consumer contract complete)  
**Operator:** implementer

## 1. HEADs

| Ref | Original | Final |
|-----|----------|-------|
| PR #186 `feat/extra-local-command-center` | `0913b2f5c7fef41ae830c40478342822d5737767` | `ffae2459653b424ecbc531d7d84c42f080a66d1b` |
| PR #187 `feat/pseo-export-isolated` | `f2b54588304cad76c70fa1ea6cb40ac2b52ca1bd` | *(tip after this push)* |
| `main` | `1718d6389c4e772bf3c5a45ac059871c32d83afc` | unchanged |

## 2. A16 (PR #186) — evidence

| Command | Result |
|---------|--------|
| pytest command_center | **104 passed** |
| npm ci/build/test | **ok / 10 passed** |
| e2e full | **52 passed** |
| routes / visual | **16 / 8 passed** |

Logs on #186: `docs/ops/campaigns/.../logs/a16-*.txt`

## 3. B12 (PR #187) — evidence (this closeout)

| Command | Result |
|---------|--------|
| `pytest tests/pseo/` | **53 passed** (incl. 250k + consumer contract) |
| `ruff check scripts/pseo/ tests/pseo/` | **clean** |
| `python -m scripts.pseo.export_web_cfg --fixture … --validate` | **ok**, `CANDIDATE`, `indexable=false` |

### 250k synthetic benchmark
- File: `logs/pseo-250k-benchmark.json`
- 250000 rows, 50 batches, **fetchall=0**, elapsed **0.3785s**, RSS Δ **6.12 MiB**

### Consumer contract
- Schema contract vs vendored web-cfg rules: **PROVEN**
- Full site render/Netlify: **`CONSUMER_INTEGRATION_NOT_PROVEN`**
- Report: `PR-187-CONSUMER-CONTRACT.md`

## 4. Per-PR status

| PR | Status | Why |
|----|--------|-----|
| **#186** | **`PASS_MERGE_READY`** | A16 full green; P0s closed; REAL live remains non-claim only |
| **#187** | **`PARTIAL_BLOCKED`** | Export trust gates + 250k synthetic + schema consumer contract proven; still no human PUBLISH_READY approval artifact in-repo, no web-cfg render build, no live RO 250k Postgres run |

## 5. Non-claims
- No merge / deploy / VPS / LIVE_READY
- No Netlify or web-cfg production tree write
- No invented human APPROVED for production indexability
- No million-row production DSN proof (synthetic 250k only)

## 6. Isolation
Maintained: CC only on #186, pSEO only on #187.
