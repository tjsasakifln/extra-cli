# Story: Critical Issues Wave 1

**Status:** Ready for Review
**Branch:** `agent/critical-issues-wave-1`
**Base:** `origin/main` at `fffdd3ff5d08702013fe2e2f405b945be2d7ba39`
**Capability:** Fail-closed multifonte collection, packaging, and national-contract truth

## Goal

Resolve the ten open `priority:p0` + `risk:high` issues with the highest
triage score that fit one reviewable capability and are not blocked by unmet
human or infrastructure prerequisites.

## Selection and order

The repository had 108 open issues on 2026-08-12. P0/high ties were ordered by
the repository triage formula (impact, quick-win bonus, and effort penalty),
then by critical-path unlocks. The resulting scope is:

1. #303 — PNCP contracts terminal state and page cap
2. #286 — structured `blocking_reasons`
3. #237 — preserve per-source terminal result
4. #245 — separate structural QA from delivery readiness
5. #234 — block scale before an approved stratified pilot
6. #278 — canonical systemd user and paths
7. #288 — remove silent 10,000-observation truncation
8. #233 — isolate packages by collection/run lineage
9. #311 — preserve supplier identity types
10. #313 — separate buyer and supplier roles in canonical contracts

## Acceptance criteria

### #303 — PNCP contract completion

- [x] A non-empty page produces `SUCCESS_DATA`.
- [x] A window completes only on proven zero or declared page exhaustion.
- [x] Intermediate failure, page cap, transform rejection, or incomplete
  persistence does not advance the checkpoint.
- [x] Window evidence exposes request/scope completion, page counts, and
  persisted count.
- [x] A partially successful set of windows never becomes global success.

### Remaining issues

- [x] #286: BLOCKED packages contain ordered structured blockers reconciled
  across PDF, XLSX, README, manifest, and exit status.
- [x] #237: source success remains visible when another source degrades, while
  the aggregate remains fail-closed.
- [x] #245: `structural_qa` and `delivery_readiness` are independent gates and
  both are required for delivery.
- [x] #234: scale beyond 30 entities requires a valid, hash-bound, human-approved
  stratified pilot artifact.
- [x] #278: provisioned systemd units use the canonical service user and
  `/opt`/`/var/lib` paths with preflight validation.
- [x] #288: all eligible snapshot observations are read without a silent fixed
  limit, with stable pagination/streaming evidence.
- [x] #233: every packaged observation is bound to the selected collection/run,
  with explicit reuse provenance only.
- [x] #311: CNPJ, CPF, foreign, and unknown supplier identifiers remain distinct;
  CPF is never padded or joined as CNPJ.
- [x] #313: canonical contract views expose separate buyer and supplier
  identities and consumers migrate to the corrected version.

## Quality gates

- Focused test for each issue before its atomic commit.
- `python3 -m pytest tests/ -q --tb=no -x`.
- `python3 -m scripts.golden_path --dsn "$LOCAL_DATALAKE_DSN"`.
- Generated-artifact and PR-reviewability policies against `origin/main`.
- Exact PR HEAD green in canonical GitHub Actions.

## File list

