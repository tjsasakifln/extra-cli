-- 062_commercial_leads_ledger.sql
-- Campaign: CONFENGE-COMMERCIAL-READY-01
-- Commercial lead queue state, overrides and feedback ledger.
-- Additive only. Does not alter pncp_supplier_contracts write path.
-- Idempotent: CREATE IF NOT EXISTS / DROP IF EXISTS index patterns.

BEGIN;

CREATE TABLE IF NOT EXISTS public.commercial_lead_runs (
    run_id              TEXT PRIMARY KEY,
    as_of               TIMESTAMPTZ NOT NULL DEFAULT now(),
    profile_id          TEXT NOT NULL,
    profile_version     TEXT NOT NULL,
    profile_hash        TEXT NOT NULL,
    snapshot_hash       TEXT NOT NULL,
    snapshot_manifest   JSONB NOT NULL DEFAULT '{}'::jsonb,
    git_sha             TEXT,
    status              TEXT NOT NULL DEFAULT 'RUNNING'
                            CHECK (status IN ('RUNNING', 'PASS', 'BLOCKED', 'FAIL')),
    queue_limit         INTEGER NOT NULL DEFAULT 20,
    eligible_companies  INTEGER NOT NULL DEFAULT 0,
    ranked_companies    INTEGER NOT NULL DEFAULT 0,
    metrics             JSONB NOT NULL DEFAULT '{}'::jsonb,
    non_claims          JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at         TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS public.commercial_leads (
    id                  BIGSERIAL PRIMARY KEY,
    run_id              TEXT NOT NULL REFERENCES public.commercial_lead_runs(run_id) ON DELETE CASCADE,
    cnpj14              TEXT NOT NULL,
    cnpj8               TEXT,
    razao_social        TEXT NOT NULL,
    score_total         NUMERIC(12, 4) NOT NULL DEFAULT 0,
    priority            TEXT NOT NULL DEFAULT 'MEDIUM'
                            CHECK (priority IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'WATCH')),
    score_decomposition JSONB NOT NULL DEFAULT '{}'::jsonb,
    signals_fired       JSONB NOT NULL DEFAULT '[]'::jsonb,
    signals_not_computable JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence            JSONB NOT NULL DEFAULT '[]'::jsonb,
    suggested_offer     TEXT,
    next_human_step     TEXT,
    limitations         JSONB NOT NULL DEFAULT '[]'::jsonb,
    commercial_state    TEXT NOT NULL DEFAULT 'NEW'
                            CHECK (commercial_state IN (
                                'NEW', 'REVIEWED', 'QUALIFIED', 'DISQUALIFIED',
                                'CONTACTED', 'REPLIED', 'MEETING', 'PROPOSAL',
                                'WON', 'LOST', 'DO_NOT_CONTACT'
                            )),
    rank_position       INTEGER,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_commercial_leads_run_cnpj UNIQUE (run_id, cnpj14)
);

CREATE INDEX IF NOT EXISTS idx_commercial_leads_run_score
    ON public.commercial_leads (run_id, score_total DESC);
CREATE INDEX IF NOT EXISTS idx_commercial_leads_cnpj14
    ON public.commercial_leads (cnpj14);

CREATE TABLE IF NOT EXISTS public.commercial_lead_state_overrides (
    id                  BIGSERIAL PRIMARY KEY,
    cnpj14              TEXT NOT NULL,
    author              TEXT NOT NULL,
    previous_state      TEXT NOT NULL,
    new_state           TEXT NOT NULL
                            CHECK (new_state IN (
                                'NEW', 'REVIEWED', 'QUALIFIED', 'DISQUALIFIED',
                                'CONTACTED', 'REPLIED', 'MEETING', 'PROPOSAL',
                                'WON', 'LOST', 'DO_NOT_CONTACT'
                            )),
    reason              TEXT NOT NULL,
    run_id              TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_commercial_overrides_cnpj
    ON public.commercial_lead_state_overrides (cnpj14, created_at DESC);

CREATE TABLE IF NOT EXISTS public.commercial_feedback_ledger (
    id                  BIGSERIAL PRIMARY KEY,
    run_id              TEXT,
    cnpj14              TEXT NOT NULL,
    event_type          TEXT NOT NULL
                            CHECK (event_type IN (
                                'STATE_CHANGE', 'REVIEW', 'CONTACT', 'OUTCOME',
                                'SUPPRESSION', 'NOTE', 'EXPORT'
                            )),
    payload             JSONB NOT NULL DEFAULT '{}'::jsonb,
    author              TEXT NOT NULL DEFAULT 'system',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_commercial_feedback_cnpj
    ON public.commercial_feedback_ledger (cnpj14, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_commercial_feedback_run
    ON public.commercial_feedback_ledger (run_id) WHERE run_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.commercial_exclusions (
    id                  BIGSERIAL PRIMARY KEY,
    run_id              TEXT NOT NULL REFERENCES public.commercial_lead_runs(run_id) ON DELETE CASCADE,
    raw_tax_id          TEXT,
    raw_name            TEXT,
    reason_code         TEXT NOT NULL,
    detail              TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_commercial_exclusions_run
    ON public.commercial_exclusions (run_id, reason_code);

COMMENT ON TABLE public.commercial_lead_runs IS
'CONFENGE commercial queue runs. Signals are need/fit hypotheses, not purchase propensity.';
COMMENT ON TABLE public.commercial_leads IS
'Ranked commercial leads per run. Score is prioritization for human review only.';
COMMENT ON TABLE public.commercial_feedback_ledger IS
'Append-only commercial feedback and state change ledger.';

COMMIT;
