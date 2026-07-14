-- ============================================================================
-- Migration 040: Coverage Model Expansion (Story 1.5)
-- ============================================================================
-- Expande a tabela coverage_evidence com campos da Secao 9 do plano mestre:
--   - canonical_entity_key, capability, applicability, scope_key
--   - pages_expected, pages_processed, records_expected
--   - freshness_status, checked_at, next_due_at
--   - period_start, period_end (alias funcional para queried_start/queried_end)
--
-- Expande o enum evidence_state com 11 estados de coverage (Secao 9):
--   - pending (novo), running (novo), blocked (novo), stale (novo)
--   - error (mapeado para os estados de erro especificos existentes)
--
-- Cria tabela materializada de aplicabilidade (Task 5)
--
-- Depende de: 024, 025 (coverage_evidence existe), 037 (target_universe_entities existe)
-- Idempotente: Sim (IF NOT EXISTS, DO $$ blocks)
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. Expandir o enum evidence_state com 4 novos estados
-- ============================================================================
-- Estados atuais: success_with_data, success_zero, partial, connection_failed,
--                  auth_failed, parse_failed, transform_failed, persist_failed,
--                  not_applicable, not_investigated
-- Novos estados:  pending, running, blocked, stale
-- Mapeamento:     "error" e o nome generico; os estados especificos existentes
--                 (connection_failed, auth_failed, etc.) continuam valendo.

-- PostgreSQL nao permite ALTER ENUM ADD VALUE dentro de uma transacao que
-- tambem faz outras operacoes. Usamos DO $$ blocks para cada ADD VALUE.
-- Cada um e uma transacao implicita separada (via DO).

DO $$ BEGIN
    ALTER TYPE evidence_state ADD VALUE IF NOT EXISTS 'pending' BEFORE 'running';
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TYPE evidence_state ADD VALUE IF NOT EXISTS 'running' BEFORE 'success_with_data';
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TYPE evidence_state ADD VALUE IF NOT EXISTS 'blocked' AFTER 'persist_failed';
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TYPE evidence_state ADD VALUE IF NOT EXISTS 'stale' AFTER 'blocked';
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================================================
-- 2. Adicionar novas colunas a coverage_evidence (Secao 9)
-- ============================================================================

-- canonical_entity_key: ligacao com o universo canonico (target_universe_entities)
ALTER TABLE coverage_evidence
    ADD COLUMN IF NOT EXISTS canonical_entity_key TEXT;

COMMENT ON COLUMN coverage_evidence.canonical_entity_key IS
    'Stable entity identity key linking to target_universe_entities.canonical_entity_key. Story 1.5';

-- capability: qual capacidade de negocio esta sendo medida
ALTER TABLE coverage_evidence
    ADD COLUMN IF NOT EXISTS capability TEXT;

COMMENT ON COLUMN coverage_evidence.capability IS
    'Capacidade: open_tenders|historical_contracts|competitors|prices|entity_matching|coverage_truth|source_health. Story 1.5';

-- applicability: se o par (ente x fonte x capacidade) e aplicavel
ALTER TABLE coverage_evidence
    ADD COLUMN IF NOT EXISTS applicability TEXT;

COMMENT ON COLUMN coverage_evidence.applicability IS
    'Decisao de aplicabilidade: applicable|not_applicable|unknown. Story 1.5';

-- applicability_reason: justificativa para a decisao de aplicabilidade
ALTER TABLE coverage_evidence
    ADD COLUMN IF NOT EXISTS applicability_reason TEXT;

COMMENT ON COLUMN coverage_evidence.applicability_reason IS
    'Justificativa para a decisao de aplicabilidade (ex: fonte federal so para entes PNCP). Story 1.5';

-- scope_key: escopo da execucao (ex: "SC_90d", "BR_2024")
ALTER TABLE coverage_evidence
    ADD COLUMN IF NOT EXISTS scope_key TEXT;

COMMENT ON COLUMN coverage_evidence.scope_key IS
    'Chave do escopo de execucao (ex: SC_90d, BR_2024_full). Story 1.5';

-- pages_expected: numero de paginas esperadas para paginacao completa
ALTER TABLE coverage_evidence
    ADD COLUMN IF NOT EXISTS pages_expected INT;

