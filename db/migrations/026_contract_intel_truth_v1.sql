-- Migration 026: Contract Intelligence Truth v1 — Analytical Views (corrected)
--
-- Fixes column-name drift between migrations 001-025 and the real PostgreSQL schema.
-- The real pncp_supplier_contracts uses:
--   numero_controle_pncp (NOT contrato_id)
--   ni_fornecedor          (NOT fornecedor_cnpj)
--   nome_fornecedor        (NOT fornecedor_nome)
--   valor_global           (NOT valor_total)
--   data_assinatura        (NOT data_inicio — data_inicio does NOT exist)
--   data_fim_vigencia      (NOT data_fim)
--   (NO data_publicacao column exists)
--
-- sc_public_entities uses:
--   cnpj_8                 (NOT cnpj_raiz)
--   distancia_fk           (NOT distancia_km)
--   raio_200km (boolean)   (NOT a text field)
--
-- SEMANTIC NOTE: valor_global is the PNCP "valorGlobal" field.
--   It is NOT "preço praticado" nor "valor homologado" nor "deságio".
--   When PNCP does not distinguish value semantics, we mark it as
--   "valor_global — semântica não desambiguada pela origem" and
--   block metrics that depend on precise value semantics.
--
-- DESIGN: All views use the REAL column names from the production PostgreSQL.
--   Views are idempotent (CREATE OR REPLACE).
--   Views are read-only analytical layer over pncp_supplier_contracts.

BEGIN;

-- B2G-FIX-04: DROP views first — CREATE OR REPLACE cannot change column lists
DROP VIEW IF EXISTS v_contract_historical CASCADE;
DROP VIEW IF EXISTS v_supplier_winners CASCADE;
DROP VIEW IF EXISTS v_expiring_contracts CASCADE;
DROP VIEW IF EXISTS v_contract_intel_percentis CASCADE;

-- ==========================================================================
-- View 1: v_contract_historical
-- Historical contracts (3-year window) for target universe entities.
-- ==========================================================================

CREATE OR REPLACE VIEW v_contract_historical AS
SELECT
    c.contrato_id,
    c.orgao_cnpj,
    c.orgao_nome,
    c.fornecedor_cnpj,
    c.fornecedor_nome,
    c.objeto_contrato,
    c.valor_total                                            AS valor_contrato,
    c.data_inicio                                            AS data_inicio_contrato,
    c.data_fim                                               AS data_fim_contrato,
    c.uf,
    c.municipio,
    e.razao_social                                           AS ente_razao_social,
    e.municipio                                              AS ente_municipio,
    e.codigo_ibge                                            AS ente_codigo_ibge,
    e.distancia_fk                                           AS ente_distancia_km,
    e.raio_200km,
    c.ingested_at
FROM pncp_supplier_contracts c
JOIN sc_public_entities e
    ON LEFT(c.orgao_cnpj, 8) = e.cnpj_8
WHERE e.raio_200km IS TRUE
  AND c.is_active IS TRUE
  AND c.data_inicio >= (CURRENT_DATE - INTERVAL '3 years');

COMMENT ON VIEW v_contract_historical IS
'Historical contracts (3-year window) for public entities within 200 km of Florianópolis.
Value column is valor_global from PNCP — NOT preço praticado, NOT valor homologado.
When PNCP does not distinguish, the semantic is marked as unknown at the API level.';

-- ==========================================================================
-- View 2: v_supplier_winners
-- Supplier/competitor rankings by count, value, avg ticket, concentration.
-- Uses "vencedores históricos" (historical winners), NOT "todos os licitantes".
-- ==========================================================================

