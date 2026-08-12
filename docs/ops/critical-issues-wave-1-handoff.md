# Critical Issues Wave 1 — Handoff

**Branch:** `agent/critical-issues-wave-1`  
**Scope:** #303, #286, #237, #245, #234, #278, #288, #233, #311, #313  
**Truth ceiling:** branch evidence is at most `VERIFIED`; issue closure and DOD
acceptance require exact-HEAD CI and the repository's human/main gates.

## Current state

| Issue | State | Reproducible evidence | Remaining gate |
|---:|---|---|---|
| #303 | VERIFIED | Focused contracts suite; new zero/data/multipage/error/cap/persistence cases | exact-HEAD CI + main |
| #286 | VERIFIED | 23 pack tests; blocker codes reconciled across four formats | exact-HEAD CI + main |
| #237 | VERIFIED | 58 resilience/feeder tests; local terminal fields independent of aggregate exit | exact-HEAD CI + main |
| #245 | VERIFIED | 25 pack tests; independent QA/readiness gates in all formats | exact-HEAD CI + main |
| #234 | VERIFIED | 103 pack/queue/weekly tests; preflight before state/output writes | exact-HEAD CI + main |
| #278 | VERIFIED | 49 systemd/resilience tests; rendered pair + idempotent install smoke | exact-HEAD CI + main |
| #288 | VERIFIED | 80 loader/pack/weekly tests; 10,037 rows reconcile to one SQL snapshot | exact-HEAD CI + main |
| #233 | OPEN | — | implementation and test |
| #311 | OPEN | — | implementation and test |
| #313 | OPEN | — | implementation and test |

## #303 verification

```text
python3 -m pytest tests/test_contracts_crawler.py \
  tests/test_contracts_pilot_completion.py \
  tests/test_contracts_per_window_persist.py -q --tb=short
76 passed

python3 -m ruff check scripts/crawl/contracts_crawler.py \
  scripts/ops/run_contracts_pilot.py tests/test_contracts_crawler.py \
  tests/test_contracts_pilot_completion.py
All checks passed!
```

No live coverage, `LOCAL_READY`, or `VPS_OPERATIONAL` claim is made.

## #286 verification

```text
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -o addopts= \
  tests/test_multi_source_open_pack.py -q --tb=short
23 passed

python3 -m ruff check scripts/ops/multi_source_open_pack/pipeline.py \
  scripts/ops/multi_source_open_pack/render_pack.py \
  tests/test_multi_source_open_pack.py
All checks passed!
```

The generated fixture package is `BLOCKED` and carries ordered blocker objects
with `code`, `evidence`, `owner`, and `next_action`. README, manifest, workbook
and PDF expose the identical code sequence. No readiness seal is claimed.

## #245 verification

```text
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -o addopts= \
  tests/test_multi_source_open_pack.py -q --tb=short
25 passed
```

The fixture proves `structural_qa.ok=true` can coexist honestly with
`delivery_readiness.ok=false`; in that state `deliverable=false`, terminal state
is `BLOCKED`, and the CLI exits non-zero. Manifest, README, XLSX and PDF expose
the same gate states.

## #237 verification

```text
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -o addopts= \
  tests/test_daily_multi_source_collect.py tests/test_local_resilience.py \
  -q --tb=short
58 passed

python3 -m ruff check scripts/crawl/resilience/pipeline.py \
  scripts/ops/resilient_cycle.py scripts/ops/daily_multi_source_collect.py \
  tests/test_daily_multi_source_collect.py tests/test_local_resilience.py
All checks passed!
```

The source node now owns `terminal_status`, `request_completed`, and
`scope_complete`. A degraded aggregate exit remains visible under `aggregate`
but no longer rewrites a completed SC Compras result; a genuinely incomplete
SC Compras node remains `partial`.

## #234 verification

```text
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -o addopts= \
  tests/test_multi_source_open_pack.py \
  tests/process_documents/test_entity_queue_and_process_card.py \
  tests/process_documents/test_daily_rotation_multisource.py \
  tests/test_weekly_decision_artifacts.py tests/test_weekly_cycle.py \
  -q --tb=short
103 passed, 1 skipped
```

The skip is a pre-existing environment-dependent weekly test. The scale gate
runs before queue initialization, observation loading, coverage generation, or
package directory creation. It validates exactly 30 stratified pilot entities,
multi-source pagination/zero/dedup evidence and human approval, all bound to the
active universe and source-policy hashes. Usage and schema are documented in
`docs/ops/pilot-scale-approval.md`.

## #278 verification

```text
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -o addopts= \
  tests/test_process_documents_systemd.py tests/test_local_resilience.py \
  -q --tb=short
49 passed

bash -n deploy/install.sh deploy/provision-vps.sh
```

The process-documents unit now uses `extra-consultoria`,
`/opt/extra-consultoria`, `/var/lib/extra-consultoria`, the application venv,
and the canonical env file. Provisioning renders timer and service from one
configuration with identical deploy/config hashes, runs preflight and
`systemd-analyze verify`, and is byte-idempotent on reinstall. Its smoke claim
is explicitly `UNIT_INSTALL_SMOKE_ONLY` with `vps_operational=false`. Debian 13
compatibility and the non-destructive, no-reimage procedure are documented in
`docs/ops/netcup-inventory-live.md`.

## #288 verification

```text
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -o addopts= \
  tests/test_snapshot_observation_loader.py \
  tests/test_multi_source_open_pack.py \
  tests/test_weekly_decision_artifacts.py tests/test_weekly_cycle.py \
  -q --tb=short
80 passed, 1 skipped
```

The PostgreSQL loaders no longer use a fixed row limit. A server-side cursor
streams a single materialized SQL statement ordered by unique `id`; that same
statement publishes `txid_current_snapshot()` and the eligible `COUNT(*)`.
Returning a prefix, duplicate, changed snapshot, or memory estimate above the
512 MiB VPS budget raises `SnapshotReconciliationError`. The 10,037-row test
also measures actual peak allocation below the budget. Observation-sheet and
shortlist cuts remain presentation-only and are explicitly labeled in pack
metadata. Cross-source lineage selection remains the separate #233 commit.
