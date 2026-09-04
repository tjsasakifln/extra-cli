-- 105_confenge_live_intelligence_company_ref.sql
-- CONFENGE_LIVE_INTELLIGENCE — bump ADITIVO do schema do motor para suportar
-- identidade de estabelecimento (LI-W2 / Task 1).
--
-- Story:      docs/stories/story-confenge-live-intelligence-w2-web-export.md (Ready, AC8/AC9/AC11)
-- Normativo:  docs/architecture/confenge-live-intelligence-w2-decisions.md v1.1 (§B.2, §B.3)
-- Owner DDL:  @data-engineer (autoridade exclusiva sobre schema/DDL)
-- Base:       db/migrations/104_confenge_live_intelligence_v1.sql (padrao de estilo,
--             REVOKE/GRANT e rollback herdados literalmente desta migration)
--
-- ============================================================================
-- ESCOPO — lista fechada, nada alem disto:
--   ALTER TABLE public.confenge_live_intelligence_companies
--     + coluna  company_ref                  TEXT      (nullable, formato cref1:<32 hex>)
--     + coluna  observed_establishment_cnpjs TEXT[]    (NOT NULL DEFAULT '{}')
--     + CHECK   chk_live_intel_company_ref_format
--     + CHECK   chk_live_intel_company_establishment_cnpj14
--     + INDEX   idx_live_intel_company_ref   (parcial)
--     + COMMENT ON COLUMN (x2)
--   Reasserção literal dos REVOKE/GRANT da 104 sobre a MESMA tabela.
--
-- NAO faz parte desta migration (registrado para o gate do @architect, nao e
-- omissao):
--   * extensao do role confenge_live_intel_reader com INSERT/DELETE nas tabelas
--     confenge_live_intelligence_* exigida pelo AC10 — pertence ao banco isolado
--     `extra_li_equiv` (Task 10, scripts/ops/li_equiv_db.py), nao ao schema de
--     `extra_test`/producao. Conceder DML aqui alargaria o role em TODO database
--     que aplicar a 105, o que contraria o proprio AC10 (role de leitura).
--   * qualquer CHECK ligando a presenca de `company_ref` a
--     `row_completeness_state`. A assercao "toda company ROW_COMPLETE produz >=1
--     digest de estabelecimento" (AC8 / §B.3) e do producer, por decisao da
--     arquitetura. Em DDL ela quebraria toda linha gravada antes da 105 e
--     inventaria escopo.
--   * qualquer alteracao de coluna existente, DROP, TRUNCATE ou DML — nenhuma.
--
-- ============================================================================
-- ADITIVIDADE — esta migration NAO executa ALTER, DROP, CREATE OR REPLACE nem
-- DML sobre nenhum objeto outbound. Objetos protegidos (mesma lista da 104):
--   opportunity_intel*            confenge_company_target_fit_current
--   confenge_target_fit_dirty     confenge_company_target_fit_history
--   confenge_target_fit_events    confenge_target_fit_shadow
--   pncp_supplier_contracts       canonical_public_snapshots
--   canonical_snapshot_*          canonical_public_events_v1
--   v_open_opportunities_canonical  v_contracts_canonical_v2
--   pncp_raw_bids                 sc_public_entities
-- Nenhum deles e sequer nomeado num statement executavel deste arquivo.
--
-- ★ NOTA PARA O TESTE ESTATICO DE ADITIVIDADE (mesmo instrumento da 104,
--   tests/test_live_intelligence_outbound_equivalence.py): a assercao e POR
--   STATEMENT e sobre o texto sem comentarios. O unico token mutante aqui e
--   `ALTER TABLE public.confenge_live_intelligence_companies`, tabela do proprio
--   motor, criada pela 104 — nao esta em PROTECTED_OBJECTS. Aquele arquivo de
--   teste hoje aponta apenas para a 104; estender a parametrizacao para a 105 e
--   trabalho do @dev na Task 11, e esta declarado na story, nao aqui.
--
-- ============================================================================
-- CUSTO DE APLICACAO
--   ADD COLUMN sem default (company_ref) e ADD COLUMN com default CONSTANTE
--   ('{}'::text[]) nao reescrevem a tabela no PostgreSQL >= 11: o default e
--   gravado em pg_attribute.atthasmissing/attmissingval. MEDIDO no alvo:
--   PostgreSQL 16.15. Os dois CHECK sao validados contra as linhas existentes —
--   `SELECT count(*) FROM public.confenge_live_intelligence_companies` = 0 em
--   `extra_test` (verificado nesta rodada), logo a validacao e trivial. Em um
--   database com linhas pre-105, ambos os CHECK sao satisfeitos por construcao:
--   company_ref nasce NULL (permitido) e observed_establishment_cnpjs nasce
--   '{}' (cardinality 0, permitido).
--   O ALTER TABLE toma ACCESS EXCLUSIVE sob lock_timeout = 5s, igual a 104.
--
-- ============================================================================
-- GRANTS — simetria com a 104, sem grant de coluna
--   O ACL de tabela (pg_class.relacl) vale para colunas adicionadas depois:
--   as colunas novas ja nascem cobertas pelos REVOKE/GRANT da 104. As tres
--   sentencas abaixo sao REASSERCAO idempotente, mantidas literais pelo mesmo
--   motivo da 104 (o teste estatico precisa ver o nome do objeto no texto) e
--   como defesa contra drift manual do ACL entre a 104 e a 105.
--
--   ★ DELIBERADAMENTE NAO emitimos GRANT/REVOKE de COLUNA
--     (`GRANT SELECT (col) ...`). Isso gravaria linha em pg_attribute.attacl,
--     onde a 104 nao gravou nenhuma — divergencia silenciosa de catalogo que
--     nenhum teste existente pegaria. Criterio de aceite: attacl IS NULL para
--     as duas colunas novas.
--   ★ Nenhum ALTER DEFAULT PRIVILEGES, pelo motivo medido e documentado no
--     cabecalho da 104 (mecanismo inerte no PG16; o GRANT inverso gravaria
--     residuo em pg_default_acl). Criterio de aceite: pg_default_acl continua
--     com 0 linhas em 'public'.
--
-- ============================================================================
-- ROLLBACK (comando unico, executavel):
--
--   psql "$LOCAL_DATALAKE_DSN" -f db/rollback/105_confenge_live_intelligence_company_ref_rollback.sql
--
-- O rollback remove indice, CHECKs e as DUAS colunas novas — e nada mais. Ele
-- nao toca no role confenge_live_intel_reader (que e da 104 e sobrevive a 105
-- por desenho) nem em pg_default_acl (a 105 nao grava la).
-- Criterio de aceite do rollback: a tabela
-- confenge_live_intelligence_companies continua existindo com exatamente as
-- colunas pre-105, relacl identico ao pre-105, e reaplicar a 105 depois
-- funciona.
-- ★ O rollback DESCARTA os valores das duas colunas novas. Isso e aceitavel
--   porque ambas sao derivaveis: company_ref e funcao pura de company_root8
--   (§B.2) e observed_establishment_cnpjs e reprojetavel pelo producer a partir
--   do datalake. Nenhum dado observado e perdido de forma irrecuperavel.
--
-- ============================================================================
-- DECISOES REGISTRADAS
--   (a) company_ref e NULLABLE. Migration aditiva sobre tabela que pode ter
--       linhas pre-105, para as quais nao existe valor correto a inventar
--       (backfill seria DML de motor dentro de DDL). O CHECK segue o padrao de
--       `content_hash` da 104 (104:160): "IS NULL OR bate o formato".
--   (b) O formato `cref1:<32 hex>` e travado em CHECK. A versao esta no prefixo
--       por decisao de §B.2: mudanca de formula = `cref2:`, e ai o CHECK muda
--       junto, de forma visivel, numa migration nova.
--   (c) observed_establishment_cnpjs espelha byte a byte a forma de
--       observed_buyer_cnpjs (104:325): TEXT[] NOT NULL DEFAULT '{}'.
--       Diferenca deliberada: aqui existe CHECK de elemento, porque esta coluna
--       e o INSUMO DA IDENTIDADE PUBLICA (company_digest, §B.1) — um elemento
--       de comprimento errado viraria um digest publico invalido e um 404 mudo
--       no consumidor. observed_buyer_cnpjs nao tem CHECK porque seu caminho
--       fail-closed e em tempo de projecao (§A.4.1, buyer_cnpj_not_hashable).
--   (d) O CHECK de elemento tem TRES conjuntos, e cada um cobre um furo real
--       MEDIDO no alvo (PostgreSQL 16.15) durante esta rodada:
--         1. `array_to_string(col, ',') ~ '^([0-9]{14}(,[0-9]{14})*)?$'`
--            sozinho ACEITA o elemento unico '12345678000199,12345678000188'
--            (uma virgula dentro do proprio elemento se disfarca de separador);
--         2. `array_to_string(col, '') ~ '^[0-9]*$'` fecha esse furo (virgula
--            dentro de elemento reprova) mas sozinho aceita {10 digitos, 18
--            digitos};
--         3. `length(array_to_string(col, '')) = 14 * cardinality(col)` fecha o
--            furo de elemento NULL (array_to_string ignora NULL, os demais
--            conjuntos nao o veem).
--       Os tres juntos foram exercitados contra 7 casos (vazio, dois validos,
--       curto, virgula embutida, elemento NULL, 10+18, com letra) com o
--       resultado esperado em todos. Um CHECK furado seria pior que nenhum:
--       daria garantia falsa a um campo de identidade publica.
--   (e) `sorted(set(...))` (ordenacao e unicidade dos elementos, §B.3) NAO e
--       imposto em DDL: exigiria subquery, proibida em CHECK. Continua sendo
--       responsabilidade do producer, e o hash do snapshot torna qualquer
--       divergencia de ordem visivel em replay.
--   (f) O indice e um btree PARCIAL em (snapshot_id, company_ref) WHERE
--       company_ref IS NOT NULL. NAO e UNIQUE: (snapshot_id, company_ref) e
--       unico POR CONSTRUCAO — company_ref e funcao pura de company_root8, que
--       ja compoe a PK (snapshot_id, company_root8) — e uma UNIQUE aqui seria
--       redundante e transformaria um bug de producer em erro de constraint num
--       lugar que nao explica a causa. Registrado para ficar visivel no gate.
--   (g) NAO criamos indice GIN sobre observed_establishment_cnpjs. Nenhum
--       caminho de leitura do W2 busca company POR CNPJ de estabelecimento: o
--       export le a linha da company e projeta N digests a partir do array
--       (§B.3), e a busca reversa do consumidor e resolvida pelo nome do arquivo
--       estatico `companies/<digest>.json`. Indice sem consulta e custo de
--       escrita sem beneficio.
-- ============================================================================

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

