-- 095_canonical_arp_atas.sql
-- #250: local PostgreSQL is the metadata authority for ARP/IRP (not Supabase RPC).

BEGIN;

CREATE TABLE IF NOT EXISTS public.canonical_arp_atas (
    official_id       TEXT PRIMARY KEY,
    source            TEXT NOT NULL DEFAULT 'pncp_arp',
    pncp_id_origem    TEXT,
    orgao_cnpj        TEXT,
    orgao_nome        TEXT,
    objeto            TEXT,
    status            TEXT,
    vigencia_inicio   DATE,
    vigencia_fim      DATE,
    itens             JSONB NOT NULL DEFAULT '[]'::jsonb,
    fornecedores      JSONB NOT NULL DEFAULT '[]'::jsonb,
    documentos        JSONB NOT NULL DEFAULT '[]'::jsonb,
    raw_hash          TEXT NOT NULL,
    content_hash      TEXT NOT NULL,
    previous_hash     TEXT,
    persisted_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_canonical_arp_atas_orgao
    ON public.canonical_arp_atas (orgao_cnpj);

COMMENT ON TABLE public.canonical_arp_atas IS
    'ARP/IRP official identity in the local lake. PostgreSQL is the metadata authority.';

COMMIT;