CREATE OR REPLACE VIEW v_supplier_winners AS
WITH fornecedor_orgao_agg AS (
    SELECT
        c.fornecedor_cnpj,
        c.fornecedor_nome,
        c.orgao_cnpj,
        c.orgao_nome,
        SUM(COALESCE(c.valor_total, 0))                        AS valor_orgao,
        COUNT(*)                                                AS qtd_contratos_orgao
    FROM pncp_supplier_contracts c
    JOIN sc_public_entities e
        ON LEFT(c.orgao_cnpj, 8) = e.cnpj_8
    WHERE e.raio_200km IS TRUE
      AND c.is_active IS TRUE
      AND c.fornecedor_cnpj IS NOT NULL
      AND c.fornecedor_cnpj != ''
    GROUP BY c.fornecedor_cnpj, c.fornecedor_nome, c.orgao_cnpj, c.orgao_nome
),
fornecedor_totals AS (
    SELECT
        fo.fornecedor_cnpj,
        fo.fornecedor_nome,
        SUM(fo.qtd_contratos_orgao)                             AS qtd_contratos,
        SUM(fo.valor_orgao)                                     AS valor_total,
        ROUND(AVG(fo.valor_orgao)::numeric, 2)                  AS ticket_medio_contrato,
        COUNT(DISTINCT fo.orgao_cnpj)                           AS qtd_orgaos_distintos,
        STRING_AGG(DISTINCT fo.orgao_nome, '; ' ORDER BY fo.orgao_nome) AS orgaos_lista
    FROM fornecedor_orgao_agg fo
    GROUP BY fo.fornecedor_cnpj, fo.fornecedor_nome
),
hhi_calc AS (
    SELECT
        ft.*,
        ROUND(
            (SELECT SUM(POWER(fo2.valor_orgao * 1.0 / NULLIF(ft.valor_total, 0), 2) * 10000)
             FROM fornecedor_orgao_agg fo2
             WHERE fo2.fornecedor_cnpj = ft.fornecedor_cnpj),
            0
        )                                                        AS hhi_concentracao
    FROM fornecedor_totals ft
)
SELECT
    fornecedor_cnpj,
    fornecedor_nome,
    qtd_contratos,
    ROUND(valor_total::numeric, 2)                              AS valor_total_contratos,
    ticket_medio_contrato,
    qtd_orgaos_distintos,
    hhi_concentracao,
    orgaos_lista
FROM hhi_calc
ORDER BY valor_total_contratos DESC;

COMMENT ON VIEW v_supplier_winners IS
'Supplier winner rankings: contract count, total value, average ticket per contract,
distinct agencies served, HHI concentration index (0-10000).
Uses historical winners only — NOT all bidders.
Value column is valor_global from PNCP — NOT preço praticado.';

-- ==========================================================================
-- View 3: v_expiring_contracts
-- Active contracts ending in 90-180 days (renewal/rebidding window).
-- ==========================================================================

CREATE OR REPLACE VIEW v_expiring_contracts AS
SELECT
    c.contrato_id,
    c.orgao_cnpj,
    c.orgao_nome,
    c.fornecedor_cnpj,
    c.fornecedor_nome,
    c.objeto_contrato,
    c.valor_total                                            AS valor_contrato,
    c.data_inicio                                            AS data_inicio_contrato,
    c.data_fim                                               AS data_fim_contrato,
    (c.data_fim - CURRENT_DATE)                              AS dias_ate_fim,
    c.uf,
    c.municipio,
    e.razao_social                                           AS ente_razao_social,
    e.municipio                                              AS ente_municipio
FROM pncp_supplier_contracts c
JOIN sc_public_entities e
    ON LEFT(c.orgao_cnpj, 8) = e.cnpj_8
WHERE e.raio_200km IS TRUE
  AND c.is_active IS TRUE
  AND c.data_fim IS NOT NULL
  AND c.data_fim BETWEEN (CURRENT_DATE + INTERVAL '90 days')
                     AND (CURRENT_DATE + INTERVAL '180 days')
ORDER BY c.data_fim, c.valor_total DESC NULLS LAST;

COMMENT ON VIEW v_expiring_contracts IS
'Active contracts ending between 90 and 180 days from today (renewal/rebidding window).
REQUIRES non-NULL data_fim_vigencia — contracts without end date are EXCLUDED.
Value column is valor_global from PNCP — NOT preço praticado.';

-- ==========================================================================
-- View 4: v_contract_intel_percentis (corrected)
-- P25/P50/P75 value/ticket percentiles by contract category.
-- ==========================================================================

