-- Migration 021: Entity hierarchy table for hierarchical matching
-- Story COVERAGE-1.8: Match Hierarquico Secretaria → Prefeitura
--
-- Cria tabela entity_hierarchy para vincular entidades municipais
-- (secretarias, fundacoes, autarquias, fundos) as respectivas prefeituras,
-- permitindo que entes sem match direto herdem cobertura da prefeitura.
--
-- Dependencias: Migration 007 (sc_public_entities)
--               Migration 009 (entity_coverage)

-- ============================================================
-- 1. entity_hierarchy — mapeamento hierarquico por municipio
-- ============================================================
CREATE TABLE IF NOT EXISTS entity_hierarchy (
    entity_id           INTEGER PRIMARY KEY REFERENCES sc_public_entities(id),
    parent_entity_id    INTEGER NOT NULL REFERENCES sc_public_entities(id),
    relationship        VARCHAR(32) NOT NULL CHECK (relationship IN (
                            'prefeitura', 'camara', 'autarquia',
                            'fundacao', 'fundo', 'conselho', 'outros'
                        )),
    match_confidence    VARCHAR(16) NOT NULL CHECK (match_confidence IN (
                            'direct', 'hierarchical', 'inferred'
                        )),
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON TABLE entity_hierarchy IS
    'Mapeamento hierarquico de entidades municipais para suas respectivas prefeituras — Story COVERAGE-1.8';

COMMENT ON COLUMN entity_hierarchy.entity_id IS
    'ID da entidade filha (secretaria, fundacao, autarquia, etc.)';
COMMENT ON COLUMN entity_hierarchy.parent_entity_id IS
    'ID da entidade pai (prefeitura/municipio)';
COMMENT ON COLUMN entity_hierarchy.relationship IS
    'Tipo de relacao: prefeitura | camara | autarquia | fundacao | fundo | conselho | outros';
COMMENT ON COLUMN entity_hierarchy.match_confidence IS
    'Confianca do vinculo: direct | hierarchical | inferred';

-- Index para buscas por parent (prefeitura)
CREATE INDEX IF NOT EXISTS idx_entity_hierarchy_parent
    ON entity_hierarchy(parent_entity_id);

-- Index para buscas por relationship
CREATE INDEX IF NOT EXISTS idx_entity_hierarchy_relationship
    ON entity_hierarchy(relationship);

-- Index composto para cobertura hierarquica
CREATE INDEX IF NOT EXISTS idx_entity_hierarchy_coverage
    ON entity_hierarchy(entity_id, parent_entity_id)
    INCLUDE (relationship);

-- ============================================================
-- 2. Funcao para atualizar updated_at automaticamente
-- ============================================================
CREATE OR REPLACE FUNCTION update_entity_hierarchy_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_entity_hierarchy_timestamp
    BEFORE UPDATE ON entity_hierarchy
    FOR EACH ROW
    EXECUTE FUNCTION update_entity_hierarchy_timestamp();

-- ============================================================
-- 3. View para cobertura hierarquica (entes com cobertura herdada)
-- ============================================================
CREATE OR REPLACE VIEW v_hierarchical_coverage AS
SELECT
    e.id AS entity_id,
    e.razao_social,
    e.municipio,
    e.natureza_juridica,
    h.relationship,
    h.parent_entity_id,
    p.razao_social AS parent_razao_social,
    pec.is_covered AS parent_covered,
    pec.total_bids AS parent_total_bids,
    ec.is_covered AS direct_covered
FROM sc_public_entities e
JOIN entity_hierarchy h ON h.entity_id = e.id
JOIN sc_public_entities p ON p.id = h.parent_entity_id
LEFT JOIN entity_coverage ec ON ec.entity_id = e.id AND ec.source = 'pncp'
LEFT JOIN entity_coverage pec ON pec.entity_id = h.parent_entity_id AND pec.source = 'pncp'
WHERE e.is_active = TRUE;

COMMENT ON VIEW v_hierarchical_coverage IS
    'Visao consolidada da cobertura hierarquica — Story COVERAGE-1.8';
