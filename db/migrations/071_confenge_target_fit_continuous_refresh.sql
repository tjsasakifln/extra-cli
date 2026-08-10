-- 071_confenge_target_fit_continuous_refresh.sql
-- CONFENGE target-fit as a durable, incremental materialization of the datalake.
-- Additive only. ETL path never depends on these tables.
-- Idempotent: IF NOT EXISTS guards.

BEGIN;

-- ---------------------------------------------------------------------------
-- Dirty queue (logical CDC work items, unit = CNPJ root / company group)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.confenge_target_fit_dirty (
    id                  BIGSERIAL PRIMARY KEY,
    company_key         TEXT NOT NULL,
    cnpj_raiz           CHAR(8) NOT NULL,
    reason              TEXT NOT NULL,
    source_entity       TEXT NOT NULL DEFAULT 'pncp_supplier_contracts',
    source_id           TEXT,
    source_updated_at   TIMESTAMPTZ,
    source_watermark    TEXT NOT NULL DEFAULT '',
    detected_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    priority            INTEGER NOT NULL DEFAULT 50
        CHECK (priority >= 0 AND priority <= 100),
    status              TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN (
            'pending', 'processing', 'done', 'retry',
            'dead', 'skipped_same_fingerprint', 'refresh_failed'
        )),
    attempt_count       INTEGER NOT NULL DEFAULT 0,
    next_retry_at       TIMESTAMPTZ,
    last_error          TEXT,
    locked_by           TEXT,
    locked_until        TIMESTAMPTZ,
    input_fingerprint   TEXT,
    idempotency_key     TEXT NOT NULL,
    processed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (idempotency_key)
);

CREATE INDEX IF NOT EXISTS confenge_tf_dirty_claim_idx
    ON public.confenge_target_fit_dirty (status, priority DESC, detected_at ASC)
    WHERE status IN ('pending', 'retry');

CREATE INDEX IF NOT EXISTS confenge_tf_dirty_company_idx
    ON public.confenge_target_fit_dirty (company_key, status);

CREATE INDEX IF NOT EXISTS confenge_tf_dirty_lock_idx
    ON public.confenge_target_fit_dirty (locked_until)
    WHERE status = 'processing';

COMMENT ON TABLE public.confenge_target_fit_dirty IS
'CONFENGE target-fit dirty queue. Logical CDC at CNPJ-root granularity. Async consumer of datalake changes.';

