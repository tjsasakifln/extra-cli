-- ============================================================================
-- Migration 069: Predictive intelligence layer (point-in-time datasets, models,
-- immutable predictions, outcomes, drift, claim states)
-- Note: 068 reserved by decision-outcome-memory (PR #198); predictive uses 069.
-- ============================================================================
-- Campaign: EXTRA-PREDICTIVE-INTELLIGENCE-PRODUCTION-01
-- ============================================================================

BEGIN;

-- Dataset build runs
CREATE TABLE IF NOT EXISTS public.predictive_dataset_runs (
    run_id                  TEXT PRIMARY KEY,
    target_name             TEXT NOT NULL,
    dataset_version         TEXT NOT NULL,
    feature_schema_version  TEXT NOT NULL,
    as_of_min               TIMESTAMPTZ,
    as_of_max               TIMESTAMPTZ,
    n_examples              INTEGER NOT NULL DEFAULT 0,
    n_positives             INTEGER NOT NULL DEFAULT 0,
    n_negatives             INTEGER NOT NULL DEFAULT 0,
    n_rejected_invalid_neg  INTEGER NOT NULL DEFAULT 0,
    label_definition        TEXT NOT NULL,
    source_tables           TEXT[] NOT NULL DEFAULT '{}',
    coverage_json           JSONB NOT NULL DEFAULT '{}'::jsonb,
    leakage_checks_json     JSONB NOT NULL DEFAULT '{}'::jsonb,
    status                  TEXT NOT NULL DEFAULT 'built',
    blockers                JSONB NOT NULL DEFAULT '[]'::jsonb,
    code_commit_sha         TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_predictive_dataset_runs_target
    ON public.predictive_dataset_runs (target_name, created_at DESC);

-- Point-in-time training examples
CREATE TABLE IF NOT EXISTS public.predictive_training_examples (
    example_id              TEXT PRIMARY KEY,
    run_id                  TEXT NOT NULL REFERENCES public.predictive_dataset_runs(run_id),
    target_name             TEXT NOT NULL,
    entity_id               TEXT,
    procurement_id          TEXT,
    supplier_id             TEXT,
    as_of_at                TIMESTAMPTZ NOT NULL,
    prediction_horizon      TEXT,
    label_window_start      TIMESTAMPTZ NOT NULL,
    label_window_end        TIMESTAMPTZ NOT NULL,
    label_value             DOUBLE PRECISION NOT NULL,
    label_source            TEXT NOT NULL,
    label_quality           TEXT NOT NULL DEFAULT 'ok',
    features_json           JSONB NOT NULL DEFAULT '{}'::jsonb,
    feature_schema_version  TEXT NOT NULL,
    source_run_ids          TEXT[] NOT NULL DEFAULT '{}',
    source_max_event_at     TIMESTAMPTZ,
    dataset_version         TEXT NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_pit_source_max CHECK (
        source_max_event_at IS NULL OR source_max_event_at <= as_of_at
    )
);

CREATE INDEX IF NOT EXISTS idx_predictive_examples_target_asof
    ON public.predictive_training_examples (target_name, as_of_at);

CREATE INDEX IF NOT EXISTS idx_predictive_examples_run
    ON public.predictive_training_examples (run_id);

-- Model registry
CREATE TABLE IF NOT EXISTS public.predictive_models (
    model_id                TEXT PRIMARY KEY,
    target_name             TEXT NOT NULL,
    model_version           TEXT NOT NULL,
    model_family            TEXT NOT NULL,
    training_dataset_version TEXT NOT NULL,
    feature_schema_version  TEXT NOT NULL,
    trained_at              TIMESTAMPTZ NOT NULL,
    training_window_start   TIMESTAMPTZ,
    training_window_end     TIMESTAMPTZ,
    validation_window_start TIMESTAMPTZ,
    validation_window_end   TIMESTAMPTZ,
    test_window_start       TIMESTAMPTZ,
    test_window_end         TIMESTAMPTZ,
    artifact_sha256         TEXT,
    artifact_uri            TEXT,
    code_commit_sha         TEXT,
    metrics_json            JSONB NOT NULL DEFAULT '{}'::jsonb,
    baselines_json          JSONB NOT NULL DEFAULT '{}'::jsonb,
    supported_cohorts       JSONB NOT NULL DEFAULT '[]'::jsonb,
    unsupported_cohorts     JSONB NOT NULL DEFAULT '[]'::jsonb,
    approval_status         TEXT NOT NULL DEFAULT 'candidate',
    approved_by             TEXT,
    approved_at             TIMESTAMPTZ,
    limitations             JSONB NOT NULL DEFAULT '[]'::jsonb,
    rollback_model_id       TEXT,
    calibrated              BOOLEAN NOT NULL DEFAULT FALSE,
    calibration_method      TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (target_name, model_version)
);

CREATE INDEX IF NOT EXISTS idx_predictive_models_target_status
    ON public.predictive_models (target_name, approval_status);

CREATE TABLE IF NOT EXISTS public.predictive_model_metrics (
    metric_id               BIGSERIAL PRIMARY KEY,
    model_id                TEXT NOT NULL REFERENCES public.predictive_models(model_id),
    fold_id                 TEXT NOT NULL,
    split_role              TEXT NOT NULL,
    cohort                  TEXT NOT NULL DEFAULT 'overall',
    metrics_json            JSONB NOT NULL DEFAULT '{}'::jsonb,
    n_examples              INTEGER,
    n_positives             INTEGER,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_predictive_model_metrics_model
    ON public.predictive_model_metrics (model_id);

CREATE TABLE IF NOT EXISTS public.predictive_model_artifacts (
    artifact_id             TEXT PRIMARY KEY,
    model_id                TEXT NOT NULL REFERENCES public.predictive_models(model_id),
    artifact_kind           TEXT NOT NULL,
    sha256                  TEXT NOT NULL,
    uri                     TEXT,
    bytes                   BIGINT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Immutable predictions (corrections = new version row)
CREATE TABLE IF NOT EXISTS public.predictive_predictions (
    prediction_id           TEXT PRIMARY KEY,
    prediction_group_id     TEXT NOT NULL,
    version                 INTEGER NOT NULL DEFAULT 1,
    supersedes_prediction_id TEXT,
    target_name             TEXT NOT NULL,
    model_id                TEXT REFERENCES public.predictive_models(model_id),
    model_version           TEXT,
    artifact_sha256         TEXT,
    dataset_version         TEXT,
    claim_id                TEXT NOT NULL,
    claim_state             TEXT NOT NULL,
    entity_id               TEXT,
    procurement_id          TEXT,
    supplier_id             TEXT,
    as_of_at                TIMESTAMPTZ NOT NULL,
    prediction_horizon      TEXT,
    valid_until             TIMESTAMPTZ,
    score                   DOUBLE PRECISION,
    probability             DOUBLE PRECISION,
    prediction_interval_lo  DOUBLE PRECISION,
    prediction_interval_hi  DOUBLE PRECISION,
    quantiles_json          JSONB NOT NULL DEFAULT '{}'::jsonb,
    features_json           JSONB NOT NULL DEFAULT '{}'::jsonb,
    sample_support          INTEGER,
    cohort                  TEXT,
    limitations             JSONB NOT NULL DEFAULT '[]'::jsonb,
    prediction_allowed      BOOLEAN NOT NULL DEFAULT FALSE,
    is_calibrated           BOOLEAN NOT NULL DEFAULT FALSE,
    mode                    TEXT NOT NULL DEFAULT 'shadow',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (prediction_group_id, version)
);

CREATE INDEX IF NOT EXISTS idx_predictive_predictions_asof
    ON public.predictive_predictions (target_name, as_of_at DESC);

CREATE INDEX IF NOT EXISTS idx_predictive_predictions_entity
    ON public.predictive_predictions (entity_id, target_name);

-- Trigger: forbid UPDATE of immutable prediction payload columns
CREATE OR REPLACE FUNCTION public.predictive_predictions_immutability()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF NEW.prediction_id IS DISTINCT FROM OLD.prediction_id
           OR NEW.score IS DISTINCT FROM OLD.score
           OR NEW.probability IS DISTINCT FROM OLD.probability
           OR NEW.features_json IS DISTINCT FROM OLD.features_json
           OR NEW.as_of_at IS DISTINCT FROM OLD.as_of_at
           OR NEW.model_id IS DISTINCT FROM OLD.model_id
           OR NEW.version IS DISTINCT FROM OLD.version
        THEN
            RAISE EXCEPTION
                'predictive_predictions is immutable; insert a new version instead (prediction_id=%)',
                OLD.prediction_id;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_predictive_predictions_immutability
    ON public.predictive_predictions;
CREATE TRIGGER trg_predictive_predictions_immutability
    BEFORE UPDATE ON public.predictive_predictions
    FOR EACH ROW
    EXECUTE FUNCTION public.predictive_predictions_immutability();

CREATE TABLE IF NOT EXISTS public.predictive_prediction_explanations (
    explanation_id          BIGSERIAL PRIMARY KEY,
    prediction_id           TEXT NOT NULL REFERENCES public.predictive_predictions(prediction_id),
    factors_up              JSONB NOT NULL DEFAULT '[]'::jsonb,
    factors_down            JSONB NOT NULL DEFAULT '[]'::jsonb,
    baseline_comparison     JSONB NOT NULL DEFAULT '{}'::jsonb,
    coverage_notes          TEXT,
    method                  TEXT NOT NULL DEFAULT 'feature_decomposition',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.predictive_outcomes (
    outcome_id              TEXT PRIMARY KEY,
    prediction_id           TEXT NOT NULL REFERENCES public.predictive_predictions(prediction_id),
    observed_at             TIMESTAMPTZ NOT NULL,
    label_value             DOUBLE PRECISION,
    outcome_source          TEXT NOT NULL,
    outcome_quality         TEXT NOT NULL DEFAULT 'ok',
    error_abs               DOUBLE PRECISION,
    brier_component         DOUBLE PRECISION,
    metadata_json           JSONB NOT NULL DEFAULT '{}'::jsonb,
    reconciled_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Decision Memory linkage (commercial facts are canonical in dm_outcome_events)
    dm_outcome_event_id     UUID NULL,
    link_status             TEXT NOT NULL DEFAULT 'NOT_APPLICABLE_MODEL_ONLY'
                            CHECK (link_status IN (
                                'LINKED_DM',
                                'UNLINKED_LEGACY',
                                'HISTORICAL_UNVERIFIED',
                                'NOT_APPLICABLE_MODEL_ONLY'
                            )),
    UNIQUE (prediction_id)
);

-- Upgrade path when table already exists without DM columns (idempotent)
ALTER TABLE public.predictive_outcomes
    ADD COLUMN IF NOT EXISTS dm_outcome_event_id UUID NULL;
ALTER TABLE public.predictive_outcomes
    ADD COLUMN IF NOT EXISTS link_status TEXT NOT NULL DEFAULT 'NOT_APPLICABLE_MODEL_ONLY';

-- FK only when Decision Memory migration 068 is present
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'dm_outcome_events'
    ) AND NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_predictive_outcomes_dm_outcome'
    ) THEN
        ALTER TABLE public.predictive_outcomes
            ADD CONSTRAINT fk_predictive_outcomes_dm_outcome
            FOREIGN KEY (dm_outcome_event_id)
            REFERENCES public.dm_outcome_events(event_id);
    END IF;
END $$;

-- Ensure CHECK on link_status for upgrade path
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_predictive_outcomes_link_status'
    ) THEN
        ALTER TABLE public.predictive_outcomes
            ADD CONSTRAINT ck_predictive_outcomes_link_status
            CHECK (link_status IN (
                'LINKED_DM',
                'UNLINKED_LEGACY',
                'HISTORICAL_UNVERIFIED',
                'NOT_APPLICABLE_MODEL_ONLY'
            ));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_predictive_outcomes_dm_event
    ON public.predictive_outcomes (dm_outcome_event_id)
    WHERE dm_outcome_event_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.predictive_drift_runs (
    drift_run_id            TEXT PRIMARY KEY,
    model_id                TEXT REFERENCES public.predictive_models(model_id),
    target_name             TEXT NOT NULL,
    window_start            TIMESTAMPTZ NOT NULL,
    window_end              TIMESTAMPTZ NOT NULL,
    psi_json                JSONB NOT NULL DEFAULT '{}'::jsonb,
    calibration_json        JSONB NOT NULL DEFAULT '{}'::jsonb,
    brier                   DOUBLE PRECISION,
    brier_skill_score       DOUBLE PRECISION,
    ece                     DOUBLE PRECISION,
    coverage_json           JSONB NOT NULL DEFAULT '{}'::jsonb,
    decision                TEXT NOT NULL DEFAULT 'ok',
    reasons                 JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.predictive_claim_states (
    claim_id                TEXT PRIMARY KEY,
    state                   TEXT NOT NULL,
    evidence_json           JSONB NOT NULL DEFAULT '{}'::jsonb,
    blockers_json           JSONB NOT NULL DEFAULT '[]'::jsonb,
    limitations_json        JSONB NOT NULL DEFAULT '[]'::jsonb,
    model_id                TEXT,
    model_version           TEXT,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Client profile calibration versions (Extra personalization)
CREATE TABLE IF NOT EXISTS public.predictive_client_profile_versions (
    profile_version_id      TEXT PRIMARY KEY,
    client_id               TEXT NOT NULL,
    version                 INTEGER NOT NULL,
    profile_json            JSONB NOT NULL DEFAULT '{}'::jsonb,
    missing_critical        JSONB NOT NULL DEFAULT '[]'::jsonb,
    author                  TEXT,
    source                  TEXT NOT NULL DEFAULT 'elicitation',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (client_id, version)
);

COMMIT;