COMMENT ON COLUMN coverage_evidence.pages_expected IS
    'Numero de paginas esperadas para paginacao completa. Story 1.5';

-- pages_processed: numero de paginas efetivamente processadas
ALTER TABLE coverage_evidence
    ADD COLUMN IF NOT EXISTS pages_processed INT;

COMMENT ON COLUMN coverage_evidence.pages_processed IS
    'Numero de paginas efetivamente processadas. Story 1.5';

-- records_expected: numero de registros esperados (total estimado)
ALTER TABLE coverage_evidence
    ADD COLUMN IF NOT EXISTS records_expected INT;

COMMENT ON COLUMN coverage_evidence.records_expected IS
    'Numero de registros esperados (total estimado antes da execucao). Story 1.5';

-- freshness_status: estado de atualizacao dos dados
ALTER TABLE coverage_evidence
    ADD COLUMN IF NOT EXISTS freshness_status TEXT;

COMMENT ON COLUMN coverage_evidence.freshness_status IS
    'Estado de atualizacao: fresh|stale|unknown|overdue. Story 1.5';

-- checked_at: quando a verificacao foi feita
ALTER TABLE coverage_evidence
    ADD COLUMN IF NOT EXISTS checked_at TIMESTAMPTZ;

COMMENT ON COLUMN coverage_evidence.checked_at IS
    'Momento exato da verificacao de cobertura. Story 1.5';

-- next_due_at: quando a proxima verificacao deve ocorrer
ALTER TABLE coverage_evidence
    ADD COLUMN IF NOT EXISTS next_due_at TIMESTAMPTZ;

COMMENT ON COLUMN coverage_evidence.next_due_at IS
    'Prazo para a proxima verificacao. Story 1.5';

-- period_start / period_end: alias funcional para queried_start / queried_end
-- (as colunas ja existem como queried_start e queried_end)
-- Criamos uma view de compatibilidade em vez de renomear colunas existentes.

-- ============================================================================
-- 3. Indices para as novas colunas
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_ce_capability
    ON coverage_evidence (capability)
    WHERE capability IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ce_applicability
    ON coverage_evidence (applicability, source, entity_id)
    WHERE applicability IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ce_freshness
    ON coverage_evidence (freshness_status, next_due_at)
    WHERE freshness_status IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ce_canonical_key
    ON coverage_evidence (canonical_entity_key)
    WHERE canonical_entity_key IS NOT NULL;

-- ============================================================================
-- 4. View de compatibilidade: coverage_evidence com nomenclatura Secao 9
-- ============================================================================

CREATE OR REPLACE VIEW v_coverage_evidence_expanded AS
SELECT
    id,
    entity_id,
    canonical_entity_key,
    capability,
    source,
    data_type,
    applicability,
    applicability_reason,
    scope_key,
    -- Compatibilidade: period_start = queried_start, period_end = queried_end
    queried_start       AS period_start,
    queried_end         AS period_end,
    run_id              AS source_run_id,
    state,
    -- Mapeamento de contagens
    count_obtained      AS records_fetched,
    count_transformed   AS records_transformed,
    count_persisted     AS records_persisted,
    records_expected,
    pages_expected,
    pages_processed,
    -- Freshness
    freshness_status,
    checked_at,
    next_due_at,
    -- Erros
    error_code,
    error_message,
    -- Metadata
    metadata            AS evidence_metadata,
    started_at,
    completed_at
FROM coverage_evidence;

COMMENT ON VIEW v_coverage_evidence_expanded IS
    'Coverage evidence com nomenclatura expandida da Secao 9. Story 1.5. '
    'Compativel com o schema antigo: todas as colunas originais continuam existindo na tabela base.';

-- ============================================================================
-- 5. Tabela materializada de aplicabilidade (Task 5)
-- ============================================================================
-- Regras de decisao:
--   - Fontes federais (PNCP, ComprasGov): aplicaveis a entes com esfera federal OU
--     entes municipais que aderem voluntariamente ao PNCP
--   - Fontes estaduais (TCE-SC, DOE-SC, SC Compras): aplicaveis a entes de SC
--   - Fontes municipais (DOM-SC, CIGA CKAN): aplicaveis a entes municipais de SC
--   - PCP: multiplataforma, aplicavel amplamente
--   - Transparencia: aplicavel a entes com portal de transparencia
-- ============================================================================

