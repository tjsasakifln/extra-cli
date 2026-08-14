-- ============================================================================
-- Migration 092: Decision-Unit Intelligence + Reachability (additive)
-- After 091 (PR #371 contract durability). Does not edit 079/081/087/088/089/091.
-- Reuses canonical entities/processes/documents. This is not a generic KG.
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS public.decision_unit_runs (
    run_id              TEXT PRIMARY KEY,
    snapshot_hash       TEXT,
    policy_version      TEXT NOT NULL,
    provider_version    TEXT NOT NULL,
    objective           TEXT NOT NULL DEFAULT 'decision_unit_reachability',
    cohort_seed         TEXT,
    status              TEXT NOT NULL DEFAULT 'running',
    n_accounts          INTEGER NOT NULL DEFAULT 0,
    funnel_json         JSONB NOT NULL DEFAULT '{}'::jsonb,
    cost_brl            NUMERIC(12,4) NOT NULL DEFAULT 0,
    duration_ms         INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    extra               JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS public.decision_unit_candidates (
    candidate_id        TEXT PRIMARY KEY,
    run_id              TEXT REFERENCES public.decision_unit_runs(run_id),
    company_entity_id   TEXT NOT NULL,
    person_id           TEXT NOT NULL,
    person_name         TEXT,
    observed_roles      TEXT[] NOT NULL DEFAULT '{}',
    decision_role_class TEXT NOT NULL,
    decision_relevance  TEXT NOT NULL,
    authority_signal    TEXT NOT NULL,
    operational_relevance TEXT NOT NULL,
    service_context     TEXT NOT NULL,
    identity_confidence TEXT NOT NULL,
    role_confidence     TEXT NOT NULL,
    suitability         TEXT NOT NULL,
    reason_codes        TEXT[] NOT NULL DEFAULT '{}',
    evidence_ids        TEXT[] NOT NULL DEFAULT '{}',
    inferred_decision_relevance TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dui_candidates_company
    ON public.decision_unit_candidates (company_entity_id);

CREATE TABLE IF NOT EXISTS public.reachability_routes (
    route_id            TEXT PRIMARY KEY,
    run_id              TEXT REFERENCES public.decision_unit_runs(run_id),
    company_entity_id   TEXT NOT NULL,
    decision_unit_candidate_id TEXT,
    target_role         TEXT,
    channel_type        TEXT NOT NULL,
    channel_value       TEXT,
    route_relation      TEXT NOT NULL,
    epistemic_class     TEXT NOT NULL,
    reachability_class  TEXT NOT NULL,
    action_mode         TEXT NOT NULL,
    route_confidence    TEXT NOT NULL,
    ownership           TEXT NOT NULL,
    suppression         TEXT NOT NULL,
    reason_codes        TEXT[] NOT NULL DEFAULT '{}',
    next_action         TEXT,
    source_url          TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT reachability_routes_no_auto_send CHECK (action_mode <> 'AUTO_SEND'),
    CONSTRAINT reachability_routes_inferred_not_observed CHECK (
        NOT (channel_type = 'INFERRED_DIRECT_EMAIL' AND epistemic_class = 'OBSERVED')
    )
);

CREATE INDEX IF NOT EXISTS idx_dui_routes_company
    ON public.reachability_routes (company_entity_id);

CREATE TABLE IF NOT EXISTS public.decision_unit_field_evidence (
    evidence_id         TEXT PRIMARY KEY,
    run_id              TEXT REFERENCES public.decision_unit_runs(run_id),
    field               TEXT NOT NULL,
    value               TEXT,
    epistemic_class     TEXT NOT NULL,
    source_type         TEXT NOT NULL,
    source_url          TEXT,
    document_id         TEXT,
    document_sha256     TEXT,
    page                INTEGER,
    evidence_snippet    TEXT,
    observed_at         TIMESTAMPTZ,
    extraction_method   TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT dui_observed_needs_source CHECK (
        epistemic_class <> 'OBSERVED'
        OR source_url IS NOT NULL
        OR document_id IS NOT NULL
        OR source_type IN ('qsa_rfb', 'rfb_cadastre', 'process_document', 'company_site', 'public_page')
    )
);

CREATE TABLE IF NOT EXISTS public.decision_unit_search_attempts (
    attempt_id          TEXT PRIMARY KEY,
    run_id              TEXT REFERENCES public.decision_unit_runs(run_id),
    company_entity_id   TEXT NOT NULL,
    tier                INTEGER NOT NULL,
    provider_id         TEXT NOT NULL,
    source              TEXT NOT NULL,
    status              TEXT NOT NULL,
    reason              TEXT,
    documents_checked   INTEGER NOT NULL DEFAULT 0,
    duration_ms         INTEGER NOT NULL DEFAULT 0,
    cost_brl            NUMERIC(12,4) NOT NULL DEFAULT 0,
    blocked             BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.decision_unit_candidate_evidence (
    candidate_id        TEXT NOT NULL REFERENCES public.decision_unit_candidates(candidate_id),
    evidence_id         TEXT NOT NULL REFERENCES public.decision_unit_field_evidence(evidence_id),
    PRIMARY KEY (candidate_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS public.decision_unit_route_evidence (
    route_id            TEXT NOT NULL REFERENCES public.reachability_routes(route_id),
    evidence_id         TEXT NOT NULL REFERENCES public.decision_unit_field_evidence(evidence_id),
    PRIMARY KEY (route_id, evidence_id)
);

COMMIT;
