-- 103_contract_lifecycle_truth.sql
-- Story: contract-lifecycle-truth-v1 (additive only).
--
-- Migrations 077/091/101 stay untouched. This file adds three new SQL routines
-- and one new view. It never mutates any object that existed before it.
--
-- Why: v_contracts_canonical_v2 exposes is_active, which is 100% TRUE in
-- production and therefore carries no information. The Contract Truth stamps
-- (status_normalized, quality_state) written by scripts/contracts_truth.py are
-- not carried by that view. This view PROJECTS those stamps into an explicit
-- lifecycle vocabulary. It never re-derives them: classify_contract_activity
-- and classify_contract_quality remain the only classifiers.
--
-- The lifecycle derivation is the 7 x 4 = 28 cell truth table documented in
-- docs/decisions/contract-lifecycle-truth-v1.md. lifecycle_state is a function
-- of status_normalized alone; lifecycle_trust is a function of quality_state
-- alone; lifecycle_is_current_evidence is the AND-gate of the two and is TRUE
-- in exactly one of the 28 cells.
--
-- Nothing here is rebound to any existing consumer. commercial_authority_v2.py
-- and rebuild_commercial_qualification.py keep reading v_contracts_canonical_v2
-- unchanged, so ICP membership cannot change.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

-- ---------------------------------------------------------------------------
-- Contracting act date: the canonical precedence, in SQL.
--
-- Mirrors scripts/confenge_activation/commercial_authority_v2.py
-- QUALIFYING_DATE_PRECEDENCE (data_assinatura, data_inicio, data_publicacao,
-- data_publicacao_fonte) and contracting_date(): first non-NULL wins.
-- data_fim is deliberately absent: it is an execution-end estimate.
--
-- Deliberately NOT strict: a NULL in one input must not blank the whole
-- result, otherwise the precedence itself would be unusable.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.contract_contracting_date_v1(
    data_assinatura DATE,
    data_inicio DATE,
    data_publicacao DATE,
    data_publicacao_fonte DATE
)
RETURNS DATE
LANGUAGE SQL
IMMUTABLE
PARALLEL SAFE
AS $contracting_date_v1$
    SELECT COALESCE(
        data_assinatura,
        data_inicio,
        data_publicacao,
        data_publicacao_fonte
    );
$contracting_date_v1$;

COMMENT ON FUNCTION public.contract_contracting_date_v1(DATE, DATE, DATE, DATE) IS
'Contracting act date by the canonical precedence data_assinatura > data_inicio > data_publicacao > data_publicacao_fonte. Mirrors commercial_authority_v2.contracting_date(). Returns NULL when all four inputs are NULL, matching that function''s None.';

-- ---------------------------------------------------------------------------
-- Which precedence field produced the contracting act date.
--
-- Returns '' (empty string), never NULL, when all four inputs are NULL. This
-- mirrors commercial_authority_v2.contracting_date()'s `return None, ""`
-- byte for byte: psycopg2 maps SQL NULL to Python None, and None != ''.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.contract_contracting_date_field_v1(
    data_assinatura DATE,
    data_inicio DATE,
    data_publicacao DATE,
    data_publicacao_fonte DATE
)
RETURNS TEXT
LANGUAGE SQL
IMMUTABLE
PARALLEL SAFE
AS $contracting_date_field_v1$
    SELECT CASE
        WHEN data_assinatura IS NOT NULL THEN 'data_assinatura'
        WHEN data_inicio IS NOT NULL THEN 'data_inicio'
        WHEN data_publicacao IS NOT NULL THEN 'data_publicacao'
        WHEN data_publicacao_fonte IS NOT NULL THEN 'data_publicacao_fonte'
        ELSE ''
    END::TEXT;
$contracting_date_field_v1$;

COMMENT ON FUNCTION public.contract_contracting_date_field_v1(DATE, DATE, DATE, DATE) IS
'Name of the precedence field that produced contract_contracting_date_v1. Empty string, never NULL, when all four inputs are NULL, mirroring commercial_authority_v2.contracting_date().';

