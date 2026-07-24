-- ============================================================================
-- Migration 061: Canonical entity linkage (organs, suppliers, opportunity links)
-- ============================================================================
-- Campaign: CANONICAL-ENTITY-LINKAGE-01
-- Purpose: golden records + auditable links opportunity↔organ↔contract↔supplier
-- without creating a parallel identity authority for coverage.
--
-- Design:
--   - Strong keys (CNPJ14/CNPJ8, IBGE) never auto-merged when conflicting
--   - Every link carries classification, score, reason codes, rule version, run_id
--   - Ambiguous and unresolved remain first-class (not dropped from denominators)
--   - Idempotent re-run via natural unique keys on (run_id, link natural key)
--
-- Depends on: 002 (contracts), 007 (sc_public_entities), 027 (opportunity_intel),
--             043 (entity_aliases), 053 (entity_source_registry)
-- Idempotent: Yes
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Golden organs / units
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.canonical_organs (
    id                  BIGSERIAL PRIMARY KEY,
    canonical_key       TEXT NOT NULL,                 -- stable: cnpj14 or cnpj8:norm_name
    entity_kind         TEXT NOT NULL DEFAULT 'organ'  -- organ | unit
                            CHECK (entity_kind IN ('organ', 'unit')),
    cnpj14              TEXT,                          -- 14 digits when known
    cnpj8               TEXT,                          -- root
    ibge_code           TEXT,
    raw_name            TEXT NOT NULL,
    normalized_name     TEXT NOT NULL,
    uf                  TEXT,
    municipio           TEXT,
    source              TEXT NOT NULL DEFAULT 'pncp',
    source_record_ids   JSONB NOT NULL DEFAULT '[]'::jsonb,
    decision_history    JSONB NOT NULL DEFAULT '[]'::jsonb,
    first_seen_run_id   TEXT,
    last_seen_run_id    TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_canonical_organs_key UNIQUE (canonical_key)
);

CREATE INDEX IF NOT EXISTS idx_canonical_organs_cnpj14
    ON public.canonical_organs (cnpj14) WHERE cnpj14 IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_canonical_organs_cnpj8
    ON public.canonical_organs (cnpj8) WHERE cnpj8 IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_canonical_organs_ibge
    ON public.canonical_organs (ibge_code) WHERE ibge_code IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_canonical_organs_norm
    ON public.canonical_organs (normalized_name);

