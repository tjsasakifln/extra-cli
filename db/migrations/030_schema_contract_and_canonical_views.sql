-- ============================================================================
-- Migration 030: Schema Contract + Canonical Views
-- ============================================================================
-- Story 1.2 (Unify Schema) — Task 5: Canonical Views
--
-- Define as 5 views canonicas estaveis que servem como CONTRATO entre o
-- schema fisico e os consumers (Python queries, reports, intel pipelines).
--
-- Principios (Secao 6.2 do Plano Mestre):
--   1. CREATE OR REPLACE VIEW — idempotente, seguro para reaplicacao
--   2. Nomes de colunas estaveis — NAO mudam sem major version bump
--   3. Prefixo v_*_canonical para views canonicas
--   4. Todas registradas em _migrations tracking
--
-- Contrato completo: docs/stories/story-1.2-canonical-views-contract.md
--
-- Depende de: 001-029 (sc_public_entities, pncp_raw_bids, pncp_supplier_contracts,
--             enriched_entities, entity_coverage existem)
-- Idempotente: Sim (OR REPLACE + IF NOT EXISTS)
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. v_entities_canonical — Entidades publicas de SC
-- ============================================================================
-- Proposito: Visao unificada de entidades + cobertura
-- Consumers: consulting_readiness.py, coverage_truth.py, intel_pipeline.py
-- ============================================================================
CREATE OR REPLACE VIEW public.v_entities_canonical AS
SELECT
    e.id                 AS entity_id,
    e.cnpj_8             AS cnpj_8_base,
    e.razao_social       AS razao_social,
    e.municipio          AS municipio,
    e.codigo_ibge        AS codigo_ibge,
    e.natureza_juridica  AS natureza_juridica,
    e.cod_natureza       AS cod_natureza,
    e.latitude,
    e.longitude,
    e.distancia_fk       AS distancia_fk,
    e.raio_200km         AS within_200km,
    e.is_active          AS is_active,
    ec.total_bids        AS total_bids,
    ec.is_covered        AS is_covered,
    ec.last_seen_at      AS last_coverage_at
FROM public.sc_public_entities e
LEFT JOIN public.entity_coverage ec ON ec.entity_id = e.id AND ec.source = 'pncp';

COMMENT ON VIEW public.v_entities_canonical IS
    'Canonical entity view v1.0 — entidades SC com metadados de cobertura. Story 1.2';

COMMENT ON COLUMN public.v_entities_canonical.entity_id IS 'PK da entidade (sc_public_entities.id)';
COMMENT ON COLUMN public.v_entities_canonical.cnpj_8_base IS 'CNPJ base 8 digitos';
COMMENT ON COLUMN public.v_entities_canonical.within_200km IS 'Dentro do raio 200km de Florianopolis';
COMMENT ON COLUMN public.v_entities_canonical.last_coverage_at IS 'Ultima vez que a entidade foi coberta por crawl';
COMMENT ON COLUMN public.v_entities_canonical.is_covered IS 'Se a entidade tem coverage ativa';

-- ============================================================================
-- 2. v_open_opportunities_canonical — Licitacoes abertas
-- ============================================================================
-- Proposito: Oportunidades abertas com dados normalizados
-- Consumers: opportunity_intel pipeline, ranking, radar
-- ============================================================================
CREATE OR REPLACE VIEW public.v_open_opportunities_canonical AS
SELECT
    b.pncp_id                AS bid_id,
    b.pncp_id                AS pncp_id,
    b.objeto_compra          AS objeto,
    b.valor_total_estimado   AS valor_estimado,
    b.modalidade_id,
    b.modalidade_nome        AS modalidade,
    b.esfera_id              AS esfera_id,
    b.uf,
    b.municipio,
    b.codigo_municipio_ibge  AS codigo_ibge,
    b.orgao_cnpj,
    b.orgao_razao_social     AS orgao_nome,
    b.data_publicacao,
    b.data_abertura,
    b.data_encerramento,
    b.link_pncp              AS link_edital,
    b.source,
    b.source_id,
    b.match_method,
    b.match_score,
    b.match_confidence,
    e.id                     AS matched_entity_id,
    e.razao_social           AS matched_entity_nome,
    e.raio_200km             AS within_200km,
    e.cnpj_8                 AS entity_cnpj_8
FROM public.pncp_raw_bids b
LEFT JOIN public.sc_public_entities e ON e.id = b.matched_entity_id
WHERE b.data_encerramento >= CURRENT_DATE
   OR (b.data_encerramento IS NULL AND b.data_publicacao >= CURRENT_DATE - INTERVAL '30 days');

COMMENT ON VIEW public.v_open_opportunities_canonical IS
    'Canonical open opportunities view v1.0 — licitacoes abertas. Story 1.2';

COMMENT ON COLUMN public.v_open_opportunities_canonical.within_200km IS
    'Se a entidade matched esta dentro do raio 200km';

-- ============================================================================
-- 3. v_contracts_canonical — Contratos de fornecedores
-- ============================================================================
-- Proposito: Contratos com dados de entidades e enriched_entities
-- Consumers: consulting_readiness.py (market share, HHI), contract_intel CLI
-- ============================================================================
CREATE OR REPLACE VIEW public.v_contracts_canonical AS
SELECT
    c.contrato_id,
    c.orgao_cnpj,
    c.orgao_nome,
    c.fornecedor_cnpj,
    c.fornecedor_nome,
    c.objeto_contrato        AS objeto,
    c.valor_total            AS valor,
    c.data_inicio,
    c.data_fim,
    c.data_publicacao,
    c.uf,
    c.municipio,
    c.codigo_municipio_ibge,
    c.municipio_inferido,
    c.source,
    c.source_id,
    e.id                     AS entity_id,
    e.razao_social           AS entity_nome,
    e.cnpj_8                 AS entity_cnpj_8,
    e.raio_200km             AS within_200km,
    enr.cnae_principal,
    enr.natureza_juridica
