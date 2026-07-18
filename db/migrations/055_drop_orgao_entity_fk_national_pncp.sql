-- Migration 055: Allow national PNCP bids/contracts without SC-universe parent
--
-- Problem: orgao_cnpj_8 is GENERATED ALWAYS AS left(orgao_cnpj, 8) and had a hard
-- FK to sc_public_entities(cnpj_8). National PNCP organs outside the SC universe
-- then fail upsert with fk_bids_orgao_entity_v2, blocking live crawls.
--
-- Fix: drop hard FKs; keep generated columns + indexes for soft joins when the
-- entity exists. Matching remains via matched_entity_id / entity_aliases.

ALTER TABLE public.pncp_raw_bids
    DROP CONSTRAINT IF EXISTS fk_bids_orgao_entity_v2;

ALTER TABLE public.pncp_supplier_contracts
    DROP CONSTRAINT IF EXISTS fk_contracts_orgao_entity_v2;

COMMENT ON COLUMN public.pncp_raw_bids.orgao_cnpj_8 IS
    'Soft key left(orgao_cnpj,8); join to sc_public_entities when present (no hard FK).';

COMMENT ON COLUMN public.pncp_supplier_contracts.orgao_cnpj_8 IS
    'Soft key left(orgao_cnpj,8); join to sc_public_entities when present (no hard FK).';