-- Tabela base para regras de aplicabilidade
CREATE TABLE IF NOT EXISTS source_applicability_rules (
    id                  BIGSERIAL PRIMARY KEY,
    source              TEXT NOT NULL,
    -- Filtros de decisao
    esfera_filter       TEXT,       -- federal|estadual|municipal|* (todos)
    natureza_filter     TEXT,       -- pref|cam|gov|aut|* (todos)
    plataforma_filter   TEXT,       -- pncp_aderente|* (todos)
    municipio_filter    TEXT,       -- regex ou * (todos)
    -- Resultado
    is_applicable       BOOLEAN NOT NULL DEFAULT TRUE,
    reason              TEXT NOT NULL DEFAULT '',
    priority            INT NOT NULL DEFAULT 0, -- maior = maior prioridade
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_applicability_rule UNIQUE (source, esfera_filter, natureza_filter, plataforma_filter)
);

COMMENT ON TABLE source_applicability_rules IS
    'Regras de decisao de aplicabilidade por fonte. Story 1.5';
COMMENT ON COLUMN source_applicability_rules.esfera_filter IS
    'Filtro por esfera: federal|estadual|municipal|*';
COMMENT ON COLUMN source_applicability_rules.natureza_filter IS
    'Filtro por natureza juridica: pref|cam|gov|aut|*';
COMMENT ON COLUMN source_applicability_rules.plataforma_filter IS
    'Filtro por plataforma: pncp_aderente|*';

-- Seed rules (valores iniciais, serao refinados em P0-06 a P0-09)
INSERT INTO source_applicability_rules (source, esfera_filter, natureza_filter, is_applicable, reason, priority) VALUES
    -- PNCP: todas as esferas, todas as naturezas (adesao voluntaria)
    ('pncp',           '*', '*', TRUE,  'Fonte federal com adesao voluntaria de todas as esferas', 0),
    -- ComprasGov: todas as esferas, todas as naturezas
    ('compras_gov',    '*', '*', TRUE,  'Compras federais com adesao multiesfera', 0),
    -- DOM-SC: apenas municipios de SC
    ('dom_sc',         'municipal', '*', TRUE,  'Diario oficial dos municipios de SC', 10),
    ('dom_sc',         'estadual',  '*', FALSE, 'DOM-SC nao cobre entes estaduais', 10),
    ('dom_sc',         'federal',   '*', FALSE, 'DOM-SC nao cobre entes federais', 10),
    -- PCP: multiplataforma
    ('pcp',            '*', '*', TRUE,  'Portal de Compras Publicas — multiplataforma', 0),
    -- SC Compras: apenas entes de SC
    ('sc_compras',     '*', '*', TRUE,  'Plataforma estadual SC', 0),
    -- TCE-SC: apenas entes de SC
    ('tce_sc',         '*', '*', TRUE,  'Tribunal de Contas de SC', 0),
    -- DOE-SC: apenas entes estaduais de SC
    ('doe_sc',         'estadual', '*', TRUE,  'Diario oficial estadual de SC', 10),
    ('doe_sc',         'municipal', '*', FALSE, 'DOE-SC nao cobre entes municipais diretamente', 10),
    ('doe_sc',         'federal',   '*', FALSE, 'DOE-SC nao cobre entes federais', 10),
    -- Transparencia: entes com portal verificavel
    ('transparencia',  '*', '*', TRUE,  'Portal da transparencia — aplicavel quando portal existe', 0),
    -- CIGA CKAN: municipios de SC
    ('ciga_ckan',      'municipal', '*', TRUE,  'CIGA CKAN — dados municipais de SC', 10),
    ('ciga_ckan',      'estadual',  '*', FALSE, 'CIGA CKAN nao cobre entes estaduais', 10),
    ('ciga_ckan',      'federal',   '*', FALSE, 'CIGA CKAN nao cobre entes federais', 10),
    -- MIDES BigQuery: entes estaduais de SC
    ('mides_bigquery', 'estadual',  '*', TRUE,  'MIDES BigQuery — dados estaduais', 10),
    ('mides_bigquery', 'municipal', '*', FALSE, 'MIDES BigQuery nao cobre entes municipais', 10),
    ('mides_bigquery', 'federal',   '*', FALSE, 'MIDES BigQuery nao cobre entes federais', 10)
