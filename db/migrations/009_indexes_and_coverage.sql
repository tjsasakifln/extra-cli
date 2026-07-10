-- Migration 009: Entity coverage tracking + indexes

-- Coverage tracking per entity per source
CREATE TABLE entity_coverage (
    entity_id       INT NOT NULL REFERENCES sc_public_entities(id) ON DELETE CASCADE,
    source          TEXT NOT NULL,                  -- 'pncp'|'dom_sc'|'pcp'|'compras_gov'|'sc_compras'|'tce_sc'|'transparencia'
    last_seen_at    TIMESTAMPTZ,                   -- last time this entity appeared in this source
    total_bids      INT NOT NULL DEFAULT 0,         -- total bids collected from this entity
    is_covered      BOOLEAN NOT NULL DEFAULT FALSE, -- has publications in last 90 days?
    within_200km    BOOLEAN NOT NULL DEFAULT FALSE, -- denormalized from sc_public_entities
    PRIMARY KEY (entity_id, source)
);

-- Fast gap detection queries
CREATE INDEX idx_cov_covered ON entity_coverage (is_covered, within_200km);
CREATE INDEX idx_cov_last_seen ON entity_coverage (last_seen_at);
CREATE INDEX idx_cov_source ON entity_coverage (source, is_covered);

-- Update entity_coverage after bid insert
CREATE OR REPLACE FUNCTION update_entity_coverage()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.matched_entity_id IS NOT NULL THEN
        INSERT INTO entity_coverage (entity_id, source, last_seen_at, total_bids, is_covered, within_200km)
        VALUES (
            NEW.matched_entity_id,
            NEW.source,
            NEW.data_publicacao,
            1,
            NEW.data_publicacao >= CURRENT_DATE - 90,
            (SELECT raio_200km FROM sc_public_entities WHERE id = NEW.matched_entity_id)
        )
        ON CONFLICT (entity_id, source) DO UPDATE
        SET
            last_seen_at = GREATEST(
                entity_coverage.last_seen_at,
                NEW.data_publicacao
            ),
            total_bids = entity_coverage.total_bids + 1,
            is_covered = (
                GREATEST(entity_coverage.last_seen_at, NEW.data_publicacao)
                >= CURRENT_DATE - 90
            );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_bids_coverage
    AFTER INSERT ON pncp_raw_bids
    FOR EACH ROW
    EXECUTE FUNCTION update_entity_coverage();

-- Initialize coverage for all entities (will be populated by triggers)
INSERT INTO entity_coverage (entity_id, source, is_covered, within_200km)
SELECT
    e.id,
    'pncp',
    FALSE,
    e.raio_200km
FROM sc_public_entities e
ON CONFLICT (entity_id, source) DO NOTHING;

INSERT INTO entity_coverage (entity_id, source, is_covered, within_200km)
SELECT
    e.id,
    'dom_sc',
    FALSE,
    e.raio_200km
FROM sc_public_entities e
ON CONFLICT (entity_id, source) DO NOTHING;

INSERT INTO entity_coverage (entity_id, source, is_covered, within_200km)
SELECT
    e.id,
    'pcp',
    FALSE,
    e.raio_200km
FROM sc_public_entities e
ON CONFLICT (entity_id, source) DO NOTHING;

INSERT INTO entity_coverage (entity_id, source, is_covered, within_200km)
SELECT
    e.id,
    'compras_gov',
    FALSE,
    e.raio_200km
FROM sc_public_entities e
ON CONFLICT (entity_id, source) DO NOTHING;

-- Additional performance indexes
CREATE INDEX idx_bids_orgao_hash ON pncp_raw_bids (orgao_cnpj, content_hash);
CREATE INDEX idx_bids_uf_source ON pncp_raw_bids (uf, source, data_publicacao DESC);

-- Verify coverage (utility view)
CREATE OR REPLACE VIEW v_coverage_summary AS
SELECT
    ec.source,
    ec.within_200km,
    ec.is_covered,
    COUNT(*) AS entity_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY ec.within_200km), 1) AS pct
FROM entity_coverage ec
WHERE EXISTS (SELECT 1 FROM sc_public_entities e WHERE e.id = ec.entity_id AND e.is_active = TRUE)
GROUP BY ec.source, ec.within_200km, ec.is_covered
ORDER BY ec.source, ec.within_200km, ec.is_covered;
