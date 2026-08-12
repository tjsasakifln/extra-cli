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
| #233 | VERIFIED | 87 loader/pack/weekly tests; exact run membership and reuse proof | exact-HEAD CI + main |
| #311 | VERIFIED | 150 crawler/consumer tests + real migration transaction for four types | exact-HEAD CI + main |
| #313 | VERIFIED | 24 linkage/schema tests; adversarial buyer/supplier DB proof + four indexed plans | exact-HEAD CI + main |

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
metadata. Collection/run isolation is implemented separately by #233 below.

## #233 verification

```text
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -o addopts= \
  tests/test_weekly_cycle.py tests/test_multi_source_open_pack.py \
  tests/test_snapshot_observation_loader.py \
  tests/test_weekly_decision_artifacts.py -q --tb=short
87 passed, 1 skipped
```

The weekly package now resolves one `opportunity_runs.id` from its canonical
`CollectionRun` and loads PNCP rows only through
`source_snapshot_membership`. The selected membership count must equal the
run's persisted count (or the explicitly reused count), and every streamed row
must carry that same run lineage. Reuse records the prior run, deterministic
SHA-256 over its membership, and in-SLA freshness proof in package metadata.
Unbound official-act/file discovery is disabled for the collection-isolated
path; a foreign or missing lineage fails before the package directory is
created.

## #311 verification

```text
PGCONNECT_TIMEOUT=2 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest \
  -o addopts= tests/test_contract_supplier_identity.py \
  tests/test_contracts_crawler.py tests/test_upsert_contracts.py \
  tests/test_contracts_pilot_completion.py tests/test_contracts_per_window_persist.py \
  tests/test_crawler_pncp.py tests/test_date_propagation.py \
  tests/commercial_leads/test_all_status_history.py \
  tests/commercial_leads/test_identity.py \
  tests/commercial_leads/test_registry_selection_independence.py \
  tests/test_cmi_contract_market_intelligence.py \
  tests/test_deliverable_b_competitors.py tests/test_live_consulting_pack.py \
  -q --tb=short
150 passed, 5 skipped

python3 -m scripts.ops.apply_migrations \
  --dsn postgresql://test:test@127.0.0.1:5433/extra_test
applied 076_contract_supplier_identity.sql
```

A rolled-back database transaction then inserted and read one CNPJ, CPF,
foreign and unknown contract through the real RPC. Only the CNPJ populated
`fornecedor_cnpj`; CPF exposed only `CPF:***.***.***-**` in its export field.
The crawler and alternate PNCP adapter share the typed normalizer, contracts
without CNPJ are retained, and commercial registry/intelligence discovery now
selects validated CNPJ identities only. Privacy handling is recorded in
`docs/security/supplier-identity-privacy.md`.

## #313 verification

```text
REQUIRE_TEST_DB=1 REQUIRE_REAL_DB=1 \
TEST_DSN=postgresql://test:test@127.0.0.1:5433/extra_test \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -o addopts= \
  tests/test_contract_roles_v2.py -q --tb=short
3 passed

PGCONNECT_TIMEOUT=2 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest \
  -o addopts= tests/test_canonical_entity_linkage.py \
  tests/test_competitive_intel_validation.py \
  tests/integration/test_all_sql_references.py -q --tb=short
21 passed, 2 skipped
```

Migration 077 applied successfully to `extra_test`. The rolled-back adversarial
test used different buyer and supplier CNPJ roots that each corresponded to a
different public entity: v2 linked `buyer_entity_id` only to the `orgao_cnpj`
root and emitted the supplier as a separate content-addressed identity. The
role ledger persisted match methods, confidence, reason codes, run and
snapshot. Four `EXPLAIN (ANALYZE, BUFFERS)` assertions used the buyer,
supplier, contract primary-key and snapshot indexes. The sole Python consumer
of v1 now queries `v_contracts_canonical_v2`; v1 remains present but marked
deprecated. Evidence and the #291/#292 migration rule are in
`docs/ops/contract-roles-v2.md`.
