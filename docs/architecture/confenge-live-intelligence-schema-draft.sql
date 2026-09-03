-- =============================================================================
-- DRAFT (NAO APLICAR) — CONFENGE_LIVE_INTELLIGENCE/1.0
-- Destino proposto: db/migrations/110_confenge_live_intelligence_v1.sql
-- Autor: @data-engineer (Dara) — missao CONFENGE-REVENUE-MULTI-ENGINE-W1
-- Status: DRAFT para revisao do @architect. NAO copiar para db/migrations/
--         antes do parecer sobre as duas decisoes abertas (ver rodape).
-- =============================================================================
--
-- PROPOSITO
-- ---------
-- Motor INBOUND ("Live Intelligence") que roda em paralelo ao motor outbound
-- existente (target-fit / sector / contracts). O inbound observa o mundo e
-- publica um snapshot canonico congelado; o outbound continua dono exclusivo
-- das suas proprias tabelas.
--
-- REGRA DURA HONRADA POR ESTE ARQUIVO
-- -----------------------------------
-- Nenhum ALTER / INSERT / UPDATE / DELETE / DROP / CREATE TRIGGER sobre:
--   public.opportunity_intel
--   public.confenge_company_target_fit_current
--   public.confenge_company_target_fit_history
--   public.confenge_target_fit_dirty
--   public.pncp_supplier_contracts
--   public.canonical_public_snapshots
--   public.canonical_snapshot_*  (watermarks / event_revisions / documents /
--                                 dossiers / invalidations)
--   public.confenge_company_sector_current
--   public.confenge_company_sector_history
--
-- Este arquivo SOMENTE cria objetos novos (schema confenge_live_v1 + tabelas
-- prefixadas confenge_live_*) e LE as tabelas acima por SELECT.
--
-- DECISAO DE PROJETO CRITICA #1 — POR QUE NAO HA "CREATE TRIGGER"
-- ----------------------------------------------------------------
-- O caminho obvio para produzir os 5 eventos seria
--   AFTER INSERT OR UPDATE ON public.pncp_raw_bids
--   AFTER UPDATE ON public.confenge_company_target_fit_current
-- exatamente como a 089 faz em canonical_event_revisions. ISSO E PROIBIDO AQUI:
--   (a) CREATE TRIGGER e DDL sobre a tabela alvo: pega ACCESS EXCLUSIVE lock
--       e altera o objeto do outro motor;
--   (b) qualquer excecao dentro da funcao de trigger FAZ FALHAR o write do
--       motor outbound — acoplamento fatal entre dois motores que deveriam ser
--       independentes.
-- "Triggers idempotentes" no handoff significa SEMANTICA DE GATILHO (5 tipos de
-- evento deduplicados), nao TRIGGER do PostgreSQL.
-- Mecanismo adotado: POLL/CDC por watermark, espelhando o que a propria 071 ja
-- faz (confenge_target_fit_control.cdc_watermark). O worker le o delta via
-- SELECT e INSERE na tabela de eventos deste schema.
-- >>> REVISOR: nao "conserte" isto de volta para CREATE TRIGGER. <<<
--
-- DECISAO DE PROJETO CRITICA #2 — LIMITE REAL DO "AS-OF"
-- ------------------------------------------------------
-- public.v_open_opportunities_canonical (049) filtra por CURRENT_DATE, logo nao
-- e replayable. Trocar CURRENT_DATE por p_effective_date e NECESSARIO mas NAO
-- SUFICIENTE: public.pncp_raw_bids e mutada in-place (trg_bids_updated_at,
-- upsert_pncp_raw_bids) e nao possui valid_from/valid_to. Reexecutar a funcao
-- com uma data passada le o data_encerramento e o matched_entity_id de HOJE,
-- nao os daquela data.
-- Consequencia arquitetural assumida aqui:
--   * a funcao as-of e um INPUT DE BUILD (determinista dado o estado atual da
--     base + a data explicita), nao a verdade replayable;
--   * a verdade replayable e a tabela de membership do snapshot
--     (confenge_live_opportunity_snapshot), imutavel apos READY_CANONICAL —
--     analoga a canonical_snapshot_event_revisions da 089;
--   * chamadas retroativas sao best-effort e carimbadas com o reason code
--     'as_of_recomputed_from_mutable_base'.
-- Replay temporal completo exigiria historico append-only de bids
-- (bid observation history). Isso e escopo proprio -> @architect.
-- =============================================================================

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

-- -----------------------------------------------------------------------------
-- 0. Schemas
--    confenge_live_v1  : superficie de leitura publica (contrato versionado)
--    tabelas internas  : ficam em public.confenge_live_* (mesma convencao das
--                        071/072, facilita backup/ops e nao mistura escrita
--                        interna com a superficie select-only).
-- -----------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS confenge_live_v1;

COMMENT ON SCHEMA confenge_live_v1 IS
'Superficie select-only do motor inbound CONFENGE Live Intelligence v1. Contrato versionado; mudancas destrutivas exigem confenge_live_v2.';


-- =============================================================================
-- 1. SNAPSHOT HEADER — state machine + hashes por componente + watermarks
--    Espelha public.canonical_public_snapshots (089) SEM tocar nela.
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.confenge_live_snapshots (
    -- Identidade estavel derivada dos hashes de entrada (ver
    -- confenge_live_snapshot_id() abaixo), nunca de sequencia.
    snapshot_id              TEXT PRIMARY KEY,

    -- Corte temporal do snapshot. cutoff_at e o instante; effective_date e o
    -- dia civil usado pelo wrapper as-of de oportunidades (deadline e um fato
    -- de calendario, nao de instante).
    -- Proveniencia: definido pelo orquestrador do build.
    cutoff_at                TIMESTAMPTZ NOT NULL,
    effective_date           DATE NOT NULL,
    -- Timezone fixo, mesma trava da 089: sem isto, "data_encerramento >= hoje"
    -- muda de resultado conforme o TimeZone da sessao.
    cutoff_timezone          TEXT NOT NULL DEFAULT 'America/Sao_Paulo'
                                  CHECK (cutoff_timezone = 'America/Sao_Paulo'),

    -- Hashes SHA256 por componente (padrao 089). Cada um responde
    -- "que entrada mudou?" sem precisar difar conteudo.
    --   universe_hash  : universo de empresas considerado (CNPJ roots)
    --   policy_hash    : politica de relevancia/fit vigente
    --   schema_hash    : formato das tabelas de saida
    --   scoring_hash   : versao+sha do scorer de fit oportunidade x empresa
    --   opportunity_hash / company_hash / fit_hash : hash do conteudo de cada
    --                    familia projetada neste snapshot
    universe_hash            TEXT NOT NULL CHECK (universe_hash ~ '^[0-9a-f]{64}$'),
    policy_hash              TEXT NOT NULL CHECK (policy_hash ~ '^[0-9a-f]{64}$'),
    schema_hash              TEXT NOT NULL CHECK (schema_hash ~ '^[0-9a-f]{64}$'),
    scoring_hash             TEXT NOT NULL CHECK (scoring_hash ~ '^[0-9a-f]{64}$'),
    opportunity_hash         TEXT NOT NULL CHECK (opportunity_hash ~ '^[0-9a-f]{64}$'),
    company_hash             TEXT NOT NULL CHECK (company_hash ~ '^[0-9a-f]{64}$'),
    fit_hash                 TEXT NOT NULL CHECK (fit_hash ~ '^[0-9a-f]{64}$'),

    -- State machine. O handoff pediu 3 estados (BUILDING/READY_CANONICAL/
    -- SUPERSEDED); BLOCKED foi adicionado porque sem ele nao ha onde registrar
    -- blockers de fechamento sem mentir que o snapshot esta pronto — mesma
    -- razao da 089. DESVIO DOCUMENTADO, sujeito a veto do @architect.
    state                    TEXT NOT NULL DEFAULT 'BUILDING'
                                  CHECK (state IN ('BUILDING', 'BLOCKED',
                                                   'READY_CANONICAL', 'SUPERSEDED')),
    blockers                 JSONB NOT NULL DEFAULT '[]'::JSONB,

    -- Contagens declaradas na abertura; conferidas no fechamento.
    required_source_count    INTEGER NOT NULL CHECK (required_source_count >= 0),
    required_company_count   INTEGER NOT NULL CHECK (required_company_count >= 0),

    content_hash             TEXT CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at                TIMESTAMPTZ,
    superseded_at            TIMESTAMPTZ,
    superseded_by            TEXT REFERENCES public.confenge_live_snapshots(snapshot_id),
    created_by               TEXT NOT NULL,

    -- Zero PII / zero identidade de cliente nas colunas de chave (espirito da
    -- 089: CHECK (snapshot_id !~* 'client|profile')).
    CHECK (snapshot_id !~* 'client|profile|email|contact'),
    CHECK (created_by  !~* 'client|profile|email|contact'),

    -- Invariante de fechamento (089): READY_CANONICAL exige fechamento real.
    CHECK (state <> 'READY_CANONICAL'
           OR (closed_at IS NOT NULL AND content_hash IS NOT NULL AND blockers = '[]'::JSONB)),
    -- A 089 tem superseded_at sem transicao definida. Aqui a transicao e
    -- explicita: SUPERSEDED exige carimbo e sucessor.
    CHECK (state <> 'SUPERSEDED'
           OR (superseded_at IS NOT NULL AND superseded_by IS NOT NULL)),
    CHECK (superseded_by IS NULL OR superseded_by <> snapshot_id)
);

