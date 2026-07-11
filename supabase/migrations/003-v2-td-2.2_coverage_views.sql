-- ============================================================================
-- 003-v2-td-2.2_coverage_views.sql — Coverage Views (Adaptada de v1 009 + 011)
-- ============================================================================
-- Story TD-2.2: Aplicar Migrations 009-012 Adaptadas
-- Debito: TD-DB-02a (HIGH) — Views de cobertura ausentes na cadeia de migrations
--
-- Adaptada das migrations v1 009 (v_coverage_summary) e v1 011 (v_unmatched_bids).
-- v_coverage_summary ja existe no baseline (001-v2); v_unmatched_bids e NOVA.
--
-- DEPENDENCIA: Esta migration DEPENDE de 005-v2 (match_logging).
-- v_unmatched_bids referencia match_method, match_score e match_confidence,
-- colunas criadas pela migration 005-v2. Aplicar 005-v2 ANTES de 003-v2.
--
-- Ordem de aplicacao obrigatoria:
--   1. 002-v2 (entity_coverage)
--   2. 004-v2 (coverage_snapshots) — depende de entity_coverage
--   3. 005-v2 (match_logging) — independente
--   4. 003-v2 (coverage_views) — DEPENDE de 005-v2
--
-- Principios:
--   - Reexecutavel: CREATE OR REPLACE para todas as views
--   - Schema qualificado (public.)
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. v_coverage_summary — Resumo de cobertura por fonte
-- ============================================================================
-- Ja existe no baseline 001-v2 (Section 4.3). Re-criada para garantir
-- consistencia com o schema atual.
-- Fonte original: v1 009 (indexes_and_coverage.sql)
CREATE OR REPLACE VIEW public.v_coverage_summary AS
SELECT
    ec.source,
    ec.within_200km,
    ec.is_covered,
    COUNT(*) AS entity_count,
    ROUND(
        (COUNT(*)::NUMERIC * 100.0) / SUM(COUNT(*)) OVER (PARTITION BY ec.within_200km), 1
    ) AS pct
FROM public.entity_coverage ec
WHERE EXISTS (
    SELECT 1 FROM public.sc_public_entities e
    WHERE e.id = ec.entity_id AND e.is_active = TRUE
)
GROUP BY ec.source, ec.within_200km, ec.is_covered
ORDER BY ec.source, ec.within_200km, ec.is_covered;

COMMENT ON VIEW public.v_coverage_summary IS
    'Resumo de cobertura por fonte e raio — Story 001.5/001.7, adaptado de v1 009';

-- ============================================================================
-- 2. v_unmatched_bids — Bids sem matched_entity_id (NOVA)
-- ============================================================================
-- Adaptada da migration v1 011 (unmatched_bids_view.sql).
-- View para debugging de bids que nao conseguiram match com nenhum ente.
-- Referencia match_method, match_score, match_confidence (criados em 005-v2).
CREATE OR REPLACE VIEW public.v_unmatched_bids AS
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
FROM public.pncp_raw_bids
WHERE matched_entity_id IS NULL
  AND (
    (orgao_cnpj IS NOT NULL AND orgao_cnpj != '')
    OR (orgao_razao_social IS NOT NULL AND orgao_razao_social != '')
  )
ORDER BY data_publicacao DESC NULLS LAST, ingested_at DESC;

COMMENT ON VIEW public.v_unmatched_bids IS
    'Bids sem matched_entity_id — para debugging do entity name-matching (Story 001.3), adaptado de v1 011';

COMMENT ON COLUMN public.v_unmatched_bids.match_opportunity IS
    'Indica se o bid tem CNPJ (has_cnpj) ou apenas nome (name_only) para match';

COMMENT ON COLUMN public.v_unmatched_bids.recency IS
    'Indica se o bid e recente (90 dias) ou historico';

-- ============================================================================
-- 3. Register in _migrations tracking table
-- ============================================================================
INSERT INTO public._migrations (version, name, applied_at, checksum, rollback_sql)
VALUES (
    '003-v2',
    'td-2.2_coverage_views',
    NOW(),
    'sha256=b8f1a5263dd68297e3b4960c93982e216dd970288eb8ca52f1986053e91799ca',
    'DROP VIEW IF EXISTS public.v_coverage_summary CASCADE; DROP VIEW IF EXISTS public.v_unmatched_bids CASCADE;'
)
ON CONFLICT (version) DO NOTHING;

COMMIT;
