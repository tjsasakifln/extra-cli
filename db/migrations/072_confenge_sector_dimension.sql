-- 072_confenge_sector_dimension.sql
-- Explicit construction-sector dimension, independent from commercial target-fit.

BEGIN;

-- Migration 071 predated TARGET_INSUFFICIENT_EVIDENCE in the active table.
ALTER TABLE public.confenge_company_target_fit_current
    DROP CONSTRAINT IF EXISTS confenge_company_target_fit_current_target_fit_class_check;
ALTER TABLE public.confenge_company_target_fit_current
    ADD CONSTRAINT confenge_company_target_fit_current_target_fit_class_check
    CHECK (target_fit_class IN (
        'TARGET_CONFIRMED',
        'TARGET_PROBABLE_RESEARCH',
        'TARGET_INSUFFICIENT_EVIDENCE',
        'TARGET_OUT_OF_SCOPE',
        'REFRESH_FAILED',
        'RECOMPUTE_REQUIRED'
    ));

CREATE TABLE IF NOT EXISTS public.confenge_company_sector_current (
    company_key             TEXT PRIMARY KEY,
    cnpj_raiz               CHAR(8) NOT NULL UNIQUE,
    sector_class            TEXT NOT NULL CHECK (sector_class IN (
        'CONSTRUCTION_CONFIRMED',
        'CONSTRUCTION_PROBABLE',
        'NON_CONSTRUCTION',
        'SECTOR_INSUFFICIENT_EVIDENCE'
    )),
    sector_confidence       DOUBLE PRECISION NOT NULL DEFAULT 0
        CHECK (sector_confidence >= 0 AND sector_confidence <= 1),
    sector_version          TEXT NOT NULL,
    sector_classifier_sha256 TEXT NOT NULL,
    sector_reason_codes     JSONB NOT NULL DEFAULT '[]'::jsonb,
    sector_evidence         JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_sector_fit       TEXT NOT NULL DEFAULT '',
    activity_class          TEXT NOT NULL DEFAULT '',
    relevant_contract_count INTEGER NOT NULL DEFAULT 0,
    total_contract_count    INTEGER NOT NULL DEFAULT 0,
    input_fingerprint       TEXT NOT NULL,
    source_watermark        TEXT NOT NULL DEFAULT '',
    source_max_updated_at   TIMESTAMPTZ,
    computed_at             TIMESTAMPTZ NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS confenge_sector_current_class_idx
    ON public.confenge_company_sector_current (sector_class, updated_at);
CREATE INDEX IF NOT EXISTS confenge_sector_current_watermark_idx
    ON public.confenge_company_sector_current (source_watermark);

COMMENT ON TABLE public.confenge_company_sector_current IS
'Canonical sector membership per CNPJ root. Independent from target-fit and refreshed by the shared dirty/CDC worker.';

CREATE TABLE IF NOT EXISTS public.confenge_company_sector_history (
    id                      BIGSERIAL PRIMARY KEY,
    company_key             TEXT NOT NULL,
    cnpj_raiz               CHAR(8) NOT NULL,
    sector_class            TEXT NOT NULL,
    sector_confidence       DOUBLE PRECISION NOT NULL DEFAULT 0,
    sector_version          TEXT NOT NULL,
    sector_classifier_sha256 TEXT NOT NULL,
    sector_reason_codes     JSONB NOT NULL DEFAULT '[]'::jsonb,
    sector_evidence         JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_sector_fit       TEXT NOT NULL DEFAULT '',
    activity_class          TEXT NOT NULL DEFAULT '',
    relevant_contract_count INTEGER NOT NULL DEFAULT 0,
    total_contract_count    INTEGER NOT NULL DEFAULT 0,
    input_fingerprint       TEXT NOT NULL,
    source_watermark        TEXT NOT NULL DEFAULT '',
    source_max_updated_at   TIMESTAMPTZ,
    computed_at             TIMESTAMPTZ NOT NULL,
    previous_sector_class   TEXT,
    recorded_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS confenge_sector_history_company_idx
    ON public.confenge_company_sector_history (company_key, computed_at DESC);

COMMENT ON TABLE public.confenge_company_sector_history IS
'Append-only sector history. Target-fit transitions never delete or redefine sector membership.';

COMMIT;