-- ---------------------------------------------------------------------------
-- Canonical current materialization (one row per company_key)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.confenge_company_target_fit_current (
    company_key             TEXT PRIMARY KEY,
    cnpj_raiz               CHAR(8) NOT NULL,
    target_fit_class        TEXT NOT NULL
        CHECK (target_fit_class IN (
            'TARGET_CONFIRMED',
            'TARGET_PROBABLE_RESEARCH',
            'TARGET_OUT_OF_SCOPE',
            'REFRESH_FAILED',
            'RECOMPUTE_REQUIRED'
        )),
    target_fit_confidence   DOUBLE PRECISION NOT NULL DEFAULT 0
        CHECK (target_fit_confidence >= 0 AND target_fit_confidence <= 1),
    target_fit_version      TEXT NOT NULL,
    target_fit_reason_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    target_fit_evidence     JSONB NOT NULL DEFAULT '[]'::jsonb,
    computed_at             TIMESTAMPTZ NOT NULL,
    source_watermark        TEXT NOT NULL DEFAULT '',
    source_max_updated_at   TIMESTAMPTZ,
    input_fingerprint       TEXT NOT NULL,
    classifier_sha          TEXT NOT NULL DEFAULT '',
    schema_version          TEXT NOT NULL DEFAULT 'confenge-tf-store-v1',
    operational_status      TEXT NOT NULL DEFAULT 'ok'
        CHECK (operational_status IN (
            'ok', 'stale', 'refresh_failed', 'recompute_required', 'shadow_only'
        )),
    sector_fit              TEXT NOT NULL DEFAULT '',
    activity_class          TEXT NOT NULL DEFAULT '',
    relevant_execution_contract_count INTEGER NOT NULL DEFAULT 0,
    relevant_supply_only_count INTEGER NOT NULL DEFAULT 0,
    materialization_mode    TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (materialization_mode IN ('SHADOW', 'ACTIVE', 'CANARY')),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS confenge_tf_current_class_idx
    ON public.confenge_company_target_fit_current (target_fit_class);

CREATE INDEX IF NOT EXISTS confenge_tf_current_version_idx
    ON public.confenge_company_target_fit_current (target_fit_version);

CREATE INDEX IF NOT EXISTS confenge_tf_current_wm_idx
    ON public.confenge_company_target_fit_current (source_watermark);

CREATE INDEX IF NOT EXISTS confenge_tf_current_raiz_idx
    ON public.confenge_company_target_fit_current (cnpj_raiz);

COMMENT ON TABLE public.confenge_company_target_fit_current IS
'Canonical live target-fit per CNPJ root. Derived state of the datalake; not a forgotten spreadsheet.';

-- ---------------------------------------------------------------------------
-- Append-only history (never overwrite the past)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.confenge_company_target_fit_history (
    id                      BIGSERIAL PRIMARY KEY,
    company_key             TEXT NOT NULL,
    cnpj_raiz               CHAR(8) NOT NULL,
    target_fit_class        TEXT NOT NULL,
    target_fit_confidence   DOUBLE PRECISION NOT NULL DEFAULT 0,
    target_fit_version      TEXT NOT NULL,
    target_fit_reason_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    target_fit_evidence     JSONB NOT NULL DEFAULT '[]'::jsonb,
    computed_at             TIMESTAMPTZ NOT NULL,
    source_watermark        TEXT NOT NULL DEFAULT '',
    source_max_updated_at   TIMESTAMPTZ,
    input_fingerprint       TEXT NOT NULL,
    classifier_sha          TEXT NOT NULL DEFAULT '',
    schema_version          TEXT NOT NULL DEFAULT 'confenge-tf-store-v1',
    previous_class          TEXT,
    previous_confidence     DOUBLE PRECISION,
    transition_event        TEXT,
    materialization_mode    TEXT NOT NULL DEFAULT 'ACTIVE',
    recorded_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS confenge_tf_history_company_idx
    ON public.confenge_company_target_fit_history (company_key, computed_at DESC);

CREATE INDEX IF NOT EXISTS confenge_tf_history_transition_idx
    ON public.confenge_company_target_fit_history (transition_event, recorded_at DESC)
    WHERE transition_event IS NOT NULL;

COMMENT ON TABLE public.confenge_company_target_fit_history IS
'Append-only target-fit history. Explains yesterday PROBABLE / today CONFIRMED (and reverse).';

-- ---------------------------------------------------------------------------
-- Durable state-transition events (no external broker)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.confenge_target_fit_events (
    id                      BIGSERIAL PRIMARY KEY,
    event_type              TEXT NOT NULL,
    company_key             TEXT NOT NULL,
    cnpj_raiz               CHAR(8) NOT NULL,
    old_class               TEXT,
    new_class               TEXT,
    old_confidence          DOUBLE PRECISION,
    new_confidence          DOUBLE PRECISION,
    reason_codes            JSONB NOT NULL DEFAULT '[]'::jsonb,
    changed_evidence_ids    JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_watermark        TEXT NOT NULL DEFAULT '',
    computed_at             TIMESTAMPTZ NOT NULL,
    target_fit_version      TEXT NOT NULL,
    payload                 JSONB NOT NULL DEFAULT '{}'::jsonb,
    consumed_at             TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS confenge_tf_events_type_idx
    ON public.confenge_target_fit_events (event_type, created_at DESC);

CREATE INDEX IF NOT EXISTS confenge_tf_events_company_idx
    ON public.confenge_target_fit_events (company_key, created_at DESC);

CREATE INDEX IF NOT EXISTS confenge_tf_events_unconsumed_idx
    ON public.confenge_target_fit_events (created_at)
    WHERE consumed_at IS NULL;

COMMENT ON TABLE public.confenge_target_fit_events IS
'Durable internal events for target-fit transitions (upgrade/downgrade/evidence/version).';

-- ---------------------------------------------------------------------------
-- Shadow comparison results (SHADOW mode only writes here for eligibility)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.confenge_target_fit_shadow (
    company_key             TEXT PRIMARY KEY,
    cnpj_raiz               CHAR(8) NOT NULL,
    shadow_class            TEXT NOT NULL,
    shadow_confidence       DOUBLE PRECISION NOT NULL DEFAULT 0,
    current_class           TEXT,
    current_confidence      DOUBLE PRECISION,
    target_fit_version      TEXT NOT NULL,
    input_fingerprint       TEXT NOT NULL,
    evidence                JSONB NOT NULL DEFAULT '[]'::jsonb,
    reason_codes            JSONB NOT NULL DEFAULT '[]'::jsonb,
    transition              TEXT,
    expected_match          BOOLEAN,
    source_watermark        TEXT NOT NULL DEFAULT '',
    computed_at             TIMESTAMPTZ NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.confenge_target_fit_shadow IS
'SHADOW mode materialization. Never mutates EMAIL_SEND_READY / activation eligibility.';

-- ---------------------------------------------------------------------------
-- Downstream invalidation ledger (downgrade → suppress send eligibility)
-- Does NOT delete outreach history / Decision Memory.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.confenge_target_fit_downstream_invalidation (
    id                      BIGSERIAL PRIMARY KEY,
    company_key             TEXT NOT NULL,
    cnpj_raiz               CHAR(8) NOT NULL,
    event_id                BIGINT REFERENCES public.confenge_target_fit_events(id),
    invalidation_type       TEXT NOT NULL DEFAULT 'TARGET_FIT_DOWNGRADE',
    old_class               TEXT,
    new_class               TEXT,
    email_send_ready_revoked BOOLEAN NOT NULL DEFAULT TRUE,
    activation_suppressed   BOOLEAN NOT NULL DEFAULT TRUE,
    notes                   TEXT,
    applied_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (company_key, event_id)
);

CREATE INDEX IF NOT EXISTS confenge_tf_invalidation_company_idx
    ON public.confenge_target_fit_downstream_invalidation (company_key, applied_at DESC);

-- ---------------------------------------------------------------------------
-- Worker / CDC control plane (watermarks, cycle meta, anomaly auto-pause)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.confenge_target_fit_control (
    key                     TEXT PRIMARY KEY,
    value                   JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.confenge_target_fit_control IS
'Control plane: cdc_watermark, last_success, async_mode, auto_pause, metrics snapshot.';

CREATE TABLE IF NOT EXISTS public.confenge_target_fit_cycle_meta (
    cycle_id                TEXT PRIMARY KEY,
    cycle_kind              TEXT NOT NULL
        CHECK (cycle_kind IN ('refresh', 'worker', 'reconcile', 'shadow', 'backfill')),
    started_at              TIMESTAMPTZ NOT NULL,
    finished_at             TIMESTAMPTZ,
    source_watermark        TEXT NOT NULL DEFAULT '',
    target_fit_version      TEXT NOT NULL,
    mode                    TEXT NOT NULL DEFAULT 'SHADOW',
    stats                   JSONB NOT NULL DEFAULT '{}'::jsonb,
    status                  TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'success', 'failed', 'auto_paused')),
    error_message           TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS confenge_tf_cycle_kind_idx
    ON public.confenge_target_fit_cycle_meta (cycle_kind, started_at DESC);

-- ---------------------------------------------------------------------------
-- CDC watermark helper: last observed max(ingested_at) on contracts
-- ---------------------------------------------------------------------------
INSERT INTO public.confenge_target_fit_control (key, value)
VALUES
    ('async_mode', '{"mode": "SHADOW"}'::jsonb),
    ('cdc_watermark', '{"watermark": "", "observed_at": null}'::jsonb),
    ('auto_pause', '{"paused": false, "reason": null}'::jsonb)
ON CONFLICT (key) DO NOTHING;

COMMIT;
