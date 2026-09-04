-- equivalence_seed.sql — semente DETERMINISTICA do banco isolado extra_li_equiv.
--
-- Story: docs/stories/story-confenge-live-intelligence-w2-web-export.md (AC6, AC10)
-- Dono:  scripts/ops/li_equiv_db.py (Task 10). NAO e migration e nunca roda em
--        extra_test nem em producao — o guarda fail-closed do script impede.
--
-- O que a semente precisa exercitar, por exigencia da story:
--   1. RAIZ + FILIAL do MESMO CNPJ-8 (11222333000181 / 11222333000262), para que
--      §B.3 produza N company_digest a partir de uma unica company_root8.
--   2. Ao menos um `buyer_cnpj` com != 14 digitos ('123456'), para exercitar o
--      caminho fail-closed do AC6: comprador OMITIDO de `compradores`,
--      `manifest.coverage.buyers_unhashable` incrementado e reason code interno
--      `buyer_cnpj_not_hashable` emitido. `producer.py` extrai `buyer_cnpj` SEM
--      validar comprimento, logo este caminho e real, nao hipotetico.
--   2b. `supplier_id_type`/`supplier_identifier` sao OBRIGATORIOS: o CHECK
--      `ck_contract_supplier_identity_consistent` exige a tripla coerente e o
--      digito verificador real (`fn_contract_valid_cnpj`). Os dois CNPJ acima
--      tem DV valido — nao sao numeros arbitrarios.
--   3. Um edital aberto em `pncp_raw_bids`, que e tambem a origem do watermark
--      (`fetch_source_watermark` le MAX(updated_at) dessa tabela). Sem ele o
--      build fecharia BLOCKED e a prova de equivalencia seria vacua.
--   3b. O `pncp_id` do edital usa DELIBERADAMENTE o prefixo `LI-TEST-` de
--      `tests/confenge_live_intelligence/conftest.py:SEED_PREFIX`. Motivo (AC10):
--      `test_blocked_when_watermark_is_missing` apaga exatamente
--      `pncp_id LIKE 'LI-TEST-%'` e o AC10 proibe AMPLIAR esse escopo. Com o
--      prefixo alinhado, aquele teste roda contra `extra_li_equiv` de forma
--      deterministica — o watermark desaparece — sem uma linha alterada nele.
--
-- Prefixo LI-EQUIV- em todo id sintetico. Datas FIXAS: a semente nao pode
-- depender de relogio, senao o snapshot_id deixaria de ser reproduzivel.

BEGIN;

-- 1. Edital aberto (fonte do universo de OPPORTUNITY e do watermark).
INSERT INTO public.pncp_raw_bids (
    pncp_id, objeto_compra, valor_total_estimado, modalidade_id, modalidade_nome,
    uf, municipio, orgao_cnpj, orgao_razao_social,
    data_publicacao, data_encerramento, source, source_id, is_active, updated_at
) VALUES (
    'LI-TEST-EQUIV-BID-001',
    'Reforma de unidade basica de saude com estrutura metalica',
    '250000.00', 6, 'Pregao Eletronico',
    'SC', 'Florianopolis', '12345678000199', 'Prefeitura Sintetica LI-EQUIV',
    TIMESTAMPTZ '2026-01-10 12:00:00+00',
    TIMESTAMPTZ '2099-12-31 23:59:00+00',
    'pncp', 'LI-TEST-EQUIV-BID-001', TRUE,
    TIMESTAMPTZ '2026-01-15 12:00:00+00'
)
ON CONFLICT (pncp_id) DO NOTHING;

-- 2. Contratos observados: RAIZ e FILIAL do mesmo CNPJ-8.
--    `v_contracts_canonical_v2` projeta `pncp_supplier_contracts` com LEFT JOIN,
--    entao a tabela base sozinha ja alimenta `fetch_observed_portfolio`.
--    O predicado da view exige data_inicio OU data_publicacao nao nula.
INSERT INTO public.pncp_supplier_contracts (
    contrato_id, orgao_cnpj, orgao_nome,
    fornecedor_cnpj, fornecedor_nome, supplier_id_type, supplier_identifier,
    objeto_contrato, valor_total,
    data_inicio, data_publicacao, data_assinatura,
    uf, municipio, source, source_id, is_active
) VALUES
(
    'LI-EQUIV-CONTRACT-RAIZ',
    '12345678000199', 'Prefeitura Sintetica LI-EQUIV',
    '11222333000181', 'Construtora Sintetica LI-EQUIV Matriz', 'CNPJ', '11222333000181',
    'Reforma de escola municipal com estrutura metalica', 320000.00,
    DATE '2026-02-01', DATE '2026-02-05', DATE '2026-01-30',
    'SC', 'Florianopolis', 'pncp', 'LI-EQUIV-CONTRACT-RAIZ', TRUE
),
(
    'LI-EQUIV-CONTRACT-FILIAL',
    -- buyer_cnpj com 6 digitos: alimenta `buyers_unhashable` (AC6).
    '123456', 'Consorcio Sintetico LI-EQUIV',
    '11222333000262', 'Construtora Sintetica LI-EQUIV Filial', 'CNPJ', '11222333000262',
    'Reforma de posto de saude com estrutura metalica', 410000.00,
    DATE '2026-03-01', DATE '2026-03-05', DATE '2026-02-27',
    'SC', 'Sao Jose', 'pncp', 'LI-EQUIV-CONTRACT-FILIAL', TRUE
)
ON CONFLICT (contrato_id) DO NOTHING;

COMMIT;