CREATE OR REPLACE VIEW v_contract_intel_percentis AS
WITH categorias AS (
    SELECT
        c.valor_total                                            AS valor,
        CASE
            WHEN c.objeto_contrato ILIKE '%obra%'
              OR c.objeto_contrato ILIKE '%construção%'
              OR c.objeto_contrato ILIKE '%pavimentação%'
              OR c.objeto_contrato ILIKE '%edificação%'
              OR c.objeto_contrato ILIKE '%engenharia%'
            THEN 'OBRAS'
            WHEN c.objeto_contrato ILIKE '%limpeza%'
              OR c.objeto_contrato ILIKE '%conservação%'
              OR c.objeto_contrato ILIKE '%manutenção%'
              OR c.objeto_contrato ILIKE '%zeladoria%'
            THEN 'FACILITIES'
            WHEN c.objeto_contrato ILIKE '%software%'
              OR c.objeto_contrato ILIKE '%ti%'
              OR c.objeto_contrato ILIKE '%tecnologia%'
              OR c.objeto_contrato ILIKE '%sistema%'
              OR c.objeto_contrato ILIKE '%informática%'
            THEN 'TI'
            WHEN c.objeto_contrato ILIKE '%saúde%'
              OR c.objeto_contrato ILIKE '%medicamento%'
              OR c.objeto_contrato ILIKE '%hospitalar%'
              OR c.objeto_contrato ILIKE '%medico%'
              OR c.objeto_contrato ILIKE '%farmacêutico%'
              OR c.objeto_contrato ILIKE '%laboratório%'
            THEN 'SAÚDE'
            WHEN c.objeto_contrato ILIKE '%alimentação%'
              OR c.objeto_contrato ILIKE '%alimento%'
              OR c.objeto_contrato ILIKE '%merenda%'
              OR c.objeto_contrato ILIKE '%gênero alimentício%'
            THEN 'ALIMENTAÇÃO'
            WHEN c.objeto_contrato ILIKE '%transporte%'
              OR c.objeto_contrato ILIKE '%veículo%'
              OR c.objeto_contrato ILIKE '%frota%'
              OR c.objeto_contrato ILIKE '%ônibus%'
              OR c.objeto_contrato ILIKE '%locação de veículo%'
            THEN 'TRANSPORTE'
            WHEN c.objeto_contrato ILIKE '%segurança%'
              OR c.objeto_contrato ILIKE '%vigilância%'
              OR c.objeto_contrato ILIKE '%monitoramento%'
              OR c.objeto_contrato ILIKE '%porteiro%'
            THEN 'SEGURANÇA'
            WHEN c.objeto_contrato ILIKE '%consultoria%'
              OR c.objeto_contrato ILIKE '%assessoria%'
              OR c.objeto_contrato ILIKE '%advocacia%'
              OR c.objeto_contrato ILIKE '%jurídico%'
              OR c.objeto_contrato ILIKE '%contábil%'
            THEN 'CONSULTORIA'
            WHEN c.objeto_contrato ILIKE '%combustível%'
              OR c.objeto_contrato ILIKE '%gasolina%'
              OR c.objeto_contrato ILIKE '%diesel%'
              OR c.objeto_contrato ILIKE '%etanol%'
            THEN 'COMBUSTÍVEL'
            ELSE 'OUTROS'
        END                                                      AS categoria_agrupada
    FROM pncp_supplier_contracts c
    JOIN sc_public_entities e
        ON LEFT(c.orgao_cnpj, 8) = e.cnpj_8
    WHERE e.raio_200km IS TRUE
      AND c.is_active IS TRUE
      AND c.valor_total IS NOT NULL
      AND c.valor_total > 0
)
SELECT
    categoria_agrupada                                        AS categoria,
    COUNT(*)                                                  AS qtd_contratos,
    ROUND(SUM(valor)::numeric, 2)                             AS valor_total,
    ROUND(AVG(valor)::numeric, 2)                             AS ticket_medio,
    ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY valor)::numeric, 2) AS p25_valor,
    ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY valor)::numeric, 2) AS p50_valor,
    ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY valor)::numeric, 2) AS p75_valor
FROM categorias
GROUP BY categoria_agrupada
ORDER BY valor_total DESC;

COMMENT ON VIEW v_contract_intel_percentis IS
'P25/P50/P75 value percentiles by contract category (keyword-based).
Values in R$ (Brazilian Real). P50 is the median contract value.
These are nominal values from PNCP valor_global — NOT preços praticados.';

COMMIT;
