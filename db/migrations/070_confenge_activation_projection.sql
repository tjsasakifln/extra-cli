-- 070_confenge_activation_projection.sql
-- Recomputable commercial activation projection (NOT Decision & Outcome Memory).
-- Extra-cli authority: who deserves commercial attention *now* and why.
-- Additive only. Fail-soft if applied twice.

BEGIN;

CREATE TABLE IF NOT EXISTS public.confenge_activation_projections (
    cnpj14                CHAR(14) PRIMARY KEY,
    activation_state      TEXT NOT NULL
        CHECK (activation_state IN (
            'WATCH', 'RESEARCH_REQUIRED', 'ACTIONABLE_NOW', 'SUPPRESSED'
        )),
    activation_score      DOUBLE PRECISION NOT NULL DEFAULT 0
        CHECK (activation_score >= 0 AND activation_score <= 100),
    reason_codes          JSONB NOT NULL DEFAULT '[]'::jsonb,
    evaluated_at          TIMESTAMPTZ NOT NULL,
    next_best_action_at   TIMESTAMPTZ,
    expires_at            TIMESTAMPTZ,
    source_hash           TEXT NOT NULL DEFAULT '',
    trigger_hash          TEXT NOT NULL DEFAULT '',
    last_hot_set_at       TIMESTAMPTZ,
    policy_version        TEXT NOT NULL DEFAULT 'confenge-activation-v1',
    score_components      JSONB NOT NULL DEFAULT '{}'::jsonb,
    commercial_state      TEXT NOT NULL DEFAULT 'NEW',
    -- Flattened portfolio counters for cheap delta triggers across cycles
    active_contract_count INTEGER NOT NULL DEFAULT 0,
    contract_count_recent INTEGER NOT NULL DEFAULT 0,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.confenge_activation_projections IS
'CONFENGE activation planner projection. Recomputable. Not CRM commercial_state. Not Decision Memory.';

CREATE INDEX IF NOT EXISTS confenge_activation_state_score_idx
    ON public.confenge_activation_projections (activation_state, activation_score DESC);

CREATE INDEX IF NOT EXISTS confenge_activation_nba_idx
    ON public.confenge_activation_projections (next_best_action_at)
    WHERE next_best_action_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS confenge_activation_policy_idx
    ON public.confenge_activation_projections (policy_version);

CREATE TABLE IF NOT EXISTS public.confenge_activation_cycle_meta (
    cycle_id           TEXT PRIMARY KEY,
    policy_version     TEXT NOT NULL,
    evaluated_at       TIMESTAMPTZ NOT NULL,
    as_of              DATE NOT NULL,
    reservoir_count    INTEGER NOT NULL DEFAULT 0,
    activation_counts  JSONB NOT NULL DEFAULT '{}'::jsonb,
    hot_set_count      INTEGER NOT NULL DEFAULT 0,
    source_watermark   TEXT NOT NULL DEFAULT '',
    trigger_counts     JSONB NOT NULL DEFAULT '{}'::jsonb,
    rows_changed       INTEGER NOT NULL DEFAULT 0,
    elapsed_seconds    DOUBLE PRECISION,
    peak_rss_mb        DOUBLE PRECISION,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.confenge_activation_cycle_meta IS
'Per-cycle activation planner observability (reservoir vs hot set).';

COMMIT;
