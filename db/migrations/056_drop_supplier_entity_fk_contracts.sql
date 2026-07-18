-- Migration 056: Drop hard FK supplier→sc_public_entities on contracts
--
-- National PNCP contracts include suppliers not in the SC entity universe.
-- fornecedor_cnpj_8 is a soft join key (generated left 8), not a universe member.

ALTER TABLE public.pncp_supplier_contracts
    DROP CONSTRAINT IF EXISTS fk_contracts_supplier_entity_v2;

COMMENT ON COLUMN public.pncp_supplier_contracts.fornecedor_cnpj_8 IS
    'Soft key left(fornecedor_cnpj,8); not a hard FK to sc_public_entities.';
