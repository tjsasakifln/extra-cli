-- Migration 010: Match logging columns for entity name-matching refinement
-- Story 001.3: Entity Name-Matching Refinement
--
-- Adiciona colunas de metadata de matching à pncp_raw_bids para rastrear
-- qual estratégia (CNPJ, nome normalizado, fuzzy) foi usada e qual a
-- confiança do match.
--
-- Uso no monitor.py:
--   _match_entities_cascade() grava estas colunas após cada tentativa de match

-- Add match-method column (which strategy produced the match)
ALTER TABLE pncp_raw_bids
    ADD COLUMN IF NOT EXISTS match_method TEXT;

-- Add match-score column (0.000 = no match, 1.000 = exact)
ALTER TABLE pncp_raw_bids
    ADD COLUMN IF NOT EXISTS match_score DECIMAL(4,3);

-- Add match-confidence column (high, medium, low)
ALTER TABLE pncp_raw_bids
    ADD COLUMN IF NOT EXISTS match_confidence TEXT;

-- Index for analysing match quality / debugging unmatched bids
CREATE INDEX IF NOT EXISTS idx_bids_match_method
    ON pncp_raw_bids (match_method)
    WHERE match_method IS NOT NULL;

-- Composite index for coverage analysis: which methods are producing matches
CREATE INDEX IF NOT EXISTS idx_bids_match_coverage
    ON pncp_raw_bids (match_method, matched_entity_id)
    WHERE matched_entity_id IS NOT NULL;

COMMENT ON COLUMN pncp_raw_bids.match_method IS
    'Estrategia de matching: cnpj | name_normalized | fuzzy | unmatched';
COMMENT ON COLUMN pncp_raw_bids.match_score IS
    'Score do match (0.000-1.000). 1.000 = exact match.';
COMMENT ON COLUMN pncp_raw_bids.match_confidence IS
    'Confianca: high (>=0.95) | medium (>=threshold) | low (<threshold)';
