-- Migration 025: Contract Intelligence Analytical Views
-- Canonical SQL views for the Contract Intelligence vertical slice.
--
-- Provides:
--   1. v_contract_intel_historico    — Historical contracts for target universe
--   2. v_contract_intel_fornecedores  — Supplier/competitor analytics
--   3. v_contract_intel_ativos_90_180 — Active contracts ending in 90–180 days
--   4. v_contract_intel_percentis     — P25/P50/P75 value/ticket by category
--
-- Design constraints:
--   - Idempotent: all CREATE use IF NOT EXISTS / OR REPLACE.
--   - Never invents metrics (deságio, win rate, etc.) without data.
--   - "Valor global de contrato" is NOT called "preço praticado".
--   - Percentiles use PERCENTILE_CONT (SQL standard, not approximations).
--   - All views are read-only analytical layers over pncp_supplier_contracts.
--
-- IMPORTANT: These views require the target universe table (sc_public_entities
-- with raio_200km flag populated) and pncp_supplier_contracts populated.
-- If tables are empty, views return zero rows — not an error.

BEGIN;

-- ---------------------------------------------------------------------------
-- View 1: Historical contracts for target universe entities
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_contract_intel_historico AS
SELECT
    c.contrato_id,
    c.orgao_cnpj,
    c.orgao_nome,
    c.fornecedor_cnpj,
    c.fornecedor_nome,
    c.objeto_contrato,
    c.valor_total,
    c.data_inicio,
    c.data_fim,
    c.data_publicacao,
    c.uf,
    c.municipio,
    e.razao_social AS ente_razao_social,
    e.municipio AS ente_municipio,
    e.distancia_fk AS ente_distancia_km,
    e.raio_200km,
    c.ingested_at
FROM pncp_supplier_contracts c
JOIN sc_public_entities e
    ON c.orgao_cnpj LIKE e.cnpj_8 || '%'
WHERE e.raio_200km IS TRUE
   OR e.distancia_fk <= 200.0;

COMMENT ON VIEW v_contract_intel_historico IS
'Historical contracts for public entities within 200 km of Florianópolis.';

-- ---------------------------------------------------------------------------
-- View 2: Supplier/competitor analytics by quantity, value, concentration
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_contract_intel_fornecedores AS
WITH fornecedor_orgao_agg AS (
    -- Aggregate contract values per supplier per agency first
    SELECT
        c.fornecedor_cnpj,
        c.fornecedor_nome,
        c.orgao_cnpj,
        c.orgao_nome,
        SUM(COALESCE(c.valor_total, 0)) AS valor_orgao,
        COUNT(*) AS qtd_contratos_orgao
    FROM pncp_supplier_contracts c
    JOIN sc_public_entities e
        ON c.orgao_cnpj LIKE e.cnpj_8 || '%'
    WHERE (e.raio_200km IS TRUE OR e.distancia_fk <= 200.0)
      AND c.fornecedor_cnpj IS NOT NULL
      AND c.fornecedor_cnpj != ''
    GROUP BY c.fornecedor_cnpj, c.fornecedor_nome, c.orgao_cnpj, c.orgao_nome
),
fornecedor_totals AS (
    SELECT
        fornecedor_cnpj,
        fornecedor_nome,
        SUM(qtd_contratos_orgao)                                               AS qtd_contratos,
        SUM(valor_orgao)                                                       AS valor_total_contratos,
        ROUND(AVG(valor_orgao), 2)                                             AS valor_medio_contrato,
        COUNT(DISTINCT orgao_cnpj)                                             AS qtd_orgaos_distintos,
        STRING_AGG(DISTINCT orgao_nome, '; ' ORDER BY orgao_nome)              AS orgaos_lista
    FROM fornecedor_orgao_agg
    GROUP BY fornecedor_cnpj, fornecedor_nome
),
fornecedor_hhi AS (
    -- B2G-FIX-04: HHI computed in separate CTE (cannot nest window function inside aggregate)
    SELECT
        fo.fornecedor_cnpj,
        ROUND(
            SUM(POWER(
                fo.valor_orgao * 1.0 / NULLIF(ft.valor_total_contratos, 0), 2
            )) * 10000,
            0
        )                                                                       AS hhi_concentracao
    FROM fornecedor_orgao_agg fo
    JOIN fornecedor_totals ft ON fo.fornecedor_cnpj = ft.fornecedor_cnpj
    GROUP BY fo.fornecedor_cnpj
)
SELECT
    ft.fornecedor_cnpj,
    ft.fornecedor_nome,
    ft.qtd_contratos,
    ft.valor_total_contratos,
    ft.valor_medio_contrato,
    ft.qtd_orgaos_distintos,
    COALESCE(fh.hhi_concentracao, 0)                                            AS hhi_concentracao,
    ft.orgaos_lista