ON CONFLICT (source, esfera_filter, natureza_filter, plataforma_filter) DO NOTHING;

-- Trigger de updated_at
CREATE OR REPLACE FUNCTION fn_applicability_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_applicability_updated_at') THEN
        CREATE TRIGGER trg_applicability_updated_at
            BEFORE UPDATE ON source_applicability_rules
            FOR EACH ROW
            EXECUTE FUNCTION fn_applicability_updated_at();
    END IF;
END $$;

-- ============================================================================
-- 6. View materializada: aplicabilidade por (ente, source)
-- ============================================================================
-- Para cada ente ativo x fonte, decide se e aplicavel com base nas regras.
-- Usa a visao canonica v_entities_canonical (migration 030).
-- ============================================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_entity_source_applicability AS
WITH
-- Fontes ativas do registry (expanded list)
sources(source) AS (
    VALUES
        ('pncp'),
        ('dom_sc'),
        ('pcp'),
        ('compras_gov'),
        ('sc_compras'),
        ('transparencia'),
        ('tce_sc'),
        ('doe_sc'),
        ('ciga_ckan'),
        ('mides_bigquery')
),
-- Decisao por regra: para cada (ente, source), pega a regra de maior prioridade
entity_rules AS (
    SELECT
        e.entity_id,
        s.source,
        -- Determina esfera
        CASE
            WHEN e.natureza_juridica LIKE '%FEDERAL%' OR e.cod_natureza LIKE '1%' THEN 'federal'
            WHEN e.natureza_juridica LIKE '%ESTADUAL%' OR e.cod_natureza LIKE '2%' THEN 'estadual'
            ELSE 'municipal'
        END AS esfera,
        -- Determina natureza simplificada
        CASE
            WHEN e.natureza_juridica LIKE '%PREFEITURA%' OR e.cod_natureza LIKE '1%' THEN 'pref'
            WHEN e.natureza_juridica LIKE '%CAMARA%' OR e.cod_natureza LIKE '12%' THEN 'cam'
            WHEN e.natureza_juridica LIKE '%GOVERNO%' OR e.cod_natureza LIKE '10%' THEN 'gov'
            WHEN e.natureza_juridica LIKE '%AUTARQUIA%' OR e.cod_natureza LIKE '2%' THEN 'aut'
            ELSE 'outro'
        END AS natureza_simplificada
    FROM v_entities_canonical e
    CROSS JOIN sources s
    WHERE e.is_active = TRUE
)
SELECT
    er.entity_id,
    er.source,
    er.esfera,
    er.natureza_simplificada AS natureza,
    COALESCE(MAX(r.priority), 0) AS rule_priority,
    BOOL_OR(r.is_applicable) AS is_applicable,
    -- Pega a razao da regra de maior prioridade que se aplica
    (
        SELECT r2.reason
        FROM source_applicability_rules r2
        WHERE r2.source = er.source
          AND (r2.esfera_filter = '*' OR r2.esfera_filter = er.esfera)
          AND (r2.natureza_filter = '*' OR r2.natureza_filter = er.natureza_simplificada)
          AND r2.is_active = TRUE
        ORDER BY r2.priority DESC
        LIMIT 1
    ) AS reason,
    NOW() AS calculated_at
FROM entity_rules er
LEFT JOIN source_applicability_rules r
    ON r.source = er.source
    AND r.is_active = TRUE
    AND (r.esfera_filter = '*' OR r.esfera_filter = er.esfera)
    AND (r.natureza_filter = '*' OR r.natureza_filter = er.natureza_simplificada)
GROUP BY er.entity_id, er.source, er.esfera, er.natureza_simplificada
ORDER BY er.entity_id, er.source;

