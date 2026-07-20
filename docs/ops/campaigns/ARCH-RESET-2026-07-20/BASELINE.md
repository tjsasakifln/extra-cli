# ARCH-RESET-2026-07-20 — Baseline

**Campaign:** `ARCH-RESET-2026-07-20`  
**Baseline HEAD:** `d6d9e1984e348d64a669546613e192e4ebf610cd` (`d6d9e19`)  
**Subject:** Merge pull request #49 from tjsasakifln/campaign/extra-operational-proof-01  
**Generated:** 2026-07-20 (UTC)  
**Machine metrics:** [`baseline.json`](./baseline.json)

## Purpose

Evidence-backed snapshot of the repository **before** architecture changes.
This document does **not** change production behavior.

## Claims at baseline (honest)

| Claim | Status |
|-------|--------|
| `LOCAL_READY` | **NOT_CLAIMED** |
| Operational coverage ≥95% | **NOT_CLAIMED** |
| `VPS_OPERATIONAL` | **NOT_CLAIMED** |
| `PROJECT_DONE` | **NOT_CLAIMED** |
| `PRE_VPS_FINAL_READY` | **NOT_READY** |
| `LOCAL_RESILIENCE_READY` | **NOT_READY** (adversarial truth gate) |

## Quantitative metrics (HEAD `d6d9e19`)

| Metric | Value |
|--------|------:|
| Tracked files | 4240 |
| Python production modules (`scripts/**/*.py`) | 326 |
| Python test modules (`tests/**/*.py`) | 193 |
| Approx. LOC scripts | ~161 054 |
| Approx. LOC tests | ~37 501 |
| SQL migrations | 62 |
| ADRs (excl. INDEX) | 9 |
| CI workflows | 1 |
| Makefile targets | 23 |
| Direct `requirements.txt` deps | 12 |
| DoD open checkboxes `[ ]` | 1044 |
| DoD done checkboxes `[x]` | 308 |

Regenerate:

```bash
python3 scripts/architecture/inventory_baseline.py \
  --out docs/ops/campaigns/ARCH-RESET-2026-07-20/baseline.json
```

## Product entrypoints (classified)

| Entry | Implementation | Class |
|-------|----------------|-------|
| **`make extra-weekly`** | `python3 -m scripts.ops.weekly_cycle --strict` | **canonical** product cycle |
| `make golden-path` | `scripts/golden_path.py` | diagnostic / validation |
| `make run-pipeline` | bootstrap + crawl + intel + report | **legacy composite** (competes narratively) |
| `make report-executivo` | executive PDF + Excel generators | component (delivery) |
| `make resilient-local-cycle` | `scripts.ops.resilient_cycle --env fixture` | diagnostic / resilience |
| `force-next` | `squads/extra-dod-roi/scripts/cli.py force-next` | campaign governance (not product) |

`docs/canonical-entry-points.yaml` (v1.0, 2026-07-18) already marks **weekly** as canonical, but Makefile still exposes multiple operational-looking targets without a single fail-closed classification surface.

## Orchestrators / pipelines (concurrent surface)

| ID | Path | Role |
|----|------|------|
| weekly_cycle | `scripts/ops/weekly_cycle.py` | Canonical product pipeline |
| golden_path | `scripts/golden_path.py` | Full validation path |
| resilient_cycle | `scripts/ops/resilient_cycle.py` | Fixture resilience cycle |
| run_pipeline (Make) | `Makefile` | Legacy composite |
| intel_pipeline | `scripts/intel_pipeline.py` | Intelligence component |
| opportunity_intel | `scripts/opportunity_intel/cli.py` | Opportunity intel CLI |
| workspace | `scripts/workspace/cli.py` | Operator facade |
| extra-dod-roi | `squads/extra-dod-roi/` | DoD ROI campaign orchestrator |

**Problem:** more than one “run the system” narrative. Target: one product pipeline; everything else explicit alias/diagnostic/legacy.

## Coverage implementations (multiplicity)

On main:

1. `scripts/coverage/coverage_contract.py` (+ CLI)
2. `scripts/coverage_gate.py`
3. `scripts/coverage_truth.py`
4. `scripts/coverage/multi_source_coverage.py`
5. `scripts/coverage/session_coverage_pipeline.py`
6. `scripts/coverage/entity_freshness.py` (freshness adjacency)

ADR-018 defines multi-metric coverage contract — still multiple code paths.

## Freshness implementations

1. `scripts/freshness_gate.py`
2. `scripts/coverage/entity_freshness.py`

## Ledger / audit surfaces (multiplicity)

On main (not unified):

1. `scripts/extra_ledger/cli.py`
2. `scripts/lib/manual_override_ledger.py`
3. `scripts/fix/rebuild_evidence_ledger.py`
4. `scripts/ops/alert_pipeline.py` (`append_ledger`)
5. DB: `db/migrations/024_coverage_evidence_ledger.sql`
6. Docs ledgers under `docs/ops/ledger/` and campaign folders

**Not on main** (only open PRs): `scripts/ops/run_execution_ledger.py`, `scripts/ops/decision_pack.py`, `scripts/cto/*`.

## Data / schema lines

- PostgreSQL migrations: **62** SQL files under `db/migrations/`
- Operational source of truth: PostgreSQL (ADR/dev docs)
- OCDS: thin bridge `scripts/ocds_bridge/` (serialize only; not physical model)

## Dependencies (direct, production-ish)

From `requirements.txt` (12 direct pins/ranges):

- httpx, requests, openai, psycopg2, python-dotenv, pyyaml
- reportlab, openpyxl, rich, lxml, beautifulsoup4, rapidfuzz

**Not present on main:** dbt, Soda, Splink, PyMuPDF, XlsxWriter, fpdf2, rule-engine, Redis runtime requirement (optional code paths exist).

## Module surface (top-level `scripts/`)

Collect / raw / normalize / intel / decision / delivery are **not** cleanly layered as directories; they are packages/scripts side-by-side (`collect/`, `crawl/`, `coverage/`, `opportunity_intel/`, `ops/`, `reports/`, `workspace/`, `intel_*.py`, etc.).

## Open PR inventory (at baseline time)

| PR | Title (short) | Base → Head | Draft | CI full suite |
|----|---------------|-------------|-------|---------------|
| #48 | CTO Autopilot | main → feat/cto… | no | **FAIL** |
| #50 | cycle-1 ledger | #48 branch → canary | yes | incomplete |
| #51 | cycle-2 reconstruct | #50 → canary tip | yes | incomplete |
| #52 | decision loop | main → goal/extra-decision… | no | **FAIL** |
| #53 | §29 ledger (on top of #52 material) | main → goal/roi-rastreabilidade… | no | SKIPPED/partial |

Full disposition: [`PR-DISPOSITION.md`](./PR-DISPOSITION.md).

## Known residual problems (baseline)

1. Multiple operational entrypoints without enforced single product path.
2. Multiple coverage/freshness/ledger implementations.
3. Full CI suite red or skipped on open product PRs — cannot treat SKIPPED as green.
4. Large open DoD surface (1044 open) with campaign-driven partial flips.
5. Stacked CTO PRs (#48→#50→#51) mix agent governance with product paths.
6. Decision loop capability exists only on PR branches, not main.
7. Documentation still references multiple “next steps” / campaigns without a single architecture target page.

## Out of scope for this baseline PR

- No production code change.
- No dependency adoption.
- No DoD mass flips.
- No merge/close of open PRs.
