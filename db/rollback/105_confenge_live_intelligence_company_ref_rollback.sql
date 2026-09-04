-- 105_confenge_live_intelligence_company_ref_rollback.sql
-- Rollback completo de db/migrations/105_confenge_live_intelligence_company_ref.sql
--
--   psql "$LOCAL_DATALAKE_DSN" -f db/rollback/105_confenge_live_intelligence_company_ref_rollback.sql
--
-- Ordem: indice -> constraints -> colunas. (DROP COLUMN ja removeria indice e
-- CHECK em cascata; os DROP explicitos existem para que o inverso de cada
-- statement da 105 seja legivel neste arquivo, e para que o rollback continue
-- correto se alguem remover uma das colunas manualmente antes.)
--
-- ★ ESCOPO DO INVERSO — o que este rollback deliberadamente NAO faz:
--   * NAO dropa o role confenge_live_intel_reader. O role e da 104; a 105 apenas
--     REASSERTA grants ja existentes sobre uma tabela ja existente. Dropar o
--     role aqui reverteria a 104, nao a 105, e deixaria a 104 quebrada.
--   * NAO emite REVOKE sobre confenge_live_intelligence_companies. O ACL da
--     tabela e da 104 e sobrevive a 105 inalterado; revogar aqui removeria um
--     privilegio que a 105 nao concedeu (o GRANT da 105 e reassercao do da 104,
--     e GRANT e declarativo: reafirma-lo nao acumula estado a desfazer).
--   * NAO toca pg_default_acl — a 105 nao grava linha nenhuma la.
--   Mesmo raciocinio da secao 3 do rollback da 104: so se reverte o que a
--   migration de fato criou; compensar o que ela nao fez cria residuo.
--
-- ★ PERDA DE DADO — este rollback DESCARTA os valores de company_ref e
--   observed_establishment_cnpjs. Aceitavel por construcao: company_ref e
--   funcao pura de company_root8, que permanece na tabela (w2-decisions B.2), e
--   observed_establishment_cnpjs e reprojetavel pelo producer a partir do
--   datalake. Nenhuma observacao original vive apenas nestas duas colunas.
--   Snapshots selados antes da reversao passam a nao ser exportaveis pelo motor
--   1.1 — reverter a 105 implica reverter o codigo do W2 junto, o que ja e o que
--   a secao "Rollback" da story determina.
--
-- Criterio de aceite (verificavel):
--   SELECT attname FROM pg_attribute
--    WHERE attrelid = 'public.confenge_live_intelligence_companies'::regclass
--      AND attname IN ('company_ref','observed_establishment_cnpjs')
--      AND NOT attisdropped;                                  -- 0 linhas
--   SELECT 1 FROM pg_class WHERE relname = 'idx_live_intel_company_ref';  -- 0 linhas
--   SELECT conname FROM pg_constraint
--    WHERE conrelid = 'public.confenge_live_intelligence_companies'::regclass
--      AND conname IN ('chk_live_intel_company_ref_format',
--                      'chk_live_intel_company_establishment_cnpj14');   -- 0 linhas
--   A tabela confenge_live_intelligence_companies continua existindo, com as
--   colunas e o relacl identicos ao estado pre-105.
--   Reaplicar a 105 apos este rollback deve funcionar sem erro.
--
-- Nenhuma tabela, view ou funcao outbound e referenciada por este script.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

-- ---------------------------------------------------------------------------
-- 1. Indice parcial criado pela secao 3 da 105
-- ---------------------------------------------------------------------------
DROP INDEX IF EXISTS public.idx_live_intel_company_ref;

-- ---------------------------------------------------------------------------
-- 2. CHECKs criados pela secao 2 da 105
-- ---------------------------------------------------------------------------
ALTER TABLE public.confenge_live_intelligence_companies
    DROP CONSTRAINT IF EXISTS chk_live_intel_company_ref_format;

ALTER TABLE public.confenge_live_intelligence_companies
    DROP CONSTRAINT IF EXISTS chk_live_intel_company_establishment_cnpj14;

-- ---------------------------------------------------------------------------
-- 3. Colunas aditivas criadas pela secao 1 da 105.
--    Sem CASCADE por disciplina: se algum objeto novo passar a depender destas
--    colunas, o DROP deve FALHAR alto e visivel em vez de arrastar dependente
--    silenciosamente.
-- ---------------------------------------------------------------------------
ALTER TABLE public.confenge_live_intelligence_companies
    DROP COLUMN IF EXISTS observed_establishment_cnpjs;

ALTER TABLE public.confenge_live_intelligence_companies
    DROP COLUMN IF EXISTS company_ref;

COMMIT;
