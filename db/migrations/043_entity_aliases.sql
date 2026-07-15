-- 043_entity_aliases: tabela de hierarquia de CNPJs para resolução de aliases
-- Objetivo: mapear ente subordinate (secretaria, autarquia, fundação, câmara)
--           → ente publicante (prefeitura) dentro do mesmo município.
-- Story: CM-13 — Deduplicação Multicanal e Aliases de Compradores

BEGIN;

-- Tabela principal de aliases
CREATE TABLE IF NOT EXISTS entity_aliases (
    id              SERIAL PRIMARY KEY,
    cnpj_8_sub      TEXT NOT NULL,              -- CNPJ raiz do ente subordinate (ex: secretaria)
    cnpj_8_pub      TEXT NOT NULL,              -- CNPJ raiz do ente publicante (ex: prefeitura)
    alias_type      TEXT NOT NULL DEFAULT 'municipio_parent',  -- municipio_parent, manual, detected
    source_entity   TEXT,                        -- razao_social do ente subordinate
    target_entity   TEXT,                        -- razao_social do ente publicante
    municipio       TEXT,                        -- municipio compartilhado
    codigo_ibge     TEXT,                        -- código IBGE do municipio
    confidence      TEXT NOT NULL DEFAULT 'high', -- high, medium, low, manual
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Uma entidade subordinate só pode ter UM publicante ativo
    CONSTRAINT uq_entity_aliases_sub UNIQUE (cnpj_8_sub, is_active),
    -- Garantia de não-circularidade
    CONSTRAINT chk_no_self_alias CHECK (cnpj_8_sub <> cnpj_8_pub)
);

-- Índices para lookup rápido
CREATE INDEX IF NOT EXISTS idx_entity_aliases_sub ON entity_aliases (cnpj_8_sub) WHERE is_active;
CREATE INDEX IF NOT EXISTS idx_entity_aliases_pub ON entity_aliases (cnpj_8_pub) WHERE is_active;
CREATE INDEX IF NOT EXISTS idx_entity_aliases_municipio ON entity_aliases (municipio);
CREATE INDEX IF NOT EXISTS idx_entity_aliases_type ON entity_aliases (alias_type);

-- View para resolução: dado um CNPJ, retorna o CNPJ publicante (ou ele mesmo)
CREATE OR REPLACE VIEW v_resolve_publishing_cnpj AS
SELECT
    e.cnpj_8 AS original_cnpj,
    COALESCE(a.cnpj_8_pub, e.cnpj_8) AS publishing_cnpj,
    CASE WHEN a.cnpj_8_pub IS NOT NULL THEN TRUE ELSE FALSE END AS is_aliased,
    a.alias_type,
    a.source_entity,
    a.target_entity,
    a.municipio
FROM sc_public_entities e
LEFT JOIN entity_aliases a
    ON e.cnpj_8 = a.cnpj_8_sub
    AND a.is_active = TRUE;

-- Tabela de dedup cross-source
CREATE TABLE IF NOT EXISTS dedup_cross_source (
    id                  SERIAL PRIMARY KEY,
    canonical_hash      TEXT NOT NULL,            -- sha256 do registro canônico
    opportunity_id      INTEGER NOT NULL,         -- FK para opportunity_intel
    source              TEXT NOT NULL,             -- fonte original (pncp, compras_gov, etc.)
    source_id           TEXT,                      -- ID na fonte original
    is_canonical        BOOLEAN NOT NULL DEFAULT FALSE,  -- registro primário do grupo
    dedup_group_id      TEXT NOT NULL,             -- UUID do grupo de dedup
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_dedup_opportunity UNIQUE (opportunity_id)
);

CREATE INDEX IF NOT EXISTS idx_dedup_hash ON dedup_cross_source (canonical_hash);
CREATE INDEX IF NOT EXISTS idx_dedup_group ON dedup_cross_source (dedup_group_id);
CREATE INDEX IF NOT EXISTS idx_dedup_source ON dedup_cross_source (source);

-- Função SQL para resolver CNPJ (fallback rápido sem Python)
CREATE OR REPLACE FUNCTION resolve_publishing_cnpj_sql(cnpj_8_in TEXT)
RETURNS TEXT AS $$
    SELECT COALESCE(
        (SELECT cnpj_8_pub FROM entity_aliases
         WHERE cnpj_8_sub = cnpj_8_in AND is_active = TRUE),
        cnpj_8_in
    );
$$ LANGUAGE SQL STABLE STRICT;

COMMENT ON TABLE entity_aliases IS 'Hierarquia de CNPJs: ente subordinate → ente publicante (CM-13)';
COMMENT ON TABLE dedup_cross_source IS 'Dedup cross-source com hash canônico (CM-13)';
COMMENT ON VIEW v_resolve_publishing_cnpj IS 'Resolução de CNPJ publicante com fallback para o próprio CNPJ';
COMMENT ON FUNCTION resolve_publishing_cnpj_sql IS 'Resolve CNPJ subordinate → publicante, idempotente';

COMMIT;
