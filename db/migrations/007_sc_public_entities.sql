-- Migration 007: SC Public Entities table
-- From spreadsheet "Extra - alvos de licitação. R-0.xlsx"
-- 2,085 public entities in Santa Catarina state

CREATE TABLE sc_public_entities (
    id                  SERIAL PRIMARY KEY,
    razao_social        TEXT NOT NULL,
    cnpj_8              TEXT NOT NULL,              -- 8-digit CNPJ base (raiz)
    municipio           TEXT,
    codigo_ibge         TEXT,                       -- 7-digit IBGE municipality code
    natureza_juridica   TEXT,                       -- legal nature description
    cod_natureza        TEXT,                       -- legal nature code
    latitude            DOUBLE PRECISION,
    longitude           DOUBLE PRECISION,
    distancia_fk        DOUBLE PRECISION,           -- distance from Florianópolis (km)
    raio_200km          BOOLEAN NOT NULL DEFAULT FALSE,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Search indexes
CREATE INDEX idx_spe_cnpj ON sc_public_entities (cnpj_8);
CREATE INDEX idx_spe_municipio ON sc_public_entities (municipio);
CREATE INDEX idx_spe_ibge ON sc_public_entities (codigo_ibge);
CREATE INDEX idx_spe_raio ON sc_public_entities (raio_200km, is_active);
CREATE INDEX idx_spe_natureza ON sc_public_entities (cod_natureza);

-- Foreign key from bids table
ALTER TABLE pncp_raw_bids
    ADD CONSTRAINT fk_bids_matched_entity
    FOREIGN KEY (matched_entity_id)
    REFERENCES sc_public_entities(id)
    ON DELETE SET NULL;