CREATE INDEX IF NOT EXISTS confenge_live_snapshots_ready_idx
    ON public.confenge_live_snapshots (cutoff_at DESC, snapshot_id)
    WHERE state = 'READY_CANONICAL';

COMMENT ON TABLE public.confenge_live_snapshots IS
'Header do snapshot do motor inbound Live Intelligence. Aditivo: nao referencia nem escreve em canonical_public_snapshots.';


-- Watermark por fonte. Analogo a canonical_snapshot_source_watermarks (089).
-- Proveniencia esperada de 'source':
--   'pncp_raw_bids'                        -> max(updated_at) da base de bids
--   'confenge_company_target_fit_current'  -> max(updated_at) (SELECT apenas)
--   'confenge_company_sector_current'      -> max(updated_at) (SELECT apenas)
--   'pncp_supplier_contracts'              -> max(ingested_at) (SELECT apenas)
CREATE TABLE IF NOT EXISTS public.confenge_live_snapshot_watermarks (
    snapshot_id              TEXT NOT NULL REFERENCES public.confenge_live_snapshots(snapshot_id),
    source                   TEXT NOT NULL,
    source_run_id            TEXT NOT NULL,
    watermark_at             TIMESTAMPTZ NOT NULL,
    freshness_state          TEXT NOT NULL
                                  CHECK (freshness_state IN ('FRESH', 'STALE', 'FAILED', 'BLOCKED', 'UNKNOWN')),
    completeness_state       TEXT NOT NULL
                                  CHECK (completeness_state IN ('COMPLETE', 'INCOMPLETE', 'UNKNOWN')),
    applicable_row_count     BIGINT NOT NULL CHECK (applicable_row_count >= 0),
    evaluated_row_count      BIGINT NOT NULL CHECK (evaluated_row_count >= 0),
    evidence_hash            TEXT NOT NULL CHECK (evidence_hash ~ '^[0-9a-f]{64}$'),
    reason_codes             TEXT[] NOT NULL DEFAULT '{}',
    recorded_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (snapshot_id, source)
);

COMMENT ON TABLE public.confenge_live_snapshot_watermarks IS
'Watermark/freshness por fonte lida. Somente SELECT foi feito nas fontes; este registro e a prova do que foi lido e ate onde.';


-- =============================================================================
-- 2. WRAPPER AS-OF DE OPORTUNIDADES (resolve o CURRENT_DATE da 049)
--    Tabela-base real: public.pncp_raw_bids (PK pncp_id, migration 001,
--    colunas de data promovidas a TIMESTAMPTZ na 049).
--    A view v_open_opportunities_canonical NAO e usada: ela embute CURRENT_DATE.
-- =============================================================================