FROM fornecedor_totals ft
LEFT JOIN fornecedor_hhi fh ON ft.fornecedor_cnpj = fh.fornecedor_cnpj
ORDER BY valor_total_contratos DESC;

COMMENT ON VIEW v_contract_intel_fornecedores IS
'Supplier analytics: count, total value, average, distinct agencies, concentration (HHI).';

-- ---------------------------------------------------------------------------
-- View 3: Active contracts ending in 90–180 days
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_contract_intel_ativos_90_180 AS
SELECT
    c.contrato_id,
    c.orgao_cnpj,
    c.orgao_nome,
    c.fornecedor_cnpj,
    c.fornecedor_nome,
    c.objeto_contrato,
    c.valor_total,
    c.data_inicio,
    c.data_fim,
    (c.data_fim::date - CURRENT_DATE)                                          AS dias_ate_fim,
    c.uf,
    c.municipio,
    e.razao_social AS ente_razao_social
FROM pncp_supplier_contracts c
JOIN sc_public_entities e
    ON c.orgao_cnpj LIKE e.cnpj_8 || '%'
WHERE (e.raio_200km IS TRUE OR e.distancia_fk <= 200.0)
  AND c.data_fim IS NOT NULL
  AND c.data_fim::date BETWEEN (CURRENT_DATE + INTERVAL '90 days')
                           AND (CURRENT_DATE + INTERVAL '180 days')
ORDER BY c.data_fim, c.valor_total DESC;

COMMENT ON VIEW v_contract_intel_ativos_90_180 IS
'Active contracts ending between 90 and 180 days from today (renewal window).';

-- ---------------------------------------------------------------------------
-- View 4: P25/P50/P75 value/ticket percentiles by contract category
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_contract_intel_percentis AS
WITH categorias AS (
    SELECT
        COALESCE(c.objeto_contrato, 'NÃO CLASSIFICADO')                        AS categoria,
        c.valor_total                                                           AS valor,
        -- Simple keyword-based category extraction (extensible)
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
        END                                                                     AS categoria_agrupada
    FROM pncp_supplier_contracts c
    JOIN sc_public_entities e
        ON c.orgao_cnpj LIKE e.cnpj_8 || '%'
    WHERE (e.raio_200km IS TRUE OR e.distancia_fk <= 200.0)
      AND c.valor_total IS NOT NULL
      AND c.valor_total > 0
)
SELECT
    categoria_agrupada                                                                                 AS categoria,
    COUNT(*)                                                                                           AS qtd_contratos,
    ROUND(SUM(valor)::numeric, 2)                                                                      AS valor_total,
    ROUND(AVG(valor)::numeric, 2)                                                                      AS ticket_medio,
    ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY valor)::numeric, 2)                             AS p25_valor,
    ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY valor)::numeric, 2)                             AS p50_valor,
    ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY valor)::numeric, 2)                             AS p75_valor,
    ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY valor)::numeric, 2)                             AS p25_ticket,
    ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY valor)::numeric, 2)                             AS p50_ticket,
    ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY valor)::numeric, 2)                             AS p75_ticket
FROM categorias
GROUP BY categoria_agrupada
ORDER BY valor_total DESC;

COMMENT ON VIEW v_contract_intel_percentis IS
'P25/P50/P75 value and ticket percentiles by contract category.
Values are in R$ (Brazilian Real). P50 is the median contract value.
These are NOT "preços praticados" — they are nominal values from PNCP.';

COMMIT;