-- ---------------------------------------------------------------------------
-- Rolling qualification window floor: anchor minus 3 years, Go style.
--
-- Mirrors commercial_authority_v2.add_years_go(anchor, -QUALIFICATION_WINDOW_YEARS)
-- and therefore window_floor(), which is that same call with now.date().
-- Go's time.Time.AddDate shifts the year and then normalizes an out-of-range
-- day FORWARD, so 2024-02-29 minus 3 years is 2021-03-01, not 2021-02-28.
-- Warmbly (Go) consumes the same semantics downstream, so the arithmetic must
-- agree byte for byte.
--
-- A pure year shift can only produce an invalid date for February 29 landing
-- on a non-leap year; every other (month, day) exists in every year. That is
-- the single normalization branch below.
--
-- The anchor is an explicit parameter, never an internal CURRENT_DATE read, so
-- the view and the SQL-vs-Python parity test call one and the same function.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.contract_window_floor_v1(anchor DATE)
RETURNS DATE
LANGUAGE SQL
IMMUTABLE
PARALLEL SAFE
AS $window_floor_v1$
    SELECT CASE
        WHEN anchor IS NULL THEN NULL::DATE
        WHEN EXTRACT(MONTH FROM anchor)::INT = 2
             AND EXTRACT(DAY FROM anchor)::INT = 29
             AND NOT (
                 (
                     (EXTRACT(YEAR FROM anchor)::INT - 3) % 4 = 0
                     AND (EXTRACT(YEAR FROM anchor)::INT - 3) % 100 <> 0
                 )
                 OR (EXTRACT(YEAR FROM anchor)::INT - 3) % 400 = 0
             )
        THEN make_date(EXTRACT(YEAR FROM anchor)::INT - 3, 3, 1)
        ELSE make_date(
            EXTRACT(YEAR FROM anchor)::INT - 3,
            EXTRACT(MONTH FROM anchor)::INT,
            EXTRACT(DAY FROM anchor)::INT
        )
    END;
$window_floor_v1$;

COMMENT ON FUNCTION public.contract_window_floor_v1(DATE) IS
'First date still inside the rolling three-year qualification window as of the given anchor. Go-style year subtraction with day-overflow-forward normalization, identical to commercial_authority_v2.add_years_go(anchor, -3).';

