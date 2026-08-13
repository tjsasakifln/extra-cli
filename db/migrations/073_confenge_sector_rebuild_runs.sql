-- 073_confenge_sector_rebuild_runs.sql
-- Audit ledger for atomic full-lake sector rebuilds.

BEGIN;

CREATE TABLE IF NOT EXISTS public.confenge_sector_rebuild_runs (
    run_id                       UUID PRIMARY KEY,
    status                       TEXT NOT NULL CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
    started_at                   TIMESTAMPTZ NOT NULL,
    completed_at                 TIMESTAMPTZ,
    database_snapshot            TEXT NOT NULL,
    transaction_timestamp        TIMESTAMPTZ NOT NULL,
    source_cdc_watermark         TEXT NOT NULL,
    source_contract_rows         BIGINT NOT NULL,
    supplier_roots_observed      BIGINT NOT NULL,
    materialized_roots           BIGINT NOT NULL,
    stale_current_roots_archived BIGINT NOT NULL DEFAULT 0,
    sector_classes               JSONB NOT NULL,
    query_sha256                 TEXT NOT NULL,
    classifier_sha256            TEXT NOT NULL,
    manifest                     JSONB NOT NULL,
    created_at                   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS confenge_sector_rebuild_runs_completed_idx
    ON public.confenge_sector_rebuild_runs (completed_at DESC);

COMMENT ON TABLE public.confenge_sector_rebuild_runs IS
'Append-only audit ledger for full supplier-root sector materialization from one REPEATABLE READ source snapshot.';

-- Shadow target-fit must carry the same classifier lineage as ACTIVE current.
ALTER TABLE public.confenge_target_fit_shadow
    ADD COLUMN IF NOT EXISTS classifier_sha TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS confenge_tf_shadow_version_classifier_idx
    ON public.confenge_target_fit_shadow (target_fit_version, classifier_sha);

-- Preserve one observed, valid CNPJ-14 per sector root for contact enrichment.
ALTER TABLE public.confenge_company_sector_current
    ADD COLUMN IF NOT EXISTS representative_cnpj14 CHAR(14);

ALTER TABLE public.confenge_company_sector_history
    ADD COLUMN IF NOT EXISTS representative_cnpj14 CHAR(14);

COMMENT ON COLUMN public.confenge_company_sector_current.representative_cnpj14 IS
'Valid establishment CNPJ observed in canonical source data; NULL is honest and never synthesized.';

COMMENT ON COLUMN public.confenge_company_sector_history.representative_cnpj14 IS
'Append-only lineage for the establishment identity used by bounded enrichment workers.';

COMMIT;
