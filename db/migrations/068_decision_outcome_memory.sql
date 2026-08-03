-- 068_decision_outcome_memory.sql
-- Campaign: EXTRA-DECISION-OUTCOME-MEMORY-01
-- Canonical Decision & Outcome Memory v1 (append-only events, client-scoped).
-- Additive only. Idempotent: CREATE IF NOT EXISTS / DROP IF EXISTS patterns.
-- Does not alter predictive tables or commercial_leads paths.

BEGIN;

-- ---------------------------------------------------------------------------
-- Vocabulary helpers (CHECK constraints keep enums closed at the DB layer)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.dm_decision_events (
    event_id            UUID PRIMARY KEY,
    client_id           TEXT NOT NULL,
    opportunity_key     TEXT NOT NULL,
    source_identifiers  JSONB NOT NULL DEFAULT '{}'::jsonb,
    cycle_id            TEXT,
    run_id              TEXT,
    decided_at          TIMESTAMPTZ NOT NULL,
    session_deadline_at TIMESTAMPTZ,
    system_recommendation TEXT
                            CHECK (system_recommendation IS NULL OR system_recommendation IN (
                                'GO', 'REVIEW', 'NO_GO', 'UNKNOWN', 'NOT_PROVIDED'
                            )),
    human_decision      TEXT NOT NULL
                            CHECK (human_decision IN ('GO', 'REVIEW', 'NO_GO')),
    legacy_decision     TEXT
                            CHECK (legacy_decision IS NULL OR legacy_decision IN (
                                'ACCEPT', 'REJECT', 'DEFER', 'UNKNOWN', 'NOT_PROVIDED'
                            )),
    actor               TEXT NOT NULL,
    justification       TEXT NOT NULL,
    premises            JSONB NOT NULL DEFAULT '[]'::jsonb,
    constraints_known   JSONB NOT NULL DEFAULT '[]'::jsonb,
    data_limitations    JSONB NOT NULL DEFAULT '[]'::jsonb,
    profile_id          TEXT,
    profile_version     TEXT,
    profile_hash        TEXT,
    evidence_hash       TEXT,
    evidence_locators   JSONB NOT NULL DEFAULT '[]'::jsonb,
    schema_version      TEXT NOT NULL DEFAULT 'decision-memory/1.0',
    engine_version      TEXT,
    prediction_ref      JSONB,
    temporal_integrity  TEXT NOT NULL DEFAULT 'PROSPECTIVE'
                            CHECK (temporal_integrity IN (
                                'PROSPECTIVE',
                                'HISTORICAL_UNVERIFIED',
                                'OUTCOME_WITHOUT_PRIOR_DECISION',
                                'TEMPORAL_ORDER_UNKNOWN'
                            )),
    origin              TEXT NOT NULL DEFAULT 'cli'
                            CHECK (origin IN (
                                'cli', 'review', 'import', 'api', 'system', 'supersession'
                            )),
    idempotency_key     TEXT NOT NULL,
    supersedes_event_id UUID REFERENCES public.dm_decision_events(event_id),
    correction_reason   TEXT,
    correction_type     TEXT
                            CHECK (correction_type IS NULL OR correction_type IN (
                                'CORRECTION', 'SUPERSESSION', 'CLARIFICATION', 'VOID'
                            )),
    payload             JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_dm_decision_idempotency UNIQUE (client_id, idempotency_key),
    CONSTRAINT ck_dm_decision_actor_nonempty CHECK (length(trim(actor)) > 0),
    CONSTRAINT ck_dm_decision_justification_nonempty CHECK (length(trim(justification)) > 0),
    CONSTRAINT ck_dm_decision_client_nonempty CHECK (length(trim(client_id)) > 0),
    CONSTRAINT ck_dm_decision_opp_nonempty CHECK (length(trim(opportunity_key)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_dm_decision_client_opp
    ON public.dm_decision_events (client_id, opportunity_key, decided_at DESC);
CREATE INDEX IF NOT EXISTS idx_dm_decision_client_cycle
    ON public.dm_decision_events (client_id, cycle_id) WHERE cycle_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_dm_decision_client_created
    ON public.dm_decision_events (client_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_dm_decision_supersedes
    ON public.dm_decision_events (supersedes_event_id) WHERE supersedes_event_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.dm_action_events (
    event_id            UUID PRIMARY KEY,
    client_id           TEXT NOT NULL,
    decision_event_id   UUID NOT NULL REFERENCES public.dm_decision_events(event_id),
    opportunity_key     TEXT NOT NULL,
    description         TEXT NOT NULL,
    owner               TEXT,
    owner_absent_reason TEXT,
    due_at              TIMESTAMPTZ,
    due_absent_reason   TEXT,
    criticality         TEXT NOT NULL DEFAULT 'NORMAL'
                            CHECK (criticality IN ('CRITICAL', 'HIGH', 'NORMAL', 'LOW')),
    status              TEXT NOT NULL DEFAULT 'OPEN'
                            CHECK (status IN (
                                'OPEN', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED', 'SUPERSEDED', 'OVERDUE'
                            )),
    completion_evidence_hash TEXT,
    completion_evidence_locators JSONB NOT NULL DEFAULT '[]'::jsonb,
    completed_at        TIMESTAMPTZ,
    cancel_reason       TEXT,
    supersedes_event_id UUID REFERENCES public.dm_action_events(event_id),
    actor               TEXT NOT NULL,
    temporal_integrity  TEXT NOT NULL DEFAULT 'PROSPECTIVE'
                            CHECK (temporal_integrity IN (
                                'PROSPECTIVE',
                                'HISTORICAL_UNVERIFIED',
                                'OUTCOME_WITHOUT_PRIOR_DECISION',
                                'TEMPORAL_ORDER_UNKNOWN'
                            )),
    origin              TEXT NOT NULL DEFAULT 'cli'
                            CHECK (origin IN (
                                'cli', 'review', 'import', 'api', 'system', 'supersession'
                            )),
    idempotency_key     TEXT NOT NULL,
    schema_version      TEXT NOT NULL DEFAULT 'decision-memory/1.0',
    payload             JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_dm_action_idempotency UNIQUE (client_id, idempotency_key),
    CONSTRAINT ck_dm_action_actor_nonempty CHECK (length(trim(actor)) > 0),
    CONSTRAINT ck_dm_action_desc_nonempty CHECK (length(trim(description)) > 0),
    CONSTRAINT ck_dm_action_client_nonempty CHECK (length(trim(client_id)) > 0),
    CONSTRAINT ck_dm_action_owner_policy CHECK (
        (owner IS NOT NULL AND length(trim(owner)) > 0)
        OR (owner IS NULL AND owner_absent_reason IS NOT NULL AND length(trim(owner_absent_reason)) > 0)
    ),
    CONSTRAINT ck_dm_action_due_policy CHECK (
        due_at IS NOT NULL
        OR (due_absent_reason IS NOT NULL AND length(trim(due_absent_reason)) > 0)
    )
);

CREATE INDEX IF NOT EXISTS idx_dm_action_client_decision
    ON public.dm_action_events (client_id, decision_event_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_dm_action_client_status
    ON public.dm_action_events (client_id, status, due_at);
CREATE INDEX IF NOT EXISTS idx_dm_action_client_opp
    ON public.dm_action_events (client_id, opportunity_key);

CREATE TABLE IF NOT EXISTS public.dm_outcome_events (
    event_id            UUID PRIMARY KEY,
    client_id           TEXT NOT NULL,
    opportunity_key     TEXT NOT NULL,
    decision_event_id   UUID REFERENCES public.dm_decision_events(event_id),
    outcome_type        TEXT NOT NULL
                            CHECK (outcome_type IN (
                                'UNKNOWN',
                                'NO_PARTICIPATION',
                                'PROPOSAL_SUBMITTED',
                                'INELIGIBLE',
                                'DISQUALIFIED',
                                'LOSS',
                                'WIN',
                                'SUSPENDED',
                                'REVOKED',
                                'ANNULLED',
                                'HOMOLOGATED',
                                'AWARDED',
                                'CONTRACTED',
                                'EXECUTION_STARTED',
                                'INCIDENT',
                                'ADDENDUM',
                                'CONTRACT_CLOSED',
                                'MARGIN_DECLARED'
                            )),
    observed_at         TIMESTAMPTZ NOT NULL,
    effective_at        TIMESTAMPTZ,
    source              TEXT NOT NULL,
    locator             TEXT,
    evidence_hash       TEXT NOT NULL,
    confirmation_degree TEXT NOT NULL DEFAULT 'DECLARED'
                            CHECK (confirmation_degree IN (
                                'DECLARED', 'DOCUMENTED', 'OFFICIAL', 'UNVERIFIED'
                            )),
    actor               TEXT NOT NULL,
    structured_facts    JSONB NOT NULL DEFAULT '{}'::jsonb,
    observations        TEXT,
    limitations         JSONB NOT NULL DEFAULT '[]'::jsonb,
    expected_margin     NUMERIC(18, 4),
    realized_margin     NUMERIC(18, 4),
    temporal_integrity  TEXT NOT NULL DEFAULT 'PROSPECTIVE'
                            CHECK (temporal_integrity IN (
                                'PROSPECTIVE',
                                'HISTORICAL_UNVERIFIED',
                                'OUTCOME_WITHOUT_PRIOR_DECISION',
                                'TEMPORAL_ORDER_UNKNOWN'
                            )),
    origin              TEXT NOT NULL DEFAULT 'cli'
                            CHECK (origin IN (
                                'cli', 'review', 'import', 'api', 'system', 'supersession'
                            )),
    idempotency_key     TEXT NOT NULL,
    supersedes_event_id UUID REFERENCES public.dm_outcome_events(event_id),
    correction_reason   TEXT,
    correction_type     TEXT
                            CHECK (correction_type IS NULL OR correction_type IN (
                                'CORRECTION', 'SUPERSESSION', 'CLARIFICATION', 'VOID'
                            )),
    schema_version      TEXT NOT NULL DEFAULT 'decision-memory/1.0',
    payload             JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_dm_outcome_idempotency UNIQUE (client_id, idempotency_key),
    CONSTRAINT ck_dm_outcome_actor_nonempty CHECK (length(trim(actor)) > 0),
    CONSTRAINT ck_dm_outcome_source_nonempty CHECK (length(trim(source)) > 0),
    CONSTRAINT ck_dm_outcome_evidence_nonempty CHECK (length(trim(evidence_hash)) > 0),
    CONSTRAINT ck_dm_outcome_client_nonempty CHECK (length(trim(client_id)) > 0),
    CONSTRAINT ck_dm_outcome_opp_nonempty CHECK (length(trim(opportunity_key)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_dm_outcome_client_opp
    ON public.dm_outcome_events (client_id, opportunity_key, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_dm_outcome_client_decision
    ON public.dm_outcome_events (client_id, decision_event_id)
    WHERE decision_event_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_dm_outcome_client_type
    ON public.dm_outcome_events (client_id, outcome_type, observed_at DESC);

CREATE TABLE IF NOT EXISTS public.dm_identity_conflicts (
    conflict_id         UUID PRIMARY KEY,
    client_id           TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'BLOCKED'
                            CHECK (status IN ('BLOCKED', 'RESOLVED', 'DISMISSED')),
    candidate_keys      JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_identifiers  JSONB NOT NULL DEFAULT '{}'::jsonb,
    reason              TEXT NOT NULL,
    actor               TEXT,
    resolution_key      TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at         TIMESTAMPTZ,
    payload             JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_dm_identity_conflicts_client
    ON public.dm_identity_conflicts (client_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS public.dm_import_runs (
    import_id           UUID PRIMARY KEY,
    client_id           TEXT NOT NULL,
    mode                TEXT NOT NULL CHECK (mode IN ('dry_run', 'apply')),
    manifest            JSONB NOT NULL DEFAULT '{}'::jsonb,
    counts              JSONB NOT NULL DEFAULT '{}'::jsonb,
    actor               TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dm_import_runs_client
    ON public.dm_import_runs (client_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- Current-state projections (latest non-superseded event per natural key)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW public.dm_decision_current AS
SELECT d.*
FROM public.dm_decision_events d
WHERE NOT EXISTS (
    SELECT 1
    FROM public.dm_decision_events s
    WHERE s.client_id = d.client_id
      AND s.supersedes_event_id = d.event_id
)
AND (d.correction_type IS NULL OR d.correction_type <> 'VOID');

CREATE OR REPLACE VIEW public.dm_action_current AS
SELECT a.*
FROM public.dm_action_events a
WHERE NOT EXISTS (
    SELECT 1
    FROM public.dm_action_events s
    WHERE s.client_id = a.client_id
      AND s.supersedes_event_id = a.event_id
)
AND a.status <> 'SUPERSEDED';

CREATE OR REPLACE VIEW public.dm_outcome_current AS
SELECT o.*
FROM public.dm_outcome_events o
WHERE NOT EXISTS (
    SELECT 1
    FROM public.dm_outcome_events s
    WHERE s.client_id = o.client_id
      AND s.supersedes_event_id = o.event_id
)
AND (o.correction_type IS NULL OR o.correction_type <> 'VOID');

-- Cross-client safety: actions must reference a decision of the same client.
-- Enforced via trigger (FK alone cannot express client_id match).
CREATE OR REPLACE FUNCTION public.dm_enforce_action_client_match()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    dec_client TEXT;
BEGIN
    SELECT client_id INTO dec_client
    FROM public.dm_decision_events
    WHERE event_id = NEW.decision_event_id;
    IF dec_client IS NULL THEN
        RAISE EXCEPTION 'decision_event_id % not found', NEW.decision_event_id;
    END IF;
    IF dec_client <> NEW.client_id THEN
        RAISE EXCEPTION 'cross-client action blocked: action client=% decision client=%',
            NEW.client_id, dec_client;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_dm_action_client_match ON public.dm_action_events;
CREATE TRIGGER trg_dm_action_client_match
    BEFORE INSERT ON public.dm_action_events
    FOR EACH ROW
    EXECUTE FUNCTION public.dm_enforce_action_client_match();

CREATE OR REPLACE FUNCTION public.dm_enforce_outcome_client_match()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    dec_client TEXT;
BEGIN
    IF NEW.decision_event_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT client_id INTO dec_client
    FROM public.dm_decision_events
    WHERE event_id = NEW.decision_event_id;
    IF dec_client IS NULL THEN
        RAISE EXCEPTION 'decision_event_id % not found', NEW.decision_event_id;
    END IF;
    IF dec_client <> NEW.client_id THEN
        RAISE EXCEPTION 'cross-client outcome blocked: outcome client=% decision client=%',
            NEW.client_id, dec_client;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_dm_outcome_client_match ON public.dm_outcome_events;
CREATE TRIGGER trg_dm_outcome_client_match
    BEFORE INSERT ON public.dm_outcome_events
    FOR EACH ROW
    EXECUTE FUNCTION public.dm_enforce_outcome_client_match();

-- Append-only: block UPDATE/DELETE on event tables
CREATE OR REPLACE FUNCTION public.dm_forbid_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'dm_* event tables are append-only; use supersession events';
END;
$$;

DROP TRIGGER IF EXISTS trg_dm_decision_no_update ON public.dm_decision_events;
CREATE TRIGGER trg_dm_decision_no_update
    BEFORE UPDATE OR DELETE ON public.dm_decision_events
    FOR EACH ROW
    EXECUTE FUNCTION public.dm_forbid_mutation();

DROP TRIGGER IF EXISTS trg_dm_action_no_update ON public.dm_action_events;
CREATE TRIGGER trg_dm_action_no_update
    BEFORE UPDATE OR DELETE ON public.dm_action_events
    FOR EACH ROW
    EXECUTE FUNCTION public.dm_forbid_mutation();

DROP TRIGGER IF EXISTS trg_dm_outcome_no_update ON public.dm_outcome_events;
CREATE TRIGGER trg_dm_outcome_no_update
    BEFORE UPDATE OR DELETE ON public.dm_outcome_events
    FOR EACH ROW
    EXECUTE FUNCTION public.dm_forbid_mutation();

COMMIT;