-- ---------------------------------------------------------------------------
-- v_contract_lifecycle_truth_v1
--
-- One row per dedup key, where dedup key is
-- COALESCE(NULLIF(canonical_contract_id, ''), contrato_id). canonical_contract_id
-- has no unique constraint and is not backfilled, so rows without it fall back
-- to contrato_id, which is UNIQUE, and are never collapsed with unrelated rows.
--
-- Row population replicates v_contracts_canonical_v2's filter
-- (077_contract_roles_canonical_v2.sql:212) so the two views stay comparable.
-- The predicate is parenthesized because AND binds tighter than OR.
--
-- is_active is READ but never projected: it only decides whether the audit code
-- LIFECYCLE_LEGACY_IS_ACTIVE_IGNORED is emitted. It never influences
-- lifecycle_state, lifecycle_trust or lifecycle_is_current_evidence.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.v_contract_lifecycle_truth_v1 AS
SELECT DISTINCT ON (
    COALESCE(NULLIF(contract.canonical_contract_id, ''), contract.contrato_id)
)
    COALESCE(NULLIF(contract.canonical_contract_id, ''), contract.contrato_id) AS dedup_key,
    contract.contrato_id,
    contract.canonical_contract_id,
    contract.source,
    contract.source_contract_id,
    contract.parent_procurement_id,
    contract.first_seen_at,
    contract.last_seen_at,
    contract.ingested_at,
    contract.query_window_start,
    contract.query_window_end,

    contract.orgao_cnpj AS buyer_cnpj,
    contract.orgao_cnpj_8 AS buyer_cnpj_8,
    contract.orgao_nome AS buyer_nome,
    roles.buyer_entity_id,
    buyer.razao_social AS buyer_entity_nome,
    buyer.cnpj_8 AS buyer_entity_cnpj_8,
    buyer.raio_200km AS buyer_within_200km,
    roles.buyer_match_method,
    roles.buyer_match_confidence,
    roles.buyer_reason_codes,

    roles.supplier_identity_id,
    contract.supplier_id_type,
    contract.supplier_identifier_export,
    contract.supplier_country,
    contract.fornecedor_cnpj AS supplier_cnpj,
    contract.fornecedor_cnpj_8 AS supplier_cnpj_8,
    contract.fornecedor_nome AS supplier_nome,
    roles.supplier_match_method,
    roles.supplier_match_confidence,
    roles.supplier_reason_codes,

    contract.objeto_contrato AS objeto,
    contract.valor_total AS valor,
    contract.data_inicio,
    contract.data_fim,
    contract.data_publicacao,
    contract.data_assinatura,
    contract.data_publicacao_fonte,
    contract.uf,
    contract.municipio,
    contract.codigo_municipio_ibge,
    contract.municipio_inferido,

    contract.status_raw,
    contract.status_normalized,
    contract.status_rule_version,
    contract.status_source,
    contract.status_observed_at,
    contract.quality_state,
    contract.quality_reasons,
    contract.quality_rule_version,

    -- lifecycle_state: function of status_normalized ONLY.
    -- NULL (never stamped) and any unrecognized value both fail closed to
    -- UNKNOWN: absence of a stamp is never evidence of activity or of
    -- termination.
    CASE contract.status_normalized
        WHEN 'ACTIVE_PROVEN' THEN 'ACTIVE_PROVEN'
        WHEN 'COMPLETED' THEN 'COMPLETED'
        WHEN 'CANCELLED' THEN 'CANCELLED'
        WHEN 'TERMINATED' THEN 'TERMINATED'
        WHEN 'SUSPENDED' THEN 'SUSPENDED'
        WHEN 'UNKNOWN' THEN 'UNKNOWN'
        ELSE 'UNKNOWN'
    END::TEXT AS lifecycle_state,

    -- lifecycle_trust: function of quality_state ONLY.
    CASE contract.quality_state
        WHEN 'VALID' THEN 'TRUSTED'
        WHEN 'REVIEW' THEN 'REVIEW'
        WHEN 'QUARANTINED' THEN 'UNTRUSTED'
        ELSE 'UNSTAMPED'
    END::TEXT AS lifecycle_trust,

    -- The single positive branch of the whole rule. IS NOT DISTINCT FROM keeps
    -- the result strictly TRUE/FALSE when either stamp is NULL.
    (
        contract.status_normalized IS NOT DISTINCT FROM 'ACTIVE_PROVEN'
        AND contract.quality_state IS NOT DISTINCT FROM 'VALID'
    ) AS lifecycle_is_current_evidence,

    -- Additive audit codes: exactly one quality code always, plus
    -- LIFECYCLE_UNSTAMPED when the activity stamp is absent, plus
    -- LIFECYCLE_LEGACY_IS_ACTIVE_IGNORED when the legacy flag would have
    -- claimed activity and was discarded. Never empty; 1 to 3 codes.
    (
        ARRAY[
            CASE contract.quality_state
                WHEN 'VALID' THEN 'LIFECYCLE_TRUSTED'
                WHEN 'REVIEW' THEN 'LIFECYCLE_REVIEW'
                WHEN 'QUARANTINED' THEN 'LIFECYCLE_UNTRUSTED'
                ELSE 'LIFECYCLE_QUALITY_UNSTAMPED'
            END
        ]::TEXT[]
        || CASE
            WHEN contract.status_normalized IS NULL
            THEN ARRAY['LIFECYCLE_UNSTAMPED']::TEXT[]
            ELSE ARRAY[]::TEXT[]
        END
        || CASE
            WHEN contract.status_normalized IS NULL AND contract.is_active IS TRUE
            THEN ARRAY['LIFECYCLE_LEGACY_IS_ACTIVE_IGNORED']::TEXT[]
            ELSE ARRAY[]::TEXT[]
        END
    ) AS lifecycle_reason_codes,

    public.contract_contracting_date_v1(
        contract.data_assinatura,
        contract.data_inicio,
        contract.data_publicacao,
        contract.data_publicacao_fonte
    ) AS contracting_date,

    public.contract_contracting_date_field_v1(
        contract.data_assinatura,
        contract.data_inicio,
        contract.data_publicacao,
        contract.data_publicacao_fonte
    ) AS contracting_date_field,

    -- One implementation of the floor arithmetic: the same sanctioned function
    -- the parity test calls directly. Upper bound is CURRENT_DATE, matching
    -- qualify_root()'s `resolved > today` exclusion.
    COALESCE(
        public.contract_contracting_date_v1(
            contract.data_assinatura,
            contract.data_inicio,
            contract.data_publicacao,
            contract.data_publicacao_fonte
        ) BETWEEN public.contract_window_floor_v1(CURRENT_DATE) AND CURRENT_DATE,
        FALSE
    ) AS contracting_date_in_qualification_window

FROM public.pncp_supplier_contracts contract
LEFT JOIN public.contract_role_links roles
    ON roles.contract_id = contract.contrato_id
LEFT JOIN public.sc_public_entities buyer
    ON buyer.id = roles.buyer_entity_id
WHERE (contract.data_inicio IS NOT NULL OR contract.data_publicacao IS NOT NULL)
ORDER BY
    COALESCE(NULLIF(contract.canonical_contract_id, ''), contract.contrato_id),
    contract.last_seen_at DESC NULLS LAST,
    contract.id DESC;

COMMENT ON VIEW public.v_contract_lifecycle_truth_v1 IS
'Additive projection of the Contract Truth stamps into an explicit lifecycle vocabulary. lifecycle_state derives from status_normalized alone, lifecycle_trust from quality_state alone, lifecycle_is_current_evidence is their AND-gate and is TRUE only for ACTIVE_PROVEN plus VALID. The legacy is_active flag is read for the audit code LIFECYCLE_LEGACY_IS_ACTIVE_IGNORED and is never projected nor allowed to influence any lifecycle column. Nothing is re-derived here: classify_contract_activity and classify_contract_quality remain the only classifiers.';

REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON public.v_contract_lifecycle_truth_v1 FROM PUBLIC;
GRANT SELECT ON public.v_contract_lifecycle_truth_v1 TO PUBLIC;

COMMIT;
