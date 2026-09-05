# Rollout plan (NOT executed)

This is documentation only. Do not run against `ec-prod`. Do not start crawlers, backfills, refresh, SMTP, or cohort publication from this campaign.

## Later sequence (after #468 containment is lifted by its own campaign)

1. **Merge** this candidate to `main` only after GitHub CI is green on the exact HEAD and a human marks the draft ready. This campaign does not merge.
2. **Migrations 107 → 116** on the commercial datalake (upgrade from current main schema 106). Confirm ledger `_migrations`. Do not renumber.
3. **Backfills (separate change window)**
   - `apply_pncp_structural_fields` / `scripts/ops/backfill_pncp_structural_fields.py` (resume/limit)
   - `apply_contract_engineering_class` / `scripts/ops/backfill_engineering_class.py`
   - date-hygiene trigger already rewrites absurd dates on UPDATE; optional one-shot `UPDATE … SET data_assinatura = data_assinatura WHERE year >= 8000`
   - `scripts/ops/refresh_engineering_supplier_registry.py` (monthly, resumable)
   - `REFRESH MATERIALIZED VIEW CONCURRENTLY mv_supplier_structural_profile`
4. **ec-prod validations (not run here)**
   - counts of `QUARANTINED` vs `VALID`
   - class distribution; adversarial sample
   - `REVOGACAO|ANULACAO|RESCISAO` never HOT/WARM/ACTIVE in the view
   - `procurement_result_status` remains UNKNOWN until results ingest exists
5. **Views / role**
   - `confenge_commercial_read_v1` already created by 115 (NOLOGIN)
   - GRANT SELECT already in 115/116; do not put a password in repo
6. **Cohort**
   - small private wedge: engineering contracts recently signed/published, class + lifecycle + cadastral contact
   - exclude terminal lifecycle
   - do not treat cadastral email/phone as decision-maker
   - do not send SMTP from this plane

## Explicitly out of this campaign

Merge, deploy, production backfill, commercial refresh, contact discovery, feed, Warmbly import, SMTP, crawler/target-fit starts, timer/service changes, `ec-prod` commands, #468 files.