COMMENT ON MATERIALIZED VIEW mv_entity_source_applicability IS
    'Aplicabilidade materializada por (ente, source). Atualizar via REFRESH MATERIALIZED VIEW. Story 1.5';

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_applicability_entity_source
    ON mv_entity_source_applicability (entity_id, source);

CREATE INDEX IF NOT EXISTS idx_mv_applicability_source
    ON mv_entity_source_applicability (source, is_applicable);

-- ============================================================================
-- 7. View de cobertura por capacidade (coverage manifest)
-- ============================================================================

CREATE OR REPLACE VIEW v_coverage_manifest AS
SELECT
    COALESCE(ce.capability, 'open_tenders') AS capability,
    ce.source,
    COUNT(*) FILTER (WHERE ce.entity_id IS NOT NULL) AS total_entity_pairs,
    COUNT(*) FILTER (WHERE ce.entity_id IS NOT NULL AND ce.state IN ('success_with_data', 'success_zero')) AS covered_pairs,
    COUNT(*) FILTER (WHERE ce.entity_id IS NOT NULL AND ce.state = 'success_with_data') AS with_data,
    COUNT(*) FILTER (WHERE ce.entity_id IS NOT NULL AND ce.state = 'success_zero') AS zero_data,
    COUNT(*) FILTER (WHERE ce.entity_id IS NOT NULL AND ce.state = 'partial') AS partial,
    COUNT(*) FILTER (WHERE ce.entity_id IS NOT NULL AND ce.state IN ('pending', 'running')) AS in_progress,
    COUNT(*) FILTER (WHERE ce.entity_id IS NOT NULL AND ce.state = 'blocked') AS blocked,
    COUNT(*) FILTER (WHERE ce.entity_id IS NOT NULL AND ce.state = 'stale') AS stale,
    COUNT(*) FILTER (WHERE ce.entity_id IS NOT NULL AND ce.state LIKE '%failed') AS errored,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE ce.entity_id IS NOT NULL AND ce.state IN ('success_with_data', 'success_zero'))
        / GREATEST(COUNT(*) FILTER (WHERE ce.entity_id IS NOT NULL), 1), 1
    ) AS pct_covered,
    MAX(ce.completed_at) AS last_check_at
FROM coverage_evidence ce
WHERE ce.entity_id IS NOT NULL
GROUP BY ce.capability, ce.source
ORDER BY ce.capability, ce.source;

COMMENT ON VIEW v_coverage_manifest IS
    'Coverage manifest por capacidade e fonte. Story 1.5. '
    'Metricas independentes: data presence nao altera coverage (success_zero conta como covered).';

-- ============================================================================
-- Rollback
-- ============================================================================
-- DROP VIEW IF EXISTS v_coverage_manifest;
-- DROP MATERIALIZED VIEW IF EXISTS mv_entity_source_applicability;
-- DROP TRIGGER IF EXISTS trg_applicability_updated_at ON source_applicability_rules;
-- DROP FUNCTION IF EXISTS fn_applicability_updated_at;
-- DROP TABLE IF EXISTS source_applicability_rules;
-- DROP VIEW IF EXISTS v_coverage_evidence_expanded;
-- ALTER TABLE coverage_evidence DROP COLUMN IF EXISTS canonical_entity_key;
-- ALTER TABLE coverage_evidence DROP COLUMN IF EXISTS capability;
-- ALTER TABLE coverage_evidence DROP COLUMN IF EXISTS applicability;
-- ALTER TABLE coverage_evidence DROP COLUMN IF EXISTS applicability_reason;
-- ALTER TABLE coverage_evidence DROP COLUMN IF EXISTS scope_key;
-- ALTER TABLE coverage_evidence DROP COLUMN IF EXISTS pages_expected;
-- ALTER TABLE coverage_evidence DROP COLUMN IF EXISTS pages_processed;
-- ALTER TABLE coverage_evidence DROP COLUMN IF EXISTS records_expected;
-- ALTER TABLE coverage_evidence DROP COLUMN IF EXISTS freshness_status;
-- ALTER TABLE coverage_evidence DROP COLUMN IF EXISTS checked_at;
-- ALTER TABLE coverage_evidence DROP COLUMN IF EXISTS next_due_at;

COMMIT;
