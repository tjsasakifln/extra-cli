# Acceptance sets

## CODE_CANDIDATE_READY

Provable on this branch without production:

- Single candidate branch from contemporary `origin/main`
- Unique commits only (12 patch-ids + 116); no duplicate migrations 107–116
- `v_recent_engineering_wins` consumes class, sanitized dates, terminal lifecycle, official identity, independent clocks
- #545 live claims fail-closed (`UNKNOWN` without persisted event; `trigger_type` never RESULT_PUBLISHED/ADJUDICATED/HOMOLOGATED)
- `REVOGACAO|ANULACAO|RESCISAO` → `NOT_ACTIONABLE`
- Role NOLOGIN SELECT-only; no credential in code
- Cadastral contact is not decision-maker
- Adversarial cases covered by shipped-view tests
- Clean install, upgrade-from-106, idempotent re-apply, 116 rollback+reapply on ephemeral 127.0.0.1:5439
- `check_confenge_commercial_plane` PASS
- generated-artifacts policy PASS
- PR reviewability `--draft` PASS
- Draft PR only (not merged, not marked ready)

## PRODUCTION_EVIDENCE_PENDING

Metrics that only deploy/backfill on the commercial datalake can prove:

- Count of engineering-class labels actually stamped on persisted contracts
- Coverage of official `categoria_processo_*` after structural backfill
- Count of QUARANTINED dates (year 8406 and peers) after trigger rewrite
- `mv_supplier_structural_profile` row count and F1–F8 after refresh
- `v_orgaos_contratantes_projeto` non-zero organs with SC flag
- `v_supplier_cadastral_contact` hit-rate (email/phone present)
- `pncp_procurement_results` row count after ingest (today: zero live events)
- Actionable HOT/WARM cohort size after excluding terminal lifecycle
- Query time of `v_recent_engineering_wins` on ec-prod (local EXPLAIN is not that number)
