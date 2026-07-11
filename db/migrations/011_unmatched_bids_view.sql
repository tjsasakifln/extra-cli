-- Migration 011: Unmatched bids view for debugging
-- Story 001.3: Entity Name-Matching Refinement
--
-- View para debugging de bids que nao conseguiram match com nenhum ente.
-- Facilita identificacao de:
--   - Bids com orgao_cnpj valido sem ente correspondente (entes faltando?)
--   - Bids com nome incompleto/inconsistente (normalizacao insuficiente?)
--   - Bids com threshold de fuzzy abaixo do configurado

CREATE OR REPLACE VIEW v_unmatched_bids AS
SELECT
    pncp_id,
    source,
    orgao_cnpj,
    orgao_razao_social,
    municipio,
    codigo_municipio_ibge,
    data_publicacao,
    match_method,
    match_score,
    match_confidence,
    ingested_at,
    CASE
        WHEN orgao_cnpj IS NOT NULL AND orgao_cnpj != '' THEN 'has_cnpj'
        ELSE 'name_only'
    END AS match_opportunity,
    CASE
        WHEN data_publicacao >= CURRENT_DATE - 90 THEN 'recent'
        ELSE 'historical'
    END AS recency
FROM pncp_raw_bids
WHERE matched_entity_id IS NULL
  AND (
    (orgao_cnpj IS NOT NULL AND orgao_cnpj != '')
    OR (orgao_razao_social IS NOT NULL AND orgao_razao_social != '')
  )
ORDER BY data_publicacao DESC NULLS LAST, ingested_at DESC;

COMMENT ON VIEW v_unmatched_bids IS
    'Bids sem matched_entity_id — para debugging do entity name-matching (Story 001.3)';

COMMENT ON COLUMN v_unmatched_bids.match_opportunity IS
    'Indica se o bid tem CNPJ (has_cnpj) ou apenas nome (name_only) para match';
COMMENT ON COLUMN v_unmatched_bids.recency IS
    'Indica se o bid e recente (90 dias) ou historico';
