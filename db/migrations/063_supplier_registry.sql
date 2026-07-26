-- 063_supplier_registry.sql
-- Campaign: CONFENGE-COMMERCIAL-READY-01 (gold standard)
-- Canonical cadastral / CNAE registry for suppliers.
-- Additive only. Does not alter pncp_supplier_contracts.
-- Idempotent: CREATE IF NOT EXISTS.

BEGIN;

CREATE TABLE IF NOT EXISTS public.supplier_registry (
    cnpj14              TEXT PRIMARY KEY,
    razao_social        TEXT,
    nome_fantasia       TEXT,
    cnae_principal      TEXT,
    cnaes_secundarios   JSONB NOT NULL DEFAULT '[]'::jsonb,
    situacao_cadastral  TEXT,
    data_situacao       DATE,
    municipio           TEXT,
    uf                  TEXT,
    source              TEXT NOT NULL,
    source_version      TEXT NOT NULL,
    source_date         DATE NOT NULL,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_supplier_registry_cnae
    ON public.supplier_registry (cnae_principal);

CREATE INDEX IF NOT EXISTS idx_supplier_registry_uf
    ON public.supplier_registry (uf);

COMMENT ON TABLE public.supplier_registry IS
    'Canonical supplier cadastro (CNAE). Never invent rows; missing = NOT_COMPUTABLE.';

COMMIT;