FROM public.pncp_supplier_contracts c
LEFT JOIN public.sc_public_entities e ON e.cnpj_8 = LEFT(c.fornecedor_cnpj, 8)
LEFT JOIN public.enriched_entities enr ON enr.cnpj = c.fornecedor_cnpj
WHERE c.data_inicio IS NOT NULL OR c.data_publicacao IS NOT NULL;

COMMENT ON VIEW public.v_contracts_canonical IS
    'Canonical contracts view v1.0 — contratos ativos com dados de fornecedores. Story 1.2';

-- ============================================================================
-- 4. v_suppliers_canonical — Cadastro de fornecedores
-- ============================================================================
-- Proposito: Fornecedores com metadados agregados de contratos
-- Consumers: intel pipeline, report generation
-- ============================================================================
CREATE OR REPLACE VIEW public.v_suppliers_canonical AS
SELECT
    e.cnpj                          AS cnpj_completo,
    e.razao_social,
    e.nome_fantasia,
    e.cnae_principal,
    e.cnae_secundarios,
    e.municipio,
    e.uf,
    e.codigo_ibge,
    e.natureza_juridica,
    e.situacao,
    e.enriched_at                   AS ultima_atualizacao,
    e.enriched_source,
    sc.cnpj_8                       AS entidade_cnpj_8,
    sc.razao_social                 AS entidade_nome,
    sc.raio_200km                   AS within_200km,
    COUNT(DISTINCT c.contrato_id)   AS total_contratos,
    SUM(c.valor_total)              AS valor_total_contratos
FROM public.enriched_entities e
LEFT JOIN public.sc_public_entities sc ON sc.cnpj_8 = LEFT(e.cnpj, 8)
LEFT JOIN public.pncp_supplier_contracts c ON c.fornecedor_cnpj = e.cnpj
GROUP BY e.cnpj, e.razao_social, e.nome_fantasia, e.cnae_principal,
         e.cnae_secundarios, e.municipio, e.uf, e.codigo_ibge,
         e.natureza_juridica, e.situacao, e.enriched_at, e.enriched_source,
         sc.cnpj_8, sc.razao_social, sc.raio_200km;

COMMENT ON VIEW public.v_suppliers_canonical IS
    'Canonical suppliers view v1.0 — fornecedores com agregacao de contratos. Story 1.2';

-- ============================================================================
-- 5. v_value_observations_canonical — Observacoes de valor
-- ============================================================================
-- Proposito: Valores de bids e contratos para analise estatistica
-- Consumers: lib/bid_simulator.py, lib/value_semantics.py
-- ============================================================================
CREATE OR REPLACE VIEW public.v_value_observations_canonical AS
SELECT
    'bid'::TEXT                      AS observation_type,
    b.pncp_id                        AS source_id,
    b.orgao_cnpj,
    b.municipio,
    b.uf,
    b.modalidade_id,
    b.modalidade_nome                AS modalidade,
    b.objeto_compra                  AS objeto,
    b.valor_total_estimado           AS valor,
    b.data_publicacao,
    e.cnpj_8                         AS entity_cnpj_8,
    e.raio_200km                     AS within_200km
FROM public.pncp_raw_bids b
LEFT JOIN public.sc_public_entities e ON e.id = b.matched_entity_id
WHERE b.valor_total_estimado IS NOT NULL AND b.valor_total_estimado > 0

UNION ALL

SELECT
    'contract'::TEXT                 AS observation_type,
    c.contrato_id                    AS source_id,
    c.orgao_cnpj,
    c.municipio,
    c.uf,
    NULL::INTEGER                    AS modalidade_id,
    NULL::TEXT                       AS modalidade,
    c.objeto_contrato                AS objeto,
    c.valor_total                    AS valor,
    c.data_publicacao,
    e.cnpj_8                         AS entity_cnpj_8,
    e.raio_200km                     AS within_200km
FROM public.pncp_supplier_contracts c
LEFT JOIN public.sc_public_entities e ON e.cnpj_8 = LEFT(c.fornecedor_cnpj, 8)
WHERE c.valor_total IS NOT NULL AND c.valor_total > 0;

COMMENT ON VIEW public.v_value_observations_canonical IS
    'Canonical value observations view v1.0 — bids e contracts para analise. Story 1.2';
COMMENT ON COLUMN public.v_value_observations_canonical.observation_type IS
    'Tipo: ''bid'' para licitacao, ''contract'' para contrato';

-- ============================================================================
-- Rollback SQL (remove views in reverse order)
-- ============================================================================
-- DROP VIEW IF EXISTS public.v_value_observations_canonical;
-- DROP VIEW IF EXISTS public.v_suppliers_canonical;
-- DROP VIEW IF EXISTS public.v_contracts_canonical;
-- DROP VIEW IF EXISTS public.v_open_opportunities_canonical;
-- DROP VIEW IF EXISTS public.v_entities_canonical;

COMMIT;