-- ---------------------------------------------------------------------------
-- 1. COLUNAS ADITIVAS (§B.3)
--    company_ref                  — pseudonimo INTERNO, 1:1 com a empresa.
--    observed_establishment_cnpjs — CNPJ14 de estabelecimento observados,
--                                   insumo dos N company_digest publicos.
--    Ambas com IF NOT EXISTS: reaplicar este arquivo e no-op.
-- ---------------------------------------------------------------------------
ALTER TABLE public.confenge_live_intelligence_companies
    ADD COLUMN IF NOT EXISTS company_ref                  TEXT,
    ADD COLUMN IF NOT EXISTS observed_establishment_cnpjs TEXT[] NOT NULL DEFAULT '{}';

-- ---------------------------------------------------------------------------
-- 2. CHECKS
--    ADD CONSTRAINT nao aceita IF NOT EXISTS — a idempotencia vem da guarda
--    explicita em pg_constraint (mesmo padrao de guarda da §8 da 104).
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.confenge_live_intelligence_companies'::regclass
          AND conname = 'chk_live_intel_company_ref_format'
    ) THEN
        ALTER TABLE public.confenge_live_intelligence_companies
            ADD CONSTRAINT chk_live_intel_company_ref_format CHECK (
                company_ref IS NULL OR company_ref ~ '^cref1:[0-9a-f]{32}$'
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.confenge_live_intelligence_companies'::regclass
          AND conname = 'chk_live_intel_company_establishment_cnpj14'
    ) THEN
        -- Ver decisao (d) no cabecalho: os tres conjuntos sao necessarios; cada
        -- um sozinho tem um furo medido.
        ALTER TABLE public.confenge_live_intelligence_companies
            ADD CONSTRAINT chk_live_intel_company_establishment_cnpj14 CHECK (
                array_to_string(observed_establishment_cnpjs, '') ~ '^[0-9]*$'
                AND length(array_to_string(observed_establishment_cnpjs, ''))
                    = 14 * cardinality(observed_establishment_cnpjs)
                AND array_to_string(observed_establishment_cnpjs, ',')
                    ~ '^([0-9]{14}(,[0-9]{14})*)?$'
            );
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 3. INDICE — ver decisao (f). Parcial: linhas pre-105 (company_ref NULL) nao
--    entram, e a busca por company_ref sempre traz predicado IS NOT NULL.
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_live_intel_company_ref
    ON public.confenge_live_intelligence_companies (snapshot_id, company_ref)
    WHERE company_ref IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 4. BARREIRA DE SEGURANCA — reassercao literal dos grants da 104 sobre a
