-- ============================================================================
-- Migration 050: Fix contracts upsert ambiguity + unblock national PNCP pilot
-- ============================================================================
-- K3.2 / NEXT-30D contracts 90d pilot discovered two blockers:
--
-- 1) upsert_pncp_supplier_contracts RETURNS TABLE(action, contrato_id) and used
--    unqualified "contrato_id" in ON CONFLICT / RETURNING → AmbiguousColumn.
-- 2) FK fk_contracts_{orgao,supplier}_entity_v2 → sc_public_entities (SC-scoped
--    universe, ~2k rows). National /contratos pilot has ~0% FK hit-rate; every
--    insert fails. Supplier CNPJs are not public entities and must not require
--    membership in sc_public_entities for historical contract ingest.
--
-- This migration:
--   - Replaces the upsert RPC with unambiguous column names + constraint target
--   - Dedups input by contrato_id (DISTINCT ON) to avoid multi-conflict batches
--   - Drops the two contract FKs (re-introduce only after a national entity
--     universe exists; see docs/baseline/k3.2-pncp-90d-pilot-next30d.md)
-- ============================================================================

-- 1) Drop FKs that block national contract ingest
ALTER TABLE pncp_supplier_contracts
    DROP CONSTRAINT IF EXISTS fk_contracts_orgao_entity_v2;

ALTER TABLE pncp_supplier_contracts
    DROP CONSTRAINT IF EXISTS fk_contracts_supplier_entity_v2;

-- 2) Fix upsert RPC (ambiguous OUT column vs table column)
CREATE OR REPLACE FUNCTION upsert_pncp_supplier_contracts(p_records JSONB)
RETURNS TABLE (
    action      TEXT,
    contrato_id TEXT
) LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    WITH input AS (
        SELECT DISTINCT ON ((rec->>'contrato_id'))
            rec->>'contrato_id'              AS in_contrato_id,
            rec->>'orgao_cnpj'               AS orgao_cnpj,
            rec->>'orgao_nome'               AS orgao_nome,
            rec->>'fornecedor_cnpj'          AS fornecedor_cnpj,
            rec->>'fornecedor_nome'          AS fornecedor_nome,
            rec->>'objeto_contrato'          AS objeto_contrato,
            NULLIF(rec->>'valor_total', '')::NUMERIC AS valor_total,
            NULLIF(rec->>'data_inicio', '')::DATE    AS data_inicio,
            NULLIF(rec->>'data_fim', '')::DATE       AS data_fim,
            NULLIF(rec->>'data_publicacao', '')::DATE AS data_publicacao,
            rec->>'uf'                       AS uf,
            rec->>'municipio'                AS municipio,
            COALESCE(rec->>'source', 'pncp') AS source,
            rec->>'source_id'                AS source_id
        FROM jsonb_array_elements(p_records) AS rec
        WHERE COALESCE(rec->>'contrato_id', '') <> ''
        ORDER BY (rec->>'contrato_id')
    ),
    inserted AS (
        INSERT INTO pncp_supplier_contracts AS t (
            contrato_id, orgao_cnpj, orgao_nome,
            fornecedor_cnpj, fornecedor_nome,
            objeto_contrato, valor_total,
            data_inicio, data_fim, data_publicacao,
            uf, municipio, source, source_id
        )
        SELECT
            i.in_contrato_id, i.orgao_cnpj, i.orgao_nome,
            i.fornecedor_cnpj, i.fornecedor_nome,
            i.objeto_contrato, i.valor_total,
            i.data_inicio, i.data_fim, i.data_publicacao,
            i.uf, i.municipio, i.source, i.source_id
        FROM input i
        ON CONFLICT ON CONSTRAINT pncp_supplier_contracts_contrato_id_key DO NOTHING
        RETURNING t.contrato_id
    )
    SELECT 'inserted'::TEXT, ins.contrato_id
    FROM inserted ins
    UNION ALL
    SELECT 'skipped'::TEXT, i.in_contrato_id
    FROM input i
    WHERE NOT EXISTS (
        SELECT 1 FROM inserted ins WHERE ins.contrato_id = i.in_contrato_id
    );
END;
$$;

COMMENT ON FUNCTION upsert_pncp_supplier_contracts(JSONB) IS
    'Batch upsert contracts by contrato_id (DO NOTHING). Fixed ambiguous OUT cols (050).';
