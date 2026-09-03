-- 104_confenge_live_intelligence_v1_rollback.sql
-- Rollback completo de db/migrations/104_confenge_live_intelligence_v1.sql
--
--   psql "$LOCAL_DATALAKE_DSN" -f db/rollback/104_confenge_live_intelligence_v1_rollback.sql
--
-- Ordem: funcao → tabelas filhas → tabelas pai → default privileges → role.
--
-- ★ DROP TABLE NAO remove o role: pg_roles e catalogo compartilhado e sobrevive
--   ao drop das tabelas. Sem a secao 4 abaixo o rollback deixaria residuo e a
--   104 nao seria reaplicavel de forma limpa. A secao 3 (ALTER DEFAULT
--   PRIVILEGES) esta vazia por decisao: a 104 nao grava linha em pg_default_acl,
--   entao nao ha inverso a emitir — ver a propria secao 3.
--
-- Criterio de aceite (verificavel):
--   SELECT * FROM pg_default_acl d JOIN pg_namespace n ON n.oid = d.defaclnamespace
--   WHERE n.nspname = 'public';           -- sem entradas criadas pela 104
--   SELECT 1 FROM pg_roles WHERE rolname = 'confenge_live_intel_reader';  -- 0 linhas
--   \dp public                            -- identico ao estado pre-104
--   Reaplicar a 104 apos este rollback deve funcionar sem erro.
--
-- Nenhuma tabela, view ou funcao outbound e referenciada por este script.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

-- ---------------------------------------------------------------------------
-- 1. Funcao as-of (nada depende dela; removida antes das tabelas por higiene)
-- ---------------------------------------------------------------------------
DROP FUNCTION IF EXISTS public.live_open_opportunities_as_of(DATE);

-- ---------------------------------------------------------------------------
-- 2. Tabelas do motor — filhas antes das referenciadas
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS public.confenge_live_intelligence_events;
DROP TABLE IF EXISTS public.confenge_live_intelligence_fit;
DROP TABLE IF EXISTS public.confenge_live_intelligence_companies;
DROP TABLE IF EXISTS public.confenge_live_intelligence_opportunities;
DROP TABLE IF EXISTS public.confenge_live_intelligence_source_watermarks;
DROP TABLE IF EXISTS public.confenge_live_intelligence_snapshots;

-- ---------------------------------------------------------------------------
-- 3. ★ ALTER DEFAULT PRIVILEGES — NADA A REVERTER (secao mantida vazia).
--
--    Achado do @dev, ratificado pelo @data-engineer contra PostgreSQL 16.15:
--    os tres ALTER DEFAULT PRIVILEGES que a 104 emitia eram INERTES. MEDIDO em
--    16.15: apos os tres statements, pg_default_acl continua com 0 linhas em
--    'public' e uma funcao criada depois nasce com proacl NULL (PUBLIC mantem
--    EXECUTE). O EFEITO esta provado; o mecanismo interno do PostgreSQL que o
--    causa NAO foi determinado — ver a nota completa no cabecalho da 104.
--
--    O GRANT inverso, porem, GRAVA linha ({=X/owner}). Um "GRANT EXECUTE ON
--    FUNCTIONS TO PUBLIC" incondicional aqui — como havia neste arquivo —
--    CRIAVA o residuo que este rollback existe para impedir, invertendo algo
--    que a 104 nunca fez. Tornar esse GRANT condicional a existencia da linha
--    (correcao inicial do @dev) removia o residuo, mas ainda era incorreto no
--    caso em que a linha PRE-EXISTIA a 104: o rollback concederia a PUBLIC um
--    privilegio que a 104 nao havia removido.
--
--    Resolucao definitiva: a §9 da 104 foi REMOVIDA. Sem ALTER DEFAULT
--    PRIVILEGES na migration, este rollback nao tem inverso a emitir, e o
--    criterio de aceite "pg_default_acl sem entradas desta migration" passa a
--    ser verdadeiro por construcao, nao por compensacao.
--
--    ★ Se a §9 da 104 um dia voltar e gravar linha em pg_default_acl, o GRANT
--      inverso deve voltar AQUI — condicionado, e comparando o estado com o
--      snapshot pre-104, nunca incondicional.
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- 4. ★ Role de leitura — condicionado ao marcador da 104 (padrao de 089).
--    Decisao registrada (AC12-b): o role e DROPADO no rollback, nao retido.
--    Reter um role inerte deixaria uma identidade de banco sem dono nem
--    contrato; dropa-lo torna o par migration/rollback simetrico e verificavel
--    por "SELECT 1 FROM pg_roles" retornando zero linhas.
--    Se o role possuir objetos fora deste database, a excecao e capturada e o
--    role e retido com NOTICE — mesmo comportamento de 089.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_roles role
        WHERE role.rolname = 'confenge_live_intel_reader'
          AND shobj_description(role.oid, 'pg_authid') = 'managed-by-extra-migration-104'
    ) THEN
        EXECUTE format('REVOKE ALL ON SCHEMA public FROM confenge_live_intel_reader');
        EXECUTE format('REVOKE CONNECT ON DATABASE %I FROM confenge_live_intel_reader', current_database());
        EXECUTE format('REVOKE confenge_live_intel_reader FROM %I', current_user);
        ALTER ROLE confenge_live_intel_reader RESET statement_timeout;
        ALTER ROLE confenge_live_intel_reader RESET lock_timeout;
        ALTER ROLE confenge_live_intel_reader RESET idle_in_transaction_session_timeout;
        ALTER ROLE confenge_live_intel_reader RESET default_transaction_read_only;
        DROP OWNED BY confenge_live_intel_reader;
        BEGIN
            DROP ROLE confenge_live_intel_reader;
        EXCEPTION
            WHEN dependent_objects_still_exist THEN
                RAISE NOTICE 'confenge_live_intel_reader ainda possui objetos fora do database %; role retido', current_database();
        END;
    END IF;
END $$;

COMMIT;