- `DOD.md`
- `Makefile`
- `db/migrations/076_contract_supplier_identity.sql`
- `db/migrations/077_contract_roles_canonical_v2.sql`
- `deploy/install.sh`
- `deploy/provision-vps.sh`
- `deploy/systemd/extra-process-documents-incremental.service`
- `deploy/systemd/extra-process-documents-incremental.timer`
- `deploy/systemd/templates/extra-process-documents-incremental.service.in`
- `deploy/systemd/templates/extra-process-documents-incremental.timer.in`
- `docs/ops/contract-roles-v2.md`
- `docs/ops/critical-issues-wave-1-handoff.md`
- `docs/ops/netcup-inventory-live.md`
- `docs/ops/pilot-scale-approval.md`
- `docs/security/supplier-identity-privacy.md`
- `docs/stories/story-critical-issues-wave-1.md`
- `requirements.txt`
- `scripts/confenge_target_fit/store.py`
- `scripts/contracts_identity.py`
- `scripts/crawl/contracts_crawler.py`
- `scripts/crawl/pncp_crawler_adapter.py`
- `scripts/crawl/resilience/pipeline.py`
- `scripts/linkage/pipeline.py`
- `scripts/opportunity_intel/competitive_intel_validation.py`
- `scripts/ops/contract_market_intelligence.py`
- `scripts/ops/daily_multi_source_collect.py`
- `scripts/ops/deliverable_b_competitors.py`
- `scripts/ops/live_consulting_pack.py`
- `scripts/ops/multi_source_open_pack/db_loaders.py`
- `scripts/ops/multi_source_open_pack/pilot_gate.py`
- `scripts/ops/multi_source_open_pack/pipeline.py`
- `scripts/ops/multi_source_open_pack/render_pack.py`
- `scripts/ops/provision_process_documents_systemd.py`
- `scripts/ops/resilient_cycle.py`
- `scripts/ops/run_contracts_pilot.py`
- `scripts/ops/validate_systemd.py`
- `scripts/ops/weekly_cycle.py`
- `scripts/ops/weekly_decision_artifacts.py`
- `scripts/process_documents/cli.py`
- `scripts/process_documents/collect.py`
- `scripts/schema/audit_sql_references.py`
- `scripts/schema/diagnostics.py`
- `tests/integration/test_all_sql_references.py`
- `tests/integration/test_migration_fresh_install.py`
- `tests/process_documents/test_entity_queue_and_process_card.py`
- `tests/test_cmi_contract_market_intelligence.py`
- `tests/test_contract_roles_v2.py`
- `tests/test_contract_supplier_identity.py`
- `tests/test_contracts_crawler.py`
- `tests/test_contracts_pilot_completion.py`
- `tests/test_daily_multi_source_collect.py`
- `tests/test_live_consulting_pack.py`
- `tests/test_local_resilience.py`
- `tests/test_multi_source_open_pack.py`
- `tests/test_process_documents_systemd.py`
- `tests/test_snapshot_observation_loader.py`
- `tests/test_upsert_contracts.py`
- `tests/test_weekly_decision_artifacts.py`

## Change log

| Date | Issue | State | Evidence |
|---|---:|---|---|
| 2026-08-12 | #303 | VERIFIED_LOCAL | 76 focused legacy/new tests pass; ruff and diff-check pass |
| 2026-08-12 | #286 | VERIFIED_LOCAL | 23 multi-source pack tests pass; codes reconcile in JSON/MD/XLSX/PDF |
| 2026-08-12 | #245 | VERIFIED_LOCAL | 25 pack tests pass; structural QA green remains delivery-blocked |
| 2026-08-12 | #237 | VERIFIED_LOCAL | 58 resilience/feeder tests pass; local success survives aggregate degradation |
| 2026-08-12 | #234 | VERIFIED_LOCAL | 103 focused tests pass; missing/mismatched approval stops before queue/package writes |
| 2026-08-12 | #278 | VERIFIED_LOCAL | 49 systemd/resilience tests pass; rendered pair verifies and reinstall is idempotent |
| 2026-08-12 | #288 | VERIFIED_LOCAL | 80 focused tests pass; 10,037-row snapshot reconciles without LIMIT or duplicates |
| 2026-08-12 | #233 | VERIFIED_LOCAL | 87 focused tests pass; package rejects foreign lineage and reconciles selected persisted/reused count |
| 2026-08-12 | #311 | VERIFIED_LOCAL | 150 focused tests pass; migration applies and transaction proves four identity types with CPF masked |
| 2026-08-12 | #313 | VERIFIED_LOCAL | 24 focused tests pass; adversarial DB test and four EXPLAIN plans prove role separation and indexes |
| 2026-08-12 | Wave | VERIFIED_LOCAL | Fresh PostgreSQL schema: 76 migrations applied, 2,085 entities seeded (1,093 in canonical radius); full suite: 4,279 passed, 126 skipped, 11 deselected; 49.6% coverage |
| 2026-08-12 | Wave | PARTIAL_EXTERNAL | Strict golden path exited 2: PCP fetched 147/inserted 135, ComprasGov success-zero, PNCP HTTP 504 after 413 s; freshness remained stale for PNCP/contracts; no readiness claim |