CREATE OR REPLACE FUNCTION public.confenge_live_open_opportunities_as_of(
    p_effective_date DATE
)
RETURNS TABLE (
    bid_id                   TEXT,
    objeto                   TEXT,
    valor_estimado           NUMERIC(18,2),
    modalidade_id            INTEGER,
    modalidade               TEXT,
    esfera_id                TEXT,
    uf                       TEXT,
    municipio                TEXT,
    codigo_ibge              TEXT,
    orgao_cnpj               TEXT,
    orgao_nome               TEXT,
    data_publicacao          TIMESTAMPTZ,
    data_abertura            TIMESTAMPTZ,
    data_encerramento        TIMESTAMPTZ,
    link_edital              TEXT,
    source                   TEXT,
    source_id                TEXT,
    matched_entity_id        INTEGER,
    matched_entity_nome      TEXT,
    entity_cnpj_8            TEXT,
    within_200km             BOOLEAN,
    source_updated_at        TIMESTAMPTZ,
    openness_reason_codes    TEXT[]
)
LANGUAGE sql
-- STABLE, nao IMMUTABLE: le tabelas. Marcar IMMUTABLE aqui seria mentira e
-- permitiria ao planner cachear resultado entre statements.
STABLE
AS $$
    SELECT
        bid.pncp_id,
        bid.objeto_compra,
        bid.valor_total_estimado,
        bid.modalidade_id,
        bid.modalidade_nome,
        bid.esfera_id,
        bid.uf,
        bid.municipio,
        bid.codigo_municipio_ibge,
        bid.orgao_cnpj,
        bid.orgao_razao_social,
        bid.data_publicacao,
        bid.data_abertura,
        bid.data_encerramento,
        bid.link_pncp,
        bid.source,
        bid.source_id,
        bid.matched_entity_id,
        entity.razao_social,
        entity.cnpj_8,
        entity.raio_200km,
        bid.updated_at,
        -- Reason codes explicam POR QUE a linha esta no conjunto e o que nela
        -- e desconhecido/nao replayavel. Sem isto, "aberta" vira opiniao.
        (
            ARRAY['as_of_recomputed_from_mutable_base']
            || CASE WHEN bid.data_encerramento IS NULL
                    THEN ARRAY['deadline_unknown_publication_window_fallback']
                    ELSE ARRAY[]::TEXT[] END
            || CASE WHEN bid.matched_entity_id IS NULL
                    THEN ARRAY['entity_not_in_sc_registry']
                    ELSE ARRAY[]::TEXT[] END
            || CASE WHEN bid.codigo_municipio_ibge IS NULL
                    THEN ARRAY['municipality_unknown']
                    ELSE ARRAY[]::TEXT[] END
            || CASE WHEN bid.valor_total_estimado IS NULL
                    THEN ARRAY['value_unknown']
                    ELSE ARRAY[]::TEXT[] END
        )::TEXT[]
    FROM public.pncp_raw_bids bid
    -- LEFT JOIN deliberado (identico a 049): sc_public_entities e registro
    -- ESTADUAL (SC). Transformar em INNER JOIN estreitaria silenciosamente um
    -- motor nacional. Ausencia vira reason code, nao filtro.
    LEFT JOIN public.sc_public_entities entity
           ON entity.id = bid.matched_entity_id
    -- Estreitamento DELIBERADO em relacao a 049 (que nao filtra is_active):
    -- bid soft-deletada nao pode entrar num snapshot que se diz canonico.
    -- Nao e descuido; se o @architect quiser paridade exata com a 049, remover.
    WHERE bid.is_active
      AND (
            -- Data civil ancorada em America/Sao_Paulo. Comparar TIMESTAMPTZ
            -- com DATE nu depende do TimeZone da sessao — mesmo defeito que a
            -- 089 evita fixando cutoff_timezone.
            bid.data_encerramento >= (p_effective_date::TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')
         OR (
            bid.data_encerramento IS NULL
            AND bid.data_publicacao >= ((p_effective_date - INTERVAL '30 days')::TIMESTAMP
                                        AT TIME ZONE 'America/Sao_Paulo')
            AND bid.data_publicacao <  ((p_effective_date + INTERVAL '1 day')::TIMESTAMP
                                        AT TIME ZONE 'America/Sao_Paulo')
         )
      )
      -- Sem esta clausula o "as-of" de uma data passada incluiria editais
      -- publicados DEPOIS da data efetiva. Nao corrige mutacao in-place, mas
      -- elimina o vazamento de futuro obvio.
      -- O ramo "IS NULL" e OBRIGATORIO: comparacao com NULL e NULL, e sem ele
      -- toda bid sem data_publicacao sumiria do conjunto — inclusive as que a
      -- 049 inclui por data_encerramento. Seria subcontagem silenciosa num
      -- snapshot que se declara determinista.
      AND (
            bid.data_publicacao IS NULL
         OR bid.data_publicacao < ((p_effective_date + INTERVAL '1 day')::TIMESTAMP
                                   AT TIME ZONE 'America/Sao_Paulo')
      )
$$;

COMMENT ON FUNCTION public.confenge_live_open_opportunities_as_of(DATE) IS
'Conjunto de oportunidades abertas parametrizado por data efetiva explicita (substitui o CURRENT_DATE de v_open_opportunities_canonical). Le pncp_raw_bids por SELECT. Determinista dado o estado atual da base; NAO reconstroi o estado passado da base mutavel — ver reason code as_of_recomputed_from_mutable_base.';


-- =============================================================================
-- 3. OPPORTUNITY SNAPSHOT — membership congelada (a verdade replayable)
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.confenge_live_opportunity_snapshot (
    snapshot_id              TEXT NOT NULL REFERENCES public.confenge_live_snapshots(snapshot_id),
    -- Identidade estavel: pncp_id e PK natural de pncp_raw_bids (001).
    opportunity_key          TEXT NOT NULL,

    -- ---- Fatos projetados. Proveniencia coluna a coluna: -------------------
    -- objeto            <- pncp_raw_bids.objeto_compra
    -- valor_estimado    <- pncp_raw_bids.valor_total_estimado
    -- modalidade_*      <- pncp_raw_bids.modalidade_id / modalidade_nome
    -- esfera_id         <- pncp_raw_bids.esfera_id (TEXT desde a 049)
    -- uf/municipio/ibge <- pncp_raw_bids.uf / municipio / codigo_municipio_ibge
    -- orgao_cnpj/nome   <- pncp_raw_bids.orgao_cnpj / orgao_razao_social
    -- datas             <- pncp_raw_bids.data_publicacao/abertura/encerramento
    -- link_edital       <- pncp_raw_bids.link_pncp
    -- NULL = UNKNOWN EXPLICITO, sempre acompanhado de reason_codes.
    objeto                   TEXT,
    valor_estimado           NUMERIC(18,2),
    modalidade_id            INTEGER,
    modalidade               TEXT,
    esfera_id                TEXT,
    uf                       TEXT,
    municipio                TEXT,
    codigo_ibge              TEXT,
    orgao_cnpj               TEXT,
    orgao_nome               TEXT,
    data_publicacao          TIMESTAMPTZ,
    data_abertura            TIMESTAMPTZ,
    data_encerramento        TIMESTAMPTZ,
    link_edital              TEXT,

    -- Estado derivado, nunca copiado de fonte.
    openness_state           TEXT NOT NULL
                                  CHECK (openness_state IN ('OPEN', 'CLOSING_SOON', 'CLOSED', 'UNKNOWN')),

    -- Proveniencia e reprodutibilidade
    source                   TEXT NOT NULL,
    source_id                TEXT,
    source_as_of             TIMESTAMPTZ NOT NULL,   -- pncp_raw_bids.updated_at
    reason_codes             TEXT[] NOT NULL DEFAULT '{}',
    -- semantic_hash = SHA256 do conjunto de fatos materiais (sem timestamps de
    -- coleta). E o que distingue "mudou de verdade" de "foi recoletado".
    semantic_hash            TEXT NOT NULL CHECK (semantic_hash ~ '^[0-9a-f]{64}$'),
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (snapshot_id, opportunity_key),

    -- UNKNOWN so e legitimo se explicado — e explicado PELO CODIGO CERTO.
    -- ATENCAO: "reason_codes <> '{}'" seria uma CHECK VAZIA aqui, porque a
    -- funcao as-of emite 'as_of_recomputed_from_mutable_base' em TODA linha.
    -- Cada NULL precisa estar amarrado ao codigo que explica AQUELE NULL.
    CHECK (data_encerramento IS NOT NULL
           OR 'deadline_unknown_publication_window_fallback' = ANY (reason_codes)),
    CHECK (valor_estimado IS NOT NULL
           OR 'value_unknown' = ANY (reason_codes)),
    CHECK (codigo_ibge IS NOT NULL
           OR 'municipality_unknown' = ANY (reason_codes)),
    CHECK (openness_state <> 'UNKNOWN'
           OR 'openness_undeterminable' = ANY (reason_codes)),
    -- Zero PII: nenhuma coluna de contato existe aqui, e a chave nao pode
    -- carregar identidade pessoal/cliente.
    CHECK (opportunity_key !~* 'email|telefone|phone|contact|client')
);

CREATE INDEX IF NOT EXISTS confenge_live_opp_snapshot_state_idx
    ON public.confenge_live_opportunity_snapshot (snapshot_id, openness_state);
CREATE INDEX IF NOT EXISTS confenge_live_opp_snapshot_deadline_idx
    ON public.confenge_live_opportunity_snapshot (snapshot_id, data_encerramento);
CREATE INDEX IF NOT EXISTS confenge_live_opp_snapshot_key_idx
    ON public.confenge_live_opportunity_snapshot (opportunity_key, snapshot_id);

COMMENT ON TABLE public.confenge_live_opportunity_snapshot IS
'Membership congelada de oportunidades por snapshot. Esta tabela — nao a funcao as-of — e o artefato replayable do motor inbound.';


-- =============================================================================
-- 4. COMPANY SNAPSHOT — retrato congelado da empresa (somente leitura da fonte)
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.confenge_live_company_snapshot (
    snapshot_id              TEXT NOT NULL REFERENCES public.confenge_live_snapshots(snapshot_id),
    -- Identidade estavel: mesma granularidade do motor outbound (raiz de CNPJ),
    -- para que os dois motores falem da mesma empresa sem compartilhar tabela.
    company_key              TEXT NOT NULL,
    cnpj_raiz                CHAR(8) NOT NULL,

    -- ---- Proveniencia (tudo por SELECT, nada e escrito na origem): ---------
    -- target_fit_class/confidence/version
    --      <- confenge_company_target_fit_current (071)  [SELECT]
    -- sector_class/confidence/version
    --      <- confenge_company_sector_current (072)      [SELECT]
    -- portfolio_*  <- agregacao de pncp_supplier_contracts / contract_role_links
    --                 via v_contracts_canonical_v2 (077) [SELECT]
    -- NULL = a fonte nao tinha linha para esta empresa (UNKNOWN explicito),
    -- nunca um default silencioso tipo '' ou 0.
    target_fit_class         TEXT,
    target_fit_confidence    DOUBLE PRECISION
                                  CHECK (target_fit_confidence IS NULL
                                         OR (target_fit_confidence >= 0 AND target_fit_confidence <= 1)),
    target_fit_version       TEXT,
    sector_class             TEXT,
    sector_confidence        DOUBLE PRECISION
                                  CHECK (sector_confidence IS NULL
                                         OR (sector_confidence >= 0 AND sector_confidence <= 1)),
    sector_version           TEXT,
    portfolio_contract_count INTEGER CHECK (portfolio_contract_count IS NULL OR portfolio_contract_count >= 0),
    portfolio_total_value    NUMERIC(18,2),
    portfolio_last_award_at  TIMESTAMPTZ,
    portfolio_uf_coverage    TEXT[],

    -- Estado de elegibilidade do inbound. Deliberadamente NAO reutiliza os
    -- rotulos do outbound: se um dia a politica divergir, nada quebra la.
    inbound_eligibility      TEXT NOT NULL
                                  CHECK (inbound_eligibility IN ('ELIGIBLE', 'NOT_ELIGIBLE', 'UNKNOWN')),

    source_as_of             TIMESTAMPTZ NOT NULL,
    reason_codes             TEXT[] NOT NULL DEFAULT '{}',
    semantic_hash            TEXT NOT NULL CHECK (semantic_hash ~ '^[0-9a-f]{64}$'),
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (snapshot_id, company_key),

    -- Mesma regra: o codigo tem de explicar o NULL especifico, nao apenas
    -- existir. Codigos esperados do populador (poll/CDC):
    --   target_fit_source_missing : sem linha em confenge_company_target_fit_current
    --   sector_source_missing     : sem linha em confenge_company_sector_current
    --   eligibility_undeterminable: fit/sector ausentes ou politica indefinida
    CHECK (target_fit_class IS NOT NULL
           OR 'target_fit_source_missing' = ANY (reason_codes)),
    CHECK (sector_class IS NOT NULL
           OR 'sector_source_missing' = ANY (reason_codes)),
    CHECK (inbound_eligibility <> 'UNKNOWN'
           OR 'eligibility_undeterminable' = ANY (reason_codes)),
    -- Zero PII e zero contato: sem nome de pessoa, e-mail, telefone ou cargo.
    -- CNPJ/raiz e identificador de pessoa juridica publico (mesmo criterio da
    -- 089, que exporta tax_identifier_export).
    CHECK (company_key !~* 'email|telefone|phone|contact|whatsapp'),
    CHECK (cnpj_raiz ~ '^[0-9]{8}$')
);

CREATE INDEX IF NOT EXISTS confenge_live_company_snapshot_elig_idx
    ON public.confenge_live_company_snapshot (snapshot_id, inbound_eligibility);
CREATE INDEX IF NOT EXISTS confenge_live_company_snapshot_raiz_idx
    ON public.confenge_live_company_snapshot (cnpj_raiz, snapshot_id);

COMMENT ON TABLE public.confenge_live_company_snapshot IS
'Retrato congelado da empresa para o motor inbound. Copia por valor (SELECT) de target-fit/sector/portfolio: o inbound nunca escreve nas tabelas do outbound.';


-- =============================================================================
-- 5. COMPANY_OPPORTUNITY_FIT SNAPSHOT — o produto do motor inbound
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.confenge_live_company_opportunity_fit_snapshot (
    snapshot_id              TEXT NOT NULL REFERENCES public.confenge_live_snapshots(snapshot_id),
    company_key              TEXT NOT NULL,
    opportunity_key          TEXT NOT NULL,

    -- Classe de aderencia. RELEVANCE_UNKNOWN e um veredito legitimo e
    -- obrigatoriamente explicado por reason_codes.
    fit_class                TEXT NOT NULL
                                  CHECK (fit_class IN ('FIT_STRONG', 'FIT_POSSIBLE',
                                                       'FIT_WEAK', 'NOT_RELEVANT',
                                                       'RELEVANCE_UNKNOWN')),
    -- NULL = score nao pode ser computado (entrada faltante), com reason code.
    fit_score                DOUBLE PRECISION
                                  CHECK (fit_score IS NULL OR (fit_score >= 0 AND fit_score <= 1)),
    fit_version              TEXT NOT NULL,
    scorer_sha256            TEXT NOT NULL CHECK (scorer_sha256 ~ '^[0-9a-f]{64}$'),

    -- Dimensoes de proveniencia do fit (de onde veio cada sinal):
    --   sector_signal    <- confenge_live_company_snapshot.sector_class
    --   geo_signal       <- opportunity.uf/codigo_ibge x company portfolio_uf_coverage
    --   value_signal     <- opportunity.valor_estimado x portfolio_total_value
    --   deadline_signal  <- opportunity.data_encerramento x snapshot.effective_date
    sector_signal            TEXT,
    geo_signal               TEXT,
    value_signal             TEXT,
    deadline_signal          TEXT,

    evidence                 JSONB NOT NULL DEFAULT '[]'::JSONB,
    reason_codes             TEXT[] NOT NULL DEFAULT '{}',
    source_as_of             TIMESTAMPTZ NOT NULL,
    semantic_hash            TEXT NOT NULL CHECK (semantic_hash ~ '^[0-9a-f]{64}$'),
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (snapshot_id, company_key, opportunity_key),
    -- Integridade referencial DENTRO do snapshot: um fit so existe se ambos os
    -- lados estiverem congelados no mesmo snapshot. Isto e o que impede um fit
    -- "orfao" apontando para um estado nunca publicado.
    FOREIGN KEY (snapshot_id, company_key)
        REFERENCES public.confenge_live_company_snapshot (snapshot_id, company_key),
    FOREIGN KEY (snapshot_id, opportunity_key)
        REFERENCES public.confenge_live_opportunity_snapshot (snapshot_id, opportunity_key),

    CHECK (fit_score IS NOT NULL
           OR 'fit_score_uncomputable' = ANY (reason_codes)),
    CHECK (fit_class <> 'RELEVANCE_UNKNOWN'
           OR 'relevance_undeterminable' = ANY (reason_codes)),
    CHECK (sector_signal IS NOT NULL
           OR 'sector_signal_missing' = ANY (reason_codes))
);

CREATE INDEX IF NOT EXISTS confenge_live_fit_company_idx
    ON public.confenge_live_company_opportunity_fit_snapshot (snapshot_id, company_key, fit_class);
CREATE INDEX IF NOT EXISTS confenge_live_fit_opportunity_idx
    ON public.confenge_live_company_opportunity_fit_snapshot (snapshot_id, opportunity_key, fit_class);
CREATE INDEX IF NOT EXISTS confenge_live_fit_relevant_idx
    ON public.confenge_live_company_opportunity_fit_snapshot (snapshot_id, fit_score DESC)
    WHERE fit_class IN ('FIT_STRONG', 'FIT_POSSIBLE');

COMMENT ON TABLE public.confenge_live_company_opportunity_fit_snapshot IS
'Aderencia empresa x oportunidade congelada por snapshot. FKs compostas garantem que os dois lados pertencem ao mesmo snapshot.';


-- =============================================================================
-- 6. EVENTS — os 5 gatilhos, idempotentes por construcao
--    Populada por POLL/CDC (ver DECISAO CRITICA #1), nunca por TRIGGER nas
--    tabelas do outbound.
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.confenge_live_events (
    event_id                 BIGSERIAL PRIMARY KEY,

    event_type               TEXT NOT NULL
                                  CHECK (event_type IN (
                                      'NEW_OPPORTUNITY',
                                      'OPPORTUNITY_CHANGED',
                                      'DEADLINE_CHANGED',
                                      'FIT_BECAME_RELEVANT',
                                      'COMPANY_PORTFOLIO_CHANGED'
                                  )),

    -- ---- Identidade estavel ------------------------------------------------
    -- subject_kind + subject_key sao a identidade logica do evento.
    --   OPPORTUNITY  -> subject_key = pncp_id
    --   COMPANY      -> subject_key = company_key (raiz de CNPJ)
    --   COMPANY_OPPORTUNITY -> subject_key = company_key || '|' || pncp_id
    subject_kind             TEXT NOT NULL
                                  CHECK (subject_kind IN ('OPPORTUNITY', 'COMPANY', 'COMPANY_OPPORTUNITY')),
    subject_key              TEXT NOT NULL,
    company_key              TEXT,
    opportunity_key          TEXT,

    -- Sem DEFAULT de proposito: '{}' violaria o proprio CHECK, entao um default
    -- aqui seria codigo morto. Um evento sem razao nao e um evento.
    reason_codes             TEXT[] NOT NULL CHECK (reason_codes <> '{}'),

    -- Momento do fato na FONTE (nao do processamento). Fica FORA da chave de
    -- idempotencia de proposito.
    source_as_of             TIMESTAMPTZ NOT NULL,

    -- Hash do conteudo material que justifica o evento (estado novo, e para
    -- *_CHANGED tambem o estado anterior). Dois polls sobre o mesmo fato
    -- produzem o mesmo semantic_hash.
    semantic_hash            TEXT NOT NULL CHECK (semantic_hash ~ '^[0-9a-f]{64}$'),

    -- Rastreabilidade opcional ao snapshot que observou o fato. Nullable porque
    -- o poll pode detectar o evento entre dois snapshots.
    observed_in_snapshot_id  TEXT REFERENCES public.confenge_live_snapshots(snapshot_id),

    payload                  JSONB NOT NULL DEFAULT '{}'::JSONB,
    consumed_at              TIMESTAMPTZ,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- >>> CHAVE DE IDEMPOTENCIA <<<
    -- Se source_as_of, created_at ou snapshot_id entrassem aqui, cada ciclo de
    -- poll reinseriria o mesmo fato e a idempotencia deixaria de existir.
    UNIQUE (event_type, subject_key, semantic_hash),

    -- Coerencia entre subject_kind e as colunas de conveniencia.
    CHECK (subject_kind <> 'OPPORTUNITY'
           OR (opportunity_key IS NOT NULL AND company_key IS NULL AND subject_key = opportunity_key)),
    CHECK (subject_kind <> 'COMPANY'
           OR (company_key IS NOT NULL AND opportunity_key IS NULL AND subject_key = company_key)),
    CHECK (subject_kind <> 'COMPANY_OPPORTUNITY'
           OR (company_key IS NOT NULL AND opportunity_key IS NOT NULL
               AND subject_key = company_key || '|' || opportunity_key)),

    -- Tipo de evento x sujeito compativel.
    CHECK (
        (event_type IN ('NEW_OPPORTUNITY', 'OPPORTUNITY_CHANGED', 'DEADLINE_CHANGED')
             AND subject_kind = 'OPPORTUNITY')
     OR (event_type = 'COMPANY_PORTFOLIO_CHANGED' AND subject_kind = 'COMPANY')
     OR (event_type = 'FIT_BECAME_RELEVANT'       AND subject_kind = 'COMPANY_OPPORTUNITY')
    ),

    -- Zero PII no payload e nas chaves.
    CHECK (subject_key !~* 'email|telefone|phone|whatsapp|contact'),
    CHECK (payload::TEXT !~* '"(email|telefone|phone|whatsapp|contact_name|client_id)"')
);

CREATE INDEX IF NOT EXISTS confenge_live_events_type_idx
    ON public.confenge_live_events (event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS confenge_live_events_subject_idx
    ON public.confenge_live_events (subject_kind, subject_key, created_at DESC);
CREATE INDEX IF NOT EXISTS confenge_live_events_unconsumed_idx
    ON public.confenge_live_events (created_at)
    WHERE consumed_at IS NULL;

COMMENT ON TABLE public.confenge_live_events IS
'Eventos do motor inbound, idempotentes por UNIQUE(event_type, subject_key, semantic_hash). Populada por poll/CDC — NENHUM trigger e criado nas tabelas do motor outbound.';

COMMENT ON COLUMN public.confenge_live_events.semantic_hash IS
'SHA256 do conteudo material do fato (estado novo + estado anterior nos eventos *_CHANGED). Exclui timestamps de coleta para que recoleta nao gere evento novo.';


-- Control plane proprio do inbound (analogo a confenge_target_fit_control da
-- 071, mas SEPARADO: o inbound nao escreve na tabela de controle do outbound).
CREATE TABLE IF NOT EXISTS public.confenge_live_control (
    key                      TEXT PRIMARY KEY,
    value                    JSONB NOT NULL DEFAULT '{}'::JSONB,
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO public.confenge_live_control (key, value) VALUES
    ('cdc_watermark_bids',      '{"watermark": null, "observed_at": null}'::JSONB),
    ('cdc_watermark_target_fit','{"watermark": null, "observed_at": null}'::JSONB),
    ('cdc_watermark_sector',    '{"watermark": null, "observed_at": null}'::JSONB),
    ('cdc_watermark_contracts', '{"watermark": null, "observed_at": null}'::JSONB),
    ('engine_mode',             '{"mode": "SHADOW"}'::JSONB),
    ('auto_pause',              '{"paused": false, "reason": null}'::JSONB)
ON CONFLICT (key) DO NOTHING;

COMMENT ON TABLE public.confenge_live_control IS
'Control plane do motor inbound. Watermarks de poll por fonte. Aditivo: nao toca confenge_target_fit_control.';


-- Saude da superficie de leitura — TABELA PROPRIA.
-- NAO inserimos em public.public_read_surface_health_internal nem em
-- public_read_v1.query_budgets: essas pertencem ao contrato v1 da 089/090.
CREATE TABLE IF NOT EXISTS public.confenge_live_surface_health_internal (
    view_name                TEXT PRIMARY KEY,
    enabled                  BOOLEAN NOT NULL DEFAULT TRUE,
    refreshed_at             TIMESTAMPTZ,
    last_refresh_status      TEXT NOT NULL DEFAULT 'NEVER'
                                  CHECK (last_refresh_status IN ('NEVER', 'VALID', 'FAILED', 'STALE')),
    last_error               TEXT,
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO public.confenge_live_surface_health_internal (view_name)
VALUES ('current_snapshot'), ('opportunities'), ('companies'), ('company_opportunity_fit'), ('events')
ON CONFLICT (view_name) DO NOTHING;


-- =============================================================================
-- 7. IMUTABILIDADE DO SNAPSHOT FECHADO
--    Triggers criados EXCLUSIVAMENTE em tabelas deste draft.
-- =============================================================================

CREATE OR REPLACE FUNCTION public.guard_closed_confenge_live_snapshot_v1()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    guarded_snapshot_id TEXT;
    guarded_state       TEXT;
BEGIN
    IF current_setting('app.allow_confenge_live_test_cleanup', TRUE) = 'on'
       AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = current_user AND rolsuper) THEN
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;

    -- No header a chave esta em snapshot_id da propria linha; nas tabelas
    -- filhas, na coluna FK de mesmo nome. Mesma normalizacao da 089.
    guarded_snapshot_id := CASE
        WHEN TG_TABLE_NAME = 'confenge_live_snapshots'
            THEN COALESCE(OLD.snapshot_id, NEW.snapshot_id)
        ELSE COALESCE(NEW.snapshot_id, OLD.snapshot_id)
    END;
    SELECT state INTO guarded_state
    FROM public.confenge_live_snapshots
    WHERE snapshot_id = guarded_snapshot_id;

    IF guarded_state IN ('READY_CANONICAL', 'SUPERSEDED')
       AND NOT (
           current_setting('app.confenge_live_snapshot_transition', TRUE) = 'on'
           AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = current_user AND rolsuper)
       ) THEN
        RAISE EXCEPTION 'closed confenge live snapshot % is immutable', guarded_snapshot_id
            USING ERRCODE = '55000';
    END IF;

    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

-- Guarda do PROPRIO header (equivalente a trg_canonical_snapshot_guard da 089).
-- Sem ela, um UPDATE direto poderia reescrever state/content_hash de um
-- snapshot ja READY_CANONICAL — o buraco exato que a imutabilidade fecha.
-- close_confenge_live_snapshot_v1 seta app.confenge_live_snapshot_transition,
-- entao a transicao legitima (inclusive o laco SUPERSEDED) continua passando.
DROP TRIGGER IF EXISTS trg_confenge_live_snapshot_guard ON public.confenge_live_snapshots;
CREATE TRIGGER trg_confenge_live_snapshot_guard
    BEFORE UPDATE OR DELETE ON public.confenge_live_snapshots
    FOR EACH ROW EXECUTE FUNCTION public.guard_closed_confenge_live_snapshot_v1();

DO $$
DECLARE guarded TEXT;
BEGIN
    FOREACH guarded IN ARRAY ARRAY[
        'confenge_live_snapshot_watermarks',
        'confenge_live_opportunity_snapshot',
        'confenge_live_company_snapshot',
        'confenge_live_company_opportunity_fit_snapshot'
    ] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_confenge_live_closed_guard ON public.%I', guarded);
        EXECUTE format(
            'CREATE TRIGGER trg_confenge_live_closed_guard '
            'BEFORE INSERT OR UPDATE OR DELETE ON public.%I '
            'FOR EACH ROW EXECUTE FUNCTION public.guard_closed_confenge_live_snapshot_v1()',
            guarded);
    END LOOP;
END $$;


-- =============================================================================
-- 8. RPCs DE BUILD (begin / watermark / close)
--    Espelham 089 em estrutura; escrevem SOMENTE em tabelas deste draft.
-- =============================================================================

CREATE OR REPLACE FUNCTION public.begin_confenge_live_snapshot_v1(
    p_cutoff_at              TIMESTAMPTZ,
    p_effective_date         DATE,
    p_universe_hash          TEXT,
    p_policy_hash            TEXT,
    p_schema_hash            TEXT,
    p_scoring_hash           TEXT,
    p_opportunity_hash       TEXT,
    p_company_hash           TEXT,
    p_fit_hash               TEXT,
    p_required_source_count  INTEGER,
    p_required_company_count INTEGER,
    p_created_by             TEXT
)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    result_id TEXT;
BEGIN
    IF p_created_by ~* 'client|profile|email|contact' THEN
        RAISE EXCEPTION 'live snapshot creator cannot encode client/contact identity'
            USING ERRCODE = '22023';
    END IF;

    -- Identidade derivada do conteudo: reabrir com as mesmas entradas devolve o
    -- mesmo snapshot_id em vez de criar um duplicado.
    result_id := 'clis_' || encode(digest(concat_ws('|',
        p_cutoff_at::TEXT, p_effective_date::TEXT, p_universe_hash, p_policy_hash,
        p_schema_hash, p_scoring_hash, p_opportunity_hash, p_company_hash, p_fit_hash
    ), 'sha256'), 'hex');

    INSERT INTO public.confenge_live_snapshots (
        snapshot_id, cutoff_at, effective_date, universe_hash, policy_hash,
        schema_hash, scoring_hash, opportunity_hash, company_hash, fit_hash,
        required_source_count, required_company_count, created_by
    ) VALUES (
        result_id, p_cutoff_at, p_effective_date, p_universe_hash, p_policy_hash,
        p_schema_hash, p_scoring_hash, p_opportunity_hash, p_company_hash, p_fit_hash,
        p_required_source_count, p_required_company_count, p_created_by
    ) ON CONFLICT (snapshot_id) DO NOTHING;

    RETURN result_id;
END;
$$;


CREATE OR REPLACE FUNCTION public.put_confenge_live_watermark_v1(
    p_snapshot_id            TEXT,
    p_source                 TEXT,
    p_source_run_id          TEXT,
    p_watermark_at           TIMESTAMPTZ,
    p_freshness_state        TEXT,
    p_completeness_state     TEXT,
    p_applicable_row_count   BIGINT,
    p_evaluated_row_count    BIGINT,
    p_evidence_hash          TEXT,
    p_reason_codes           TEXT[] DEFAULT '{}'
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    cutoff_value TIMESTAMPTZ;
BEGIN
    SELECT cutoff_at INTO STRICT cutoff_value
    FROM public.confenge_live_snapshots
    WHERE snapshot_id = p_snapshot_id AND state IN ('BUILDING', 'BLOCKED')
    FOR UPDATE;

    -- Um watermark posterior ao corte significaria que o snapshot leu o futuro.
    IF p_watermark_at > cutoff_value THEN
        RAISE EXCEPTION 'source watermark is after live snapshot cutoff' USING ERRCODE = '22023';
    END IF;

    INSERT INTO public.confenge_live_snapshot_watermarks (
        snapshot_id, source, source_run_id, watermark_at, freshness_state,
        completeness_state, applicable_row_count, evaluated_row_count,
        evidence_hash, reason_codes
    ) VALUES (
        p_snapshot_id, p_source, p_source_run_id, p_watermark_at, p_freshness_state,
        p_completeness_state, p_applicable_row_count, p_evaluated_row_count,
        p_evidence_hash, p_reason_codes
    ) ON CONFLICT (snapshot_id, source) DO UPDATE SET
        source_run_id        = EXCLUDED.source_run_id,
        watermark_at         = EXCLUDED.watermark_at,
        freshness_state      = EXCLUDED.freshness_state,
        completeness_state   = EXCLUDED.completeness_state,
        applicable_row_count = EXCLUDED.applicable_row_count,
        evaluated_row_count  = EXCLUDED.evaluated_row_count,
        evidence_hash        = EXCLUDED.evidence_hash,
        reason_codes         = EXCLUDED.reason_codes,
        recorded_at          = NOW();
END;
$$;


CREATE OR REPLACE FUNCTION public.close_confenge_live_snapshot_v1(p_snapshot_id TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO public, pg_temp
AS $$
DECLARE
    snapshot_row public.confenge_live_snapshots%ROWTYPE;
    blocker_list JSONB := '[]'::JSONB;
    watermark_count INTEGER;
    company_count   INTEGER;
    opportunity_count INTEGER;
    fit_count       INTEGER;
    result_hash     TEXT;
    prior_id        TEXT;
BEGIN
    SELECT * INTO STRICT snapshot_row FROM public.confenge_live_snapshots
    WHERE snapshot_id = p_snapshot_id FOR UPDATE;

    IF snapshot_row.state = 'READY_CANONICAL' THEN
        RETURN jsonb_build_object('snapshot_id', p_snapshot_id, 'state', snapshot_row.state,
                                  'content_hash', snapshot_row.content_hash,
                                  'blockers', snapshot_row.blockers);
    END IF;

    SELECT count(*) INTO watermark_count
    FROM public.confenge_live_snapshot_watermarks WHERE snapshot_id = p_snapshot_id;
    SELECT count(*) INTO company_count
    FROM public.confenge_live_company_snapshot WHERE snapshot_id = p_snapshot_id;
    SELECT count(*) INTO opportunity_count
    FROM public.confenge_live_opportunity_snapshot WHERE snapshot_id = p_snapshot_id;
    SELECT count(*) INTO fit_count
    FROM public.confenge_live_company_opportunity_fit_snapshot WHERE snapshot_id = p_snapshot_id;

    IF watermark_count < snapshot_row.required_source_count THEN
        blocker_list := blocker_list || '"missing_source_watermarks"'::JSONB;
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.confenge_live_snapshot_watermarks
        WHERE snapshot_id = p_snapshot_id
          AND (freshness_state <> 'FRESH'
               OR completeness_state <> 'COMPLETE'
               OR evaluated_row_count < applicable_row_count)
    ) THEN
        blocker_list := blocker_list || '"source_freshness_or_completeness_failed"'::JSONB;
    END IF;
    IF company_count < snapshot_row.required_company_count THEN
        blocker_list := blocker_list || '"companies_not_materialized"'::JSONB;
    END IF;
    IF opportunity_count = 0 THEN
        blocker_list := blocker_list || '"no_opportunities_materialized"'::JSONB;
    END IF;
    IF fit_count = 0 THEN
        blocker_list := blocker_list || '"no_fit_rows_materialized"'::JSONB;
    END IF;

    PERFORM set_config('app.confenge_live_snapshot_transition', 'on', TRUE);

    IF blocker_list <> '[]'::JSONB THEN
        UPDATE public.confenge_live_snapshots
        SET state = 'BLOCKED', blockers = blocker_list
        WHERE snapshot_id = p_snapshot_id;
        PERFORM set_config('app.confenge_live_snapshot_transition', 'off', TRUE);
        RETURN jsonb_build_object('snapshot_id', p_snapshot_id, 'state', 'BLOCKED',
                                  'blockers', blocker_list);
    END IF;

    -- content_hash = funcao de TODO o conteudo congelado. Dois snapshots com o
    -- mesmo content_hash sao intercambiaveis para qualquer consumidor.
    SELECT encode(digest(concat_ws('|',
        snapshot_row.snapshot_id, snapshot_row.universe_hash, snapshot_row.policy_hash,
        snapshot_row.schema_hash, snapshot_row.scoring_hash, snapshot_row.opportunity_hash,
        snapshot_row.company_hash, snapshot_row.fit_hash,
        COALESCE((SELECT string_agg(source || ':' || source_run_id || ':' || watermark_at::TEXT || ':' || evidence_hash, ',' ORDER BY source)
                  FROM public.confenge_live_snapshot_watermarks WHERE snapshot_id = p_snapshot_id), ''),
        COALESCE((SELECT string_agg(opportunity_key || ':' || semantic_hash, ',' ORDER BY opportunity_key)
                  FROM public.confenge_live_opportunity_snapshot WHERE snapshot_id = p_snapshot_id), ''),
        COALESCE((SELECT string_agg(company_key || ':' || semantic_hash, ',' ORDER BY company_key)
                  FROM public.confenge_live_company_snapshot WHERE snapshot_id = p_snapshot_id), ''),
        COALESCE((SELECT string_agg(company_key || '|' || opportunity_key || ':' || semantic_hash,
                                    ',' ORDER BY company_key, opportunity_key)
                  FROM public.confenge_live_company_opportunity_fit_snapshot WHERE snapshot_id = p_snapshot_id), '')
    ), 'sha256'), 'hex') INTO result_hash;

    UPDATE public.confenge_live_snapshots
    SET state = 'READY_CANONICAL', blockers = '[]'::JSONB,
        content_hash = result_hash, closed_at = NOW()
    WHERE snapshot_id = p_snapshot_id;

    -- Transicao SUPERSEDED explicita: o snapshot READY anterior (cutoff menor)
    -- passa a apontar para este. A 089 nunca definiu esta transicao.
    FOR prior_id IN
        SELECT snapshot_id FROM public.confenge_live_snapshots
        WHERE state = 'READY_CANONICAL'
          AND snapshot_id <> p_snapshot_id
          AND cutoff_at < snapshot_row.cutoff_at
    LOOP
        UPDATE public.confenge_live_snapshots
        SET state = 'SUPERSEDED', superseded_at = NOW(), superseded_by = p_snapshot_id
        WHERE snapshot_id = prior_id;
    END LOOP;

    UPDATE public.confenge_live_surface_health_internal
    SET refreshed_at = NOW(), last_refresh_status = 'VALID', last_error = NULL, updated_at = NOW()
    WHERE enabled;

    PERFORM set_config('app.confenge_live_snapshot_transition', 'off', TRUE);

    RETURN jsonb_build_object('snapshot_id', p_snapshot_id, 'state', 'READY_CANONICAL',
                              'content_hash', result_hash, 'blockers', '[]'::JSONB);
END;
$$;

REVOKE ALL ON FUNCTION public.close_confenge_live_snapshot_v1(TEXT) FROM PUBLIC;


-- =============================================================================
-- 9. SUPERFICIE SELECT-ONLY (padrao das migrations 089/090)
-- =============================================================================

CREATE OR REPLACE VIEW confenge_live_v1.current_snapshot AS
SELECT snapshot.snapshot_id,
       snapshot.cutoff_at AS as_of,
       snapshot.effective_date,
       snapshot.content_hash,
       snapshot.universe_hash, snapshot.policy_hash, snapshot.schema_hash,
       snapshot.scoring_hash, snapshot.opportunity_hash, snapshot.company_hash,
       snapshot.fit_hash, snapshot.closed_at,
       CASE
           WHEN EXISTS (
               SELECT 1 FROM public.confenge_live_snapshot_watermarks watermark
               WHERE watermark.snapshot_id = snapshot.snapshot_id
                 AND (watermark.completeness_state <> 'COMPLETE' OR watermark.freshness_state <> 'FRESH')
           ) THEN 'INCOMPLETE'
           WHEN NOT EXISTS (
               SELECT 1 FROM public.confenge_live_snapshot_watermarks watermark
               WHERE watermark.snapshot_id = snapshot.snapshot_id
           ) THEN 'UNKNOWN'
           ELSE 'COMPLETE'
       END AS completeness,
       jsonb_build_object('snapshot_id', snapshot.snapshot_id,
                          'content_hash', snapshot.content_hash) AS provenance
FROM public.confenge_live_snapshots snapshot
WHERE snapshot.state = 'READY_CANONICAL'
ORDER BY snapshot.cutoff_at DESC, snapshot.snapshot_id DESC
LIMIT 1;

CREATE OR REPLACE VIEW confenge_live_v1.opportunities AS
SELECT opportunity.opportunity_key, opportunity.objeto, opportunity.valor_estimado,
       opportunity.modalidade_id, opportunity.modalidade, opportunity.esfera_id,
       opportunity.uf, opportunity.municipio, opportunity.codigo_ibge,
       opportunity.orgao_cnpj, opportunity.orgao_nome,
       opportunity.data_publicacao, opportunity.data_abertura, opportunity.data_encerramento,
       opportunity.link_edital, opportunity.openness_state,
       opportunity.source, opportunity.source_as_of,
       opportunity.reason_codes,
       snapshot.as_of, snapshot.completeness,
       jsonb_build_object('snapshot_id', snapshot.snapshot_id,
                          'semantic_hash', opportunity.semantic_hash,
                          'source', opportunity.source,
                          'source_id', opportunity.source_id) AS provenance
FROM confenge_live_v1.current_snapshot snapshot
JOIN public.confenge_live_opportunity_snapshot opportunity USING (snapshot_id);

CREATE OR REPLACE VIEW confenge_live_v1.companies AS
SELECT company.company_key, company.cnpj_raiz,
       company.target_fit_class, company.target_fit_confidence, company.target_fit_version,
       company.sector_class, company.sector_confidence, company.sector_version,
       company.portfolio_contract_count, company.portfolio_total_value,
       company.portfolio_last_award_at, company.portfolio_uf_coverage,
       company.inbound_eligibility, company.source_as_of, company.reason_codes,
       snapshot.as_of, snapshot.completeness,
       jsonb_build_object('snapshot_id', snapshot.snapshot_id,
                          'semantic_hash', company.semantic_hash) AS provenance
FROM confenge_live_v1.current_snapshot snapshot
JOIN public.confenge_live_company_snapshot company USING (snapshot_id);

CREATE OR REPLACE VIEW confenge_live_v1.company_opportunity_fit AS
SELECT fit.company_key, fit.opportunity_key, fit.fit_class, fit.fit_score,
       fit.fit_version, fit.scorer_sha256,
       fit.sector_signal, fit.geo_signal, fit.value_signal, fit.deadline_signal,
       fit.evidence, fit.reason_codes, fit.source_as_of,
       snapshot.as_of, snapshot.completeness,
       jsonb_build_object('snapshot_id', snapshot.snapshot_id,
                          'semantic_hash', fit.semantic_hash) AS provenance
FROM confenge_live_v1.current_snapshot snapshot
JOIN public.confenge_live_company_opportunity_fit_snapshot fit USING (snapshot_id);

-- Eventos expostos SEM payload livre: payload pode carregar campos futuros nao
-- auditados. A superficie publica expoe apenas o contrato estavel.
CREATE OR REPLACE VIEW confenge_live_v1.events AS
SELECT event.event_id, event.event_type, event.subject_kind, event.subject_key,
       event.company_key, event.opportunity_key, event.reason_codes,
       event.source_as_of, event.semantic_hash, event.created_at,
       jsonb_build_object('observed_in_snapshot_id', event.observed_in_snapshot_id) AS provenance
FROM public.confenge_live_events event;

CREATE OR REPLACE VIEW confenge_live_v1.surface_health AS
SELECT health.view_name, health.enabled, health.refreshed_at,
       health.last_refresh_status, health.last_error,
       snapshot.snapshot_id, snapshot.as_of
FROM public.confenge_live_surface_health_internal health
LEFT JOIN confenge_live_v1.current_snapshot snapshot ON TRUE;

-- Orcamentos de query PROPRIOS (nao inserimos em public_read_v1.query_budgets,
-- que pertence ao contrato v1 publicado da 089).
CREATE TABLE IF NOT EXISTS confenge_live_v1.query_budgets (
    query_family             TEXT PRIMARY KEY,
    statement_timeout_ms     INTEGER NOT NULL,
    p95_budget_ms            INTEGER NOT NULL,
    max_rows                 INTEGER NOT NULL,
    representative_query     TEXT NOT NULL
);

INSERT INTO confenge_live_v1.query_budgets VALUES
    ('opportunities_by_uf', 3000, 400, 500,
     'SELECT * FROM confenge_live_v1.opportunities WHERE uf = $1 LIMIT 500'),
    ('fit_by_company', 3000, 400, 500,
     'SELECT * FROM confenge_live_v1.company_opportunity_fit WHERE company_key = $1 LIMIT 500'),
    ('events_unconsumed', 2000, 250, 500,
     'SELECT * FROM confenge_live_v1.events WHERE event_type = $1 ORDER BY created_at DESC LIMIT 500')
ON CONFLICT (query_family) DO UPDATE SET
    statement_timeout_ms = EXCLUDED.statement_timeout_ms,
    p95_budget_ms        = EXCLUDED.p95_budget_ms,
    max_rows             = EXCLUDED.max_rows,
    representative_query = EXCLUDED.representative_query;


-- -----------------------------------------------------------------------------
-- 9b. Role de leitura DEDICADA
--     NAO reutilizamos smartlic_public_reader: aquele papel carrega um contrato
--     publicado (public_read_v1.contract_releases v1.0.0, janela de depreciacao
--     de 180 dias). Ampliar o alcance dele nao seria aditivo — seria mudar um
--     contrato ja publicado. Role nova = superficie nova, versionavel a parte.
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'confenge_live_intel_reader') THEN
        CREATE ROLE confenge_live_intel_reader
            NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION;
        COMMENT ON ROLE confenge_live_intel_reader IS 'managed-by-extra-migration-110';
    END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO confenge_live_intel_reader', current_database());
    EXECUTE format('GRANT confenge_live_intel_reader TO %I', current_user);
END $$;

ALTER ROLE confenge_live_intel_reader SET statement_timeout = '3s';
ALTER ROLE confenge_live_intel_reader SET lock_timeout = '500ms';
ALTER ROLE confenge_live_intel_reader SET idle_in_transaction_session_timeout = '5s';
ALTER ROLE confenge_live_intel_reader SET default_transaction_read_only = 'on';

-- Superficie minima: SOMENTE o schema versionado.
REVOKE ALL ON SCHEMA public FROM confenge_live_intel_reader;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM confenge_live_intel_reader;
GRANT USAGE ON SCHEMA confenge_live_v1 TO confenge_live_intel_reader;

-- ATENCAO (licao que originou a propria migration 090): "GRANT ... ON ALL
-- TABLES IN SCHEMA" so cobre objetos EXISTENTES no momento do GRANT. Toda view
-- nova criada depois precisa de GRANT explicito — ou de uma migration de lock
-- equivalente a 090. ALTER DEFAULT PRIVILEGES abaixo cobre o caso futuro.
GRANT SELECT ON ALL TABLES IN SCHEMA confenge_live_v1 TO confenge_live_intel_reader;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON ALL TABLES IN SCHEMA confenge_live_v1 FROM confenge_live_intel_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA confenge_live_v1
    GRANT SELECT ON TABLES TO confenge_live_intel_reader;

-- EXECUTE em PUBLIC e o DEFAULT do PostgreSQL e NAO e removido por
-- "REVOKE ALL ON SCHEMA public". Sem o bloco abaixo, o leitor poderia chamar as
-- RPCs de escrita mesmo com default_transaction_read_only (SECURITY DEFINER).
DO $$
DECLARE writer REGPROCEDURE;
BEGIN
    FOREACH writer IN ARRAY ARRAY[
        'public.begin_confenge_live_snapshot_v1(TIMESTAMPTZ, DATE, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, INTEGER, INTEGER, TEXT)'::REGPROCEDURE,
        'public.put_confenge_live_watermark_v1(TEXT, TEXT, TEXT, TIMESTAMPTZ, TEXT, TEXT, BIGINT, BIGINT, TEXT, TEXT[])'::REGPROCEDURE,
        'public.close_confenge_live_snapshot_v1(TEXT)'::REGPROCEDURE
    ] LOOP
        EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC', writer);
        EXECUTE format('REVOKE ALL ON FUNCTION %s FROM confenge_live_intel_reader', writer);
    END LOOP;
END $$;

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM confenge_live_intel_reader;
REVOKE ALL ON ALL TABLES  IN SCHEMA public FROM confenge_live_intel_reader;
REVOKE USAGE ON SCHEMA public FROM confenge_live_intel_reader;

COMMIT;

-- =============================================================================
-- ROLLBACK (comentado; padrao das migrations 030-036 deste repo)
-- Seguro porque NENHUM objeto pre-existente foi alterado.
-- -----------------------------------------------------------------------------
-- BEGIN;
-- DROP VIEW  IF EXISTS confenge_live_v1.surface_health;
-- DROP VIEW  IF EXISTS confenge_live_v1.events;
-- DROP VIEW  IF EXISTS confenge_live_v1.company_opportunity_fit;
-- DROP VIEW  IF EXISTS confenge_live_v1.companies;
-- DROP VIEW  IF EXISTS confenge_live_v1.opportunities;
-- DROP VIEW  IF EXISTS confenge_live_v1.current_snapshot;
-- DROP TABLE IF EXISTS confenge_live_v1.query_budgets;
-- DROP TABLE IF EXISTS public.confenge_live_company_opportunity_fit_snapshot;
-- DROP TABLE IF EXISTS public.confenge_live_company_snapshot;
-- DROP TABLE IF EXISTS public.confenge_live_opportunity_snapshot;
-- DROP TABLE IF EXISTS public.confenge_live_snapshot_watermarks;
-- DROP TABLE IF EXISTS public.confenge_live_events;
-- DROP TABLE IF EXISTS public.confenge_live_control;
-- DROP TABLE IF EXISTS public.confenge_live_surface_health_internal;
-- DROP TABLE IF EXISTS public.confenge_live_snapshots;
-- DROP FUNCTION IF EXISTS public.close_confenge_live_snapshot_v1(TEXT);
-- DROP FUNCTION IF EXISTS public.put_confenge_live_watermark_v1(TEXT, TEXT, TEXT, TIMESTAMPTZ, TEXT, TEXT, BIGINT, BIGINT, TEXT, TEXT[]);
-- DROP FUNCTION IF EXISTS public.begin_confenge_live_snapshot_v1(TIMESTAMPTZ, DATE, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, INTEGER, INTEGER, TEXT);
-- DROP FUNCTION IF EXISTS public.guard_closed_confenge_live_snapshot_v1();
-- DROP FUNCTION IF EXISTS public.confenge_live_open_opportunities_as_of(DATE);
-- DROP SCHEMA IF EXISTS confenge_live_v1;
-- DROP ROLE  IF EXISTS confenge_live_intel_reader;
-- COMMIT;
-- =============================================================================
--
-- DECISOES ABERTAS PARA @architect / @po (ver resumo do handoff)
--  1. Replay as-of e congelado por snapshot; replay temporal completo exige
--     historico append-only de pncp_raw_bids (escopo proprio).
--  2. reason_codes usa TEXT[] (familia 089) e nao JSONB (familia 071/072).
--     Divergencia deliberada; se o @architect preferir JSONB, os CHECKs de
--     "UNKNOWN exige razao" precisam virar jsonb_array_length(...) > 0.
--  3. Estado BLOCKED adicionado alem dos 3 estados do handoff.
--  4. Role de leitura nova (confenge_live_intel_reader) em vez de estender
--     smartlic_public_reader.
--  5. As views de confenge_live_v1 NAO tem kill switch. As familias da 089/090
--     sao gateadas por public_read_v1.access_gate sobre
--     public.truth_plane_kill_switch. Reusar aquele switch acoplaria o motor
--     inbound ao kill switch do outbound (um desliga o outro) — decisao que
--     nao cabe ao @data-engineer tomar sozinho. Alternativa: switch proprio em
--     confenge_live_control. Aguardando @architect.
-- =============================================================================