-- ---------------------------------------------------------------------------
-- Golden suppliers
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.canonical_suppliers (
    id                  BIGSERIAL PRIMARY KEY,
    canonical_key       TEXT NOT NULL,                 -- cnpj14 preferred; else cpf; else blocked
    person_kind         TEXT NOT NULL DEFAULT 'cnpj'
                            CHECK (person_kind IN ('cnpj', 'cpf', 'unknown')),
    cnpj14              TEXT,
    cnpj8               TEXT,
    cpf11               TEXT,
    raw_name            TEXT NOT NULL,
    normalized_name     TEXT NOT NULL,
    source              TEXT NOT NULL DEFAULT 'pncp',
    source_record_ids   JSONB NOT NULL DEFAULT '[]'::jsonb,
    decision_history    JSONB NOT NULL DEFAULT '[]'::jsonb,
    first_seen_run_id   TEXT,
    last_seen_run_id    TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_canonical_suppliers_key UNIQUE (canonical_key)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_canonical_suppliers_cnpj14
    ON public.canonical_suppliers (cnpj14) WHERE cnpj14 IS NOT NULL AND length(cnpj14) = 14;
CREATE INDEX IF NOT EXISTS idx_canonical_suppliers_cnpj8
    ON public.canonical_suppliers (cnpj8) WHERE cnpj8 IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_canonical_suppliers_norm
    ON public.canonical_suppliers (normalized_name);

-- ---------------------------------------------------------------------------
-- Alias / provenance ledger (never destroys official keys)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.canonical_entity_aliases (
    id                  BIGSERIAL PRIMARY KEY,
    entity_type         TEXT NOT NULL CHECK (entity_type IN ('organ', 'unit', 'supplier')),
    canonical_key       TEXT NOT NULL,
    alias_kind          TEXT NOT NULL,  -- raw_name | cnpj14 | cnpj8 | ibge | source_id
    alias_value         TEXT NOT NULL,
    alias_normalized    TEXT,
    source              TEXT NOT NULL,
    source_record_id    TEXT,
    confidence          TEXT NOT NULL DEFAULT 'exact'
                            CHECK (confidence IN ('exact', 'deterministic', 'heuristic', 'manual')),
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    run_id              TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_canonical_entity_aliases
        UNIQUE (entity_type, canonical_key, alias_kind, alias_value, source)
);

CREATE INDEX IF NOT EXISTS idx_cea_lookup
    ON public.canonical_entity_aliases (entity_type, alias_kind, alias_value)
    WHERE is_active;

-- ---------------------------------------------------------------------------
-- Linkage runs (one identified execution)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.entity_linkage_runs (
    run_id              TEXT PRIMARY KEY,
    as_of               TIMESTAMPTZ NOT NULL,
    git_sha             TEXT,
    schema_version      TEXT,
    rule_version        TEXT NOT NULL DEFAULT 'linkage-v1',
    snapshot_id         TEXT,
    snapshot_hash       TEXT,
    status              TEXT NOT NULL DEFAULT 'running'
                            CHECK (status IN ('running', 'completed', 'failed')),
    metrics             JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at         TIMESTAMPTZ,
    production_touched  BOOLEAN NOT NULL DEFAULT FALSE
);

-- ---------------------------------------------------------------------------
-- Opportunity → organ links
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.opportunity_organ_links (
    id                  BIGSERIAL PRIMARY KEY,
    run_id              TEXT NOT NULL REFERENCES public.entity_linkage_runs(run_id) ON DELETE CASCADE,
    opportunity_id      BIGINT NOT NULL,
    organ_canonical_key TEXT,
    classification      TEXT NOT NULL
                            CHECK (classification IN (
                                'exact', 'deterministic_composite', 'heuristic_reviewable',
                                'ambiguous', 'unresolved'
                            )),
    score               NUMERIC(6,5) NOT NULL DEFAULT 0,
    reason_codes        TEXT[] NOT NULL DEFAULT '{}',
    claim_level         TEXT NOT NULL DEFAULT 'fact'
                            CHECK (claim_level IN ('fact', 'similarity', 'inference', 'none')),
    source_record_ids   JSONB NOT NULL DEFAULT '[]'::jsonb,
    rule_version        TEXT NOT NULL DEFAULT 'linkage-v1',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_opp_organ_link
    ON public.opportunity_organ_links (
        run_id, opportunity_id, classification, COALESCE(organ_canonical_key, '')
    );
CREATE INDEX IF NOT EXISTS idx_ool_opp ON public.opportunity_organ_links (opportunity_id);
CREATE INDEX IF NOT EXISTS idx_ool_organ ON public.opportunity_organ_links (organ_canonical_key);

-- ---------------------------------------------------------------------------
-- Opportunity → contract links (historical contracts related to opportunity)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.opportunity_contract_links (
    id                  BIGSERIAL PRIMARY KEY,
    run_id              TEXT NOT NULL REFERENCES public.entity_linkage_runs(run_id) ON DELETE CASCADE,
    opportunity_id      BIGINT NOT NULL,
    contract_id         TEXT NOT NULL,              -- pncp_supplier_contracts.contrato_id
    organ_canonical_key TEXT,
    supplier_canonical_key TEXT,
    classification      TEXT NOT NULL
                            CHECK (classification IN (
                                'exact', 'deterministic_composite', 'heuristic_reviewable',
                                'ambiguous', 'unresolved'
                            )),
    score               NUMERIC(6,5) NOT NULL DEFAULT 0,
    reason_codes        TEXT[] NOT NULL DEFAULT '{}',
    claim_level         TEXT NOT NULL DEFAULT 'similarity'
                            CHECK (claim_level IN ('fact', 'similarity', 'inference', 'none')),
    -- non-claim: never assert "participated in this tender" without observation
    non_claims          TEXT[] NOT NULL DEFAULT ARRAY[
        'unobserved_participation',
        'not_inferred_competitor_of_this_tender'
    ],
    source_record_ids   JSONB NOT NULL DEFAULT '[]'::jsonb,
    rule_version        TEXT NOT NULL DEFAULT 'linkage-v1',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_opp_contract_link UNIQUE (run_id, opportunity_id, contract_id)
);

CREATE INDEX IF NOT EXISTS idx_ocl_opp ON public.opportunity_contract_links (opportunity_id);
CREATE INDEX IF NOT EXISTS idx_ocl_contract ON public.opportunity_contract_links (contract_id);
CREATE INDEX IF NOT EXISTS idx_ocl_supplier ON public.opportunity_contract_links (supplier_canonical_key);

-- ---------------------------------------------------------------------------
-- Observed supplier relations (from contracts — winners only as observed)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.observed_supplier_relations (
    id                  BIGSERIAL PRIMARY KEY,
    run_id              TEXT NOT NULL REFERENCES public.entity_linkage_runs(run_id) ON DELETE CASCADE,
    opportunity_id      BIGINT,
    organ_canonical_key TEXT,
    supplier_canonical_key TEXT NOT NULL,
    contract_id         TEXT,
    relation_kind       TEXT NOT NULL DEFAULT 'historical_winner'
                            CHECK (relation_kind IN (
                                'historical_winner',
                                'same_organ_historical',
                                'same_object_region_historical'
                            )),
    classification      TEXT NOT NULL
                            CHECK (classification IN (
                                'exact', 'deterministic_composite', 'heuristic_reviewable',
                                'ambiguous', 'unresolved'
                            )),
    score               NUMERIC(6,5) NOT NULL DEFAULT 0,
    reason_codes        TEXT[] NOT NULL DEFAULT '{}',
    claim_level         TEXT NOT NULL DEFAULT 'fact'
                            CHECK (claim_level IN ('fact', 'similarity', 'inference', 'none')),
    non_claims          TEXT[] NOT NULL DEFAULT ARRAY[
        'not_observed_participant_of_open_tender',
        'not_win_rate',
        'not_consortium_inference'
    ],
    source_record_ids   JSONB NOT NULL DEFAULT '[]'::jsonb,
    rule_version        TEXT NOT NULL DEFAULT 'linkage-v1',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_observed_supplier
    ON public.observed_supplier_relations (
        run_id,
        COALESCE(opportunity_id, 0),
        supplier_canonical_key,
        COALESCE(contract_id, ''),
        relation_kind
    );
CREATE INDEX IF NOT EXISTS idx_osr_opp ON public.observed_supplier_relations (opportunity_id);
CREATE INDEX IF NOT EXISTS idx_osr_supplier ON public.observed_supplier_relations (supplier_canonical_key);

-- ---------------------------------------------------------------------------
-- Review queue for heuristic / ambiguous
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.entity_linkage_review_queue (
    id                  BIGSERIAL PRIMARY KEY,
    run_id              TEXT NOT NULL,
    subject_type        TEXT NOT NULL,  -- opportunity_organ | opportunity_contract | supplier_merge
    subject_id          TEXT NOT NULL,
    classification      TEXT NOT NULL,
    score               NUMERIC(6,5),
    reason_codes        TEXT[] NOT NULL DEFAULT '{}',
    payload             JSONB NOT NULL DEFAULT '{}'::jsonb,
    status              TEXT NOT NULL DEFAULT 'open'
                            CHECK (status IN ('open', 'accepted', 'rejected', 'deferred')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_elrq_open
    ON public.entity_linkage_review_queue (status, run_id)
    WHERE status = 'open';

COMMENT ON TABLE public.canonical_organs IS
  'Golden organ/unit records for linkage; does not replace coverage dual measurement.';
COMMENT ON TABLE public.opportunity_contract_links IS
  'Auditable opportunity→historical contract links. claim_level distinguishes fact vs similarity.';
COMMENT ON TABLE public.observed_supplier_relations IS
  'Observed winners/suppliers from contracts only; never invents tender participation.';

COMMIT;