--    MESMA tabela. Idempotente por natureza (REVOKE/GRANT sao declarativos).
--    Nenhum grant de coluna, nenhum ALTER DEFAULT PRIVILEGES — ver cabecalho.
-- ---------------------------------------------------------------------------
REVOKE ALL ON TABLE public.confenge_live_intelligence_companies FROM PUBLIC;
REVOKE ALL ON TABLE public.confenge_live_intelligence_companies FROM smartlic_public_reader;
GRANT SELECT ON TABLE public.confenge_live_intelligence_companies TO confenge_live_intel_reader;

-- ---------------------------------------------------------------------------
-- 5. DOCUMENTACAO DE COLUNA
-- ---------------------------------------------------------------------------
COMMENT ON COLUMN public.confenge_live_intelligence_companies.company_ref IS
    'Pseudonimo INTERNO 1:1 com a empresa: cref1: + sha256(confenge-live-intelligence|company_ref|v1|<company_root8>)[:32]. PROIBIDO em payload publico, URL publica ou log compartilhado (w2-decisions B.2). Preenchido pelo producer via metodo de LiveCompany.';

COMMENT ON COLUMN public.confenge_live_intelligence_companies.observed_establishment_cnpjs IS
    'CNPJ de estabelecimento (14 digitos) observados no datalake para a mesma raiz. Insumo dos N company_digest publicos (w2-decisions B.1/B.3): um arquivo companies/<digest>.json por elemento. Interno; nunca serializado cru no bundle publico.';

COMMIT;
