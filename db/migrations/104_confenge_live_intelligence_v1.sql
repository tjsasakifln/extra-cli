-- 104_confenge_live_intelligence_v1.sql
-- CONFENGE_LIVE_INTELLIGENCE/1.0 — fundação de schema do motor INBOUND (LI-2).
--
-- Story:      docs/stories/story-confenge-live-intelligence-01.md (v1.2, Ready)
-- Normativo:  docs/architecture/confenge-live-intelligence-impact-analysis.md
--             (Decisões 2, 3, 4, 6, 7, 8 — §8.2, §8.3, §8.4)
-- Owner DDL:  @data-engineer (autoridade exclusiva sobre schema/DDL)
--
-- ============================================================================
-- ADITIVIDADE (AC1) — esta migration NÃO executa ALTER, DROP ou
-- CREATE OR REPLACE sobre nenhum objeto outbound. Objetos protegidos:
--   opportunity_intel*            confenge_company_target_fit_current
--   confenge_target_fit_dirty     confenge_company_target_fit_history
--   confenge_target_fit_events    confenge_target_fit_shadow
--   pncp_supplier_contracts       canonical_public_snapshots
--   canonical_snapshot_*          canonical_public_events_v1
--   v_open_opportunities_canonical  v_contracts_canonical_v2
--   pncp_raw_bids                 sc_public_entities
--   confenge_company_sector_current / _history
-- Todo acesso a esses objetos aqui é SELECT (corpo da função as-of).
--
-- ★ NOTA PARA O TESTE ESTÁTICO DE AC1: a asserção deve ser *por statement*,
--   não por arquivo. O corpo de public.live_open_opportunities_as_of(DATE)
--   legitimamente nomeia pncp_raw_bids e sc_public_entities em um SELECT, e
--   este arquivo contém DROP/ALTER aplicados exclusivamente a objetos NOVOS
--   (DROP FUNCTION da própria função as-of; ALTER ROLE do role novo). Um
--   teste por arquivo produziria falso positivo.
--   Deliberadamente NÃO usamos "CREATE OR REPLACE FUNCTION" para a função
--   as-of: o par DROP IF EXISTS + CREATE mantém idempotência sem colocar o
--   token proibido na mesma sentença que nomeia tabelas outbound.
--
-- ============================================================================
-- ROLLBACK (comando único, executável):
--
--   psql "$LOCAL_DATALAKE_DSN" -f db/rollback/104_confenge_live_intelligence_v1_rollback.sql
--
-- O rollback reverte, além dos objetos, o role confenge_live_intel_reader —
-- pg_roles NÃO é afetado por DROP TABLE; o rollback executa DROP OWNED BY +
-- DROP ROLE, condicionado ao marcador COMMENT ON ROLE
-- 'managed-by-extra-migration-104'.
-- Esta migration NÃO grava nenhuma entrada em pg_default_acl (ver nota sobre
-- ALTER DEFAULT PRIVILEGES abaixo), logo o rollback nada tem a reverter lá.
-- Critério de aceite do rollback: pg_default_acl sem entradas desta migration
-- e \dp public idêntico ao estado pré-104; reaplicar a 104 depois funciona.
--
-- ============================================================================
-- BARREIRA DE SEGURANÇA (§8.3 / AC3)
-- Achado do @architect, tratado aqui como requisito: os REVOKE de
-- 090_public_read_select_only_lock.sql usam ALL TABLES / ALL FUNCTIONS IN
-- SCHEMA public, que se aplicam apenas aos objetos existentes no momento da
-- execução. Não há EVENT TRIGGER reaplicando a barreira. Portanto todo objeto
-- criado aqui recebe REVOKE explícito para PUBLIC e para smartlic_public_reader
-- imediatamente após o CREATE.
--
-- ★ PRÉ-CONDIÇÃO: os REVOKE literais abaixo exigem que o role
--   smartlic_public_reader exista (criado por 089). A ordem de aplicação
--   (089 < 104) garante isso; "role does not exist" NÃO está em
--   _REPAIRABLE_MARKERS de apply_migrations.py, então um banco com 089 marcado
--   como aplicado pelo caminho de reparo, sem o role, falharia aqui — falha
--   alta e visível, que é o comportamento desejado. Os REVOKE permanecem
--   literais (e não dentro de DO/format) para que o teste estático de AC3
--   consiga ver o nome de cada objeto no texto do arquivo.
--
-- ★ ATENÇÃO — funções e tabelas têm defaults diferentes: FUNCTIONS concedem
--   EXECUTE a PUBLIC por padrão; TABLES não concedem nada. Logo o
--   "REVOKE ALL ON FUNCTION ... FROM PUBLIC" abaixo é carga útil real, não
--   defensivo.
--
-- ★ ALTER DEFAULT PRIVILEGES REMOVIDO (@data-engineer, ratificando achado do
--   @dev contra PostgreSQL 16.15). A §9 anterior emitia, escopada FOR ROLE
--   current_user:
--     REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC
--     REVOKE ALL ON TABLES    FROM smartlic_public_reader
--     REVOKE ALL ON FUNCTIONS FROM smartlic_public_reader
--   As TRÊS foram medidas e são INERTES. MEDIDO em PostgreSQL 16.15, tanto na
--   forma DO/format quanto em statement literal: após os três statements,
--   pg_default_acl continua com 0 linhas em 'public', e uma função criada
--   DEPOIS nasce com proacl NULL — ou seja, PUBLIC continua com EXECUTE
--   (has_function_privilege('public', ..., 'EXECUTE') = true). Controle de
--   sensibilidade do probe: um REVOKE explícito na função criada inverte o
--   resultado para false, então o instrumento não é cego. O mesmo probe mostra
--   que o GRANT inverso GRAVA linha ({=X/owner}) — assimetria que fazia o
--   rollback criar o resíduo que ele mesmo proíbe (ver §3 do rollback).
--   ★ O que está provado é o EFEITO, não o mecanismo interno do PostgreSQL:
--   a causa exata (provável leitura da ACL armazenada, e não do default
--   embutido) NÃO foi determinada e a documentação oficial sugere o contrário.
--   Não tratar a explicação como fato; tratar a medição como fato.
--
--   Não foi reformulado para uma variante ativa. A única formulação que
--   funcionaria no PG16 é gravar linha positiva (GRANT ... TO <owner>), que
--   SUBSTITUI o default embutido e removeria EXECUTE de PUBLIC em TODA função
--   futura criada por este role em public — inclusive de migrations não
--   relacionadas. Efeito colateral fora do escopo de LI-2 e contrário a AC3.
--
--   A barreira real, provada por teste, são os REVOKE explícitos por objeto
--   (6 tabelas + 1 função, para PUBLIC e para smartlic_public_reader) — 14
--   statements literais acima. R1 permanece integralmente mitigado por eles.
--   AC3 (2ª parte) é uma condicional ("QUANDO a 104 adicionar ALTER DEFAULT
--   PRIVILEGES, ENTÃO deve ser escopada por role"): sem o antecedente, ela é
--   satisfeita de forma vacuosa e nenhum objeto de role futura é afetado.
--
-- ============================================================================
-- ESCOPO — objetos criados (§8.2, lista fechada):
--   confenge_live_intelligence_snapshots
--   confenge_live_intelligence_source_watermarks
--   confenge_live_intelligence_opportunities
--   confenge_live_intelligence_companies
--   confenge_live_intelligence_fit
--   confenge_live_intelligence_events        (nasce vazia; story 2 popula)
--   live_open_opportunities_as_of(DATE)
--   role confenge_live_intel_reader
--
-- NÃO criado deliberadamente (fora da lista fechada de §8.2 — não inventar
-- escopo): RPCs begin_/put_watermark_/close_snapshot e trigger de
-- imutabilidade pós-fechamento. Esses são padrões do schema-draft.sql, que a
-- story classifica como referência de engenharia, não como contrato. A máquina
-- de estados é aplicada por CHECK estrutural + producer.py (LI-6).
--
-- DECISÕES REGISTRADAS (AC12):
--   (a) reason_codes = TEXT[] — família 089 (canonical_snapshot_dossiers usa
--       TEXT[]). Consistência interna do motor; não misturar com o JSONB de
--       071/072. blockers permanece JSONB por espelhamento literal de 089.
--   (b) role de leitura NOVO: confenge_live_intel_reader. smartlic_public_reader
--       NÃO é reusado — ele tem contrato v1 publicado (public_read_v1, janela de
--       depreciação de 180 dias) e recebe REVOKE explícito sobre todo objeto
--       desta migration.
-- ============================================================================

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

-- ---------------------------------------------------------------------------
-- 1. HEADER DO SNAPSHOT — máquina de estados (Decisão 7, §8.2)
--    BUILDING → BLOCKED | PARTIAL | READY_CANONICAL → SUPERSEDED
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.confenge_live_intelligence_snapshots (
    snapshot_id                 TEXT PRIMARY KEY,
    engine_id                   TEXT NOT NULL DEFAULT 'CONFENGE_LIVE_INTELLIGENCE'
                                     CHECK (engine_id = 'CONFENGE_LIVE_INTELLIGENCE'),
    engine_version              TEXT NOT NULL,
    schema_version              TEXT NOT NULL,

    -- Determinismo temporal (Decisão 6 + §8.4): as_of_date é dia civil.
    as_of_date                  DATE NOT NULL,
    cutoff_at                   TIMESTAMPTZ NOT NULL,
    cutoff_timezone             TEXT NOT NULL DEFAULT 'America/Sao_Paulo'
                                     CHECK (cutoff_timezone = 'America/Sao_Paulo'),

    -- Ponto de troca do #531 (Decisão 7, §7.3): versão do resolver de data.
    date_resolver_version       TEXT NOT NULL,

    -- Hashes: canonical-JSON + SHA256 (Decisão 2). Mesmo CHECK de 089.
    universe_hash               TEXT NOT NULL CHECK (universe_hash ~ '^[0-9a-f]{64}$'),
    policy_hash                 TEXT NOT NULL CHECK (policy_hash ~ '^[0-9a-f]{64}$'),
    schema_hash                 TEXT NOT NULL CHECK (schema_hash ~ '^[0-9a-f]{64}$'),
    data_hash                   TEXT NOT NULL CHECK (data_hash ~ '^[0-9a-f]{64}$'),
    fit_hash                    TEXT NOT NULL CHECK (fit_hash ~ '^[0-9a-f]{64}$'),
    content_hash                TEXT CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),

    state                       TEXT NOT NULL DEFAULT 'BUILDING'
                                     CHECK (state IN ('BUILDING', 'BLOCKED', 'PARTIAL',
                                                      'READY_CANONICAL', 'SUPERSEDED')),

    -- Completude por linha com exclusão contada (Decisão 7, §7.2).
    observed_opportunity_count  INTEGER NOT NULL DEFAULT 0 CHECK (observed_opportunity_count >= 0),
    excluded_opportunity_count  INTEGER NOT NULL DEFAULT 0 CHECK (excluded_opportunity_count >= 0),
    observed_company_count      INTEGER NOT NULL DEFAULT 0 CHECK (observed_company_count >= 0),
    excluded_company_count      INTEGER NOT NULL DEFAULT 0 CHECK (excluded_company_count >= 0),

    blockers                    JSONB NOT NULL DEFAULT '[]'::JSONB,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at                   TIMESTAMPTZ,
    superseded_at               TIMESTAMPTZ,
    created_by                  TEXT NOT NULL,

    -- ★ Guarda estrutural cobrindo AMBOS os estados terminais (§8.2 / R14).
    -- "PARTIAL com blockers" e "PARTIAL sem content_hash" ficam estruturalmente
    -- impossíveis, não apenas proibidos em prosa (§7.2.1).
    CONSTRAINT chk_live_intel_terminal_state_sealed CHECK (
        state NOT IN ('READY_CANONICAL', 'PARTIAL')
        OR (closed_at IS NOT NULL AND content_hash IS NOT NULL AND blockers = '[]'::JSONB)
    ),
    -- READY_CANONICAL exige zero exclusões (§7.2).
    CONSTRAINT chk_live_intel_ready_has_no_exclusion CHECK (
        state <> 'READY_CANONICAL'
        OR (excluded_opportunity_count = 0 AND excluded_company_count = 0)
    ),
    -- PARTIAL exige ao menos uma exclusão declarada (§7.2).
    CONSTRAINT chk_live_intel_partial_has_exclusion CHECK (
        state <> 'PARTIAL'
        OR (excluded_opportunity_count > 0 OR excluded_company_count > 0)
    ),
    -- BLOCKED é fail-closed: exige blockers não vazio (§7.2, lista fechada).
    CONSTRAINT chk_live_intel_blocked_has_blockers CHECK (
        state <> 'BLOCKED' OR blockers <> '[]'::JSONB
    ),
    CONSTRAINT chk_live_intel_superseded_has_timestamp CHECK (
        state <> 'SUPERSEDED' OR superseded_at IS NOT NULL
    )
);

REVOKE ALL ON TABLE public.confenge_live_intelligence_snapshots FROM PUBLIC;
REVOKE ALL ON TABLE public.confenge_live_intelligence_snapshots FROM smartlic_public_reader;

CREATE INDEX IF NOT EXISTS idx_live_intel_snapshots_consumable
    ON public.confenge_live_intelligence_snapshots (as_of_date DESC, snapshot_id)
    WHERE state IN ('READY_CANONICAL', 'PARTIAL');

COMMENT ON TABLE public.confenge_live_intelligence_snapshots IS
    'CONFENGE_LIVE_INTELLIGENCE/1.0 snapshot header. PARTIAL e READY_CANONICAL sao ambos terminais e consumiveis (impact-analysis 7.2.1).';

-- ---------------------------------------------------------------------------
-- 2. WATERMARKS POR FONTE — espelha canonical_snapshot_source_watermarks (089)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.confenge_live_intelligence_source_watermarks (
    snapshot_id             TEXT NOT NULL
                                 REFERENCES public.confenge_live_intelligence_snapshots(snapshot_id),
    source                  TEXT NOT NULL,
    source_run_id           TEXT NOT NULL,
    watermark_at            TIMESTAMPTZ NOT NULL,
    freshness_state         TEXT NOT NULL
                                 CHECK (freshness_state IN ('FRESH', 'STALE', 'FAILED', 'BLOCKED', 'UNKNOWN')),
    completeness_state      TEXT NOT NULL
                                 CHECK (completeness_state IN ('COMPLETE', 'INCOMPLETE', 'UNKNOWN')),
    evidence_hash           TEXT NOT NULL CHECK (evidence_hash ~ '^[0-9a-f]{64}$'),
    reason_codes            TEXT[] NOT NULL DEFAULT '{}',
    recorded_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (snapshot_id, source)
);

REVOKE ALL ON TABLE public.confenge_live_intelligence_source_watermarks FROM PUBLIC;
REVOKE ALL ON TABLE public.confenge_live_intelligence_source_watermarks FROM smartlic_public_reader;

-- ---------------------------------------------------------------------------
-- 3. OPPORTUNITY (Decisão 3, §3.1)
--    UNKNOWN e explicito e tipado: nunca NULL implicito, nunca '', nunca 0.
--    Sem PII/contato: nenhum campo de e-mail, telefone, nome de pessoa,
--    cargo ou perfil social (whitelist de campos — AC10).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.confenge_live_intelligence_opportunities (
    snapshot_id             TEXT NOT NULL
                                 REFERENCES public.confenge_live_intelligence_snapshots(snapshot_id),
    opportunity_id          TEXT NOT NULL,

    objeto                  TEXT,
    objeto_state            TEXT NOT NULL CHECK (objeto_state IN ('OBSERVED', 'UNKNOWN')),

    valor_estimado_brl      NUMERIC(18,2),
    valor_state             TEXT NOT NULL CHECK (valor_state IN ('OBSERVED', 'UNKNOWN')),
    -- Faixa ordinal versionada (Decisão 4). NAO participa de aritmetica.
    valor_band              TEXT CHECK (valor_band IS NULL
                                        OR valor_band IN ('ATE_100K', '100K_1M', '1M_10M', 'ACIMA_10M')),

    modalidade_id           TEXT,
    modalidade              TEXT,
    modalidade_state        TEXT NOT NULL CHECK (modalidade_state IN ('OBSERVED', 'UNKNOWN')),

    uf                      TEXT CHECK (uf IS NULL OR uf ~ '^[A-Z]{2}$'),
    municipio               TEXT,
    codigo_ibge             TEXT,
    geo_state               TEXT NOT NULL CHECK (geo_state IN ('OBSERVED', 'UNKNOWN')),

    orgao_cnpj              TEXT CHECK (orgao_cnpj IS NULL OR orgao_cnpj ~ '^[0-9]{14}$'),
    orgao_nome              TEXT,
    orgao_state             TEXT NOT NULL CHECK (orgao_state IN ('OBSERVED', 'UNKNOWN')),

    data_publicacao         DATE,
    data_encerramento       DATE,
    deadline_state          TEXT NOT NULL CHECK (deadline_state IN ('OPEN', 'CLOSED', 'UNKNOWN')),

    link_edital             TEXT,
    source                  TEXT NOT NULL,
    source_id               TEXT,
    source_as_of            TIMESTAMPTZ NOT NULL,

    -- Completude por linha (§7.2): linhas excluidas permanecem visiveis e contadas.
    row_completeness_state  TEXT NOT NULL DEFAULT 'COMPLETE'
                                 CHECK (row_completeness_state IN ('COMPLETE', 'EXCLUDED_INCOMPLETE')),
    exclusion_reason_codes  TEXT[] NOT NULL DEFAULT '{}',
    reason_codes            TEXT[] NOT NULL DEFAULT '{}',

    opportunity_hash        TEXT NOT NULL CHECK (opportunity_hash ~ '^[0-9a-f]{64}$'),
    recorded_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (snapshot_id, opportunity_id),
    -- Exclusao sem motivo declarado e descarte silencioso: proibido.
    CONSTRAINT chk_live_intel_oppty_exclusion_justified CHECK (
        (row_completeness_state = 'COMPLETE' AND cardinality(exclusion_reason_codes) = 0)
        OR (row_completeness_state = 'EXCLUDED_INCOMPLETE' AND cardinality(exclusion_reason_codes) > 0)
    ),
    -- UNKNOWN tipado exige reason_code (nunca ausencia muda).
    CONSTRAINT chk_live_intel_oppty_unknown_has_reason CHECK (
        (objeto_state = 'OBSERVED' AND valor_state = 'OBSERVED'
         AND modalidade_state = 'OBSERVED' AND geo_state = 'OBSERVED'
         AND orgao_state = 'OBSERVED' AND deadline_state <> 'UNKNOWN')
        OR cardinality(reason_codes) > 0
    )
);

REVOKE ALL ON TABLE public.confenge_live_intelligence_opportunities FROM PUBLIC;
REVOKE ALL ON TABLE public.confenge_live_intelligence_opportunities FROM smartlic_public_reader;

CREATE INDEX IF NOT EXISTS idx_live_intel_oppty_universe
    ON public.confenge_live_intelligence_opportunities (snapshot_id, row_completeness_state);

-- ---------------------------------------------------------------------------
-- 4. COMPANY (Decisão 3, §3.2)
--    ★ PROJECAO INDEPENDENTE. Nenhum campo copiado de
--    confenge_company_target_fit_current/_history nem de
--    confenge_company_sector_current/_history. Essas tabelas sao lidas apenas
--    por SELECT (diagnostico), NUNCA materializadas aqui.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.confenge_live_intelligence_companies (
    snapshot_id                 TEXT NOT NULL
                                     REFERENCES public.confenge_live_intelligence_snapshots(snapshot_id),
    company_root8               TEXT NOT NULL CHECK (company_root8 ~ '^[0-9]{8}$'),
    razao_social                TEXT,

    portfolio_contract_ids      TEXT[] NOT NULL DEFAULT '{}',
    observed_objects            TEXT[] NOT NULL DEFAULT '{}',
    observed_value_bands        TEXT[] NOT NULL DEFAULT '{}',
    observed_ufs                TEXT[] NOT NULL DEFAULT '{}',
    observed_buyer_cnpjs        TEXT[] NOT NULL DEFAULT '{}',

    most_recent_contracting_date DATE,
    contracting_date_state      TEXT NOT NULL
                                     CHECK (contracting_date_state IN ('OBSERVED', 'UNKNOWN')),
    date_resolver_version       TEXT NOT NULL,

    row_completeness_state      TEXT NOT NULL DEFAULT 'COMPLETE'
                                     CHECK (row_completeness_state IN ('COMPLETE', 'EXCLUDED_UNRESOLVED_DATE')),
    exclusion_reason_codes      TEXT[] NOT NULL DEFAULT '{}',
    reason_codes                TEXT[] NOT NULL DEFAULT '{}',

    portfolio_hash              TEXT NOT NULL CHECK (portfolio_hash ~ '^[0-9a-f]{64}$'),
    source_as_of                TIMESTAMPTZ NOT NULL,
    recorded_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (snapshot_id, company_root8),
    CONSTRAINT chk_live_intel_company_exclusion_justified CHECK (
        (row_completeness_state = 'COMPLETE' AND cardinality(exclusion_reason_codes) = 0)
        OR (row_completeness_state = 'EXCLUDED_UNRESOLVED_DATE' AND cardinality(exclusion_reason_codes) > 0)
    ),
    -- dim_recency nao resolvida ⇒ linha excluida do universo de fit (§7.2).
    CONSTRAINT chk_live_intel_company_unresolved_date_excluded CHECK (
        contracting_date_state = 'OBSERVED'
        OR row_completeness_state = 'EXCLUDED_UNRESOLVED_DATE'
    ),
    CONSTRAINT chk_live_intel_company_date_presence CHECK (
        (contracting_date_state = 'OBSERVED' AND most_recent_contracting_date IS NOT NULL)
        OR (contracting_date_state = 'UNKNOWN' AND most_recent_contracting_date IS NULL)
    )
);

REVOKE ALL ON TABLE public.confenge_live_intelligence_companies FROM PUBLIC;
REVOKE ALL ON TABLE public.confenge_live_intelligence_companies FROM smartlic_public_reader;

CREATE INDEX IF NOT EXISTS idx_live_intel_company_universe
    ON public.confenge_live_intelligence_companies (snapshot_id, row_completeness_state);

COMMENT ON TABLE public.confenge_live_intelligence_companies IS
    'Projecao independente do portfolio observado. PROIBIDO copiar target_fit_class/confidence ou sector_class do outbound (impact-analysis 3.2).';

-- ---------------------------------------------------------------------------
-- 5. COMPANY_OPPORTUNITY_FIT (Decisão 4)
--    ★ TRI-ESTADO POR DIMENSAO. ZERO CAMPO NUMERICO. Sem score, sem
--    percentual, sem matched_count. Ordenacao e tupla lexicografica sobre
--    PRIORIDADE_DIMENSOES, computada em fit.py — nao ha coluna de ranking.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.confenge_live_intelligence_fit (
    snapshot_id             TEXT NOT NULL
                                 REFERENCES public.confenge_live_intelligence_snapshots(snapshot_id),
    company_root8           TEXT NOT NULL,
    opportunity_id          TEXT NOT NULL,

    dim_object              TEXT NOT NULL CHECK (dim_object IN ('MATCH', 'NO_MATCH', 'UNKNOWN')),
    dim_value_band          TEXT NOT NULL CHECK (dim_value_band IN ('MATCH', 'NO_MATCH', 'UNKNOWN')),
    dim_geography           TEXT NOT NULL CHECK (dim_geography IN ('MATCH', 'NO_MATCH', 'UNKNOWN')),
    dim_comparable_buyer    TEXT NOT NULL CHECK (dim_comparable_buyer IN ('MATCH', 'NO_MATCH', 'UNKNOWN')),
    dim_recency             TEXT NOT NULL CHECK (dim_recency IN ('MATCH', 'NO_MATCH', 'UNKNOWN')),

    matched_dimensions      TEXT[] NOT NULL DEFAULT '{}',
    unknown_dimensions      TEXT[] NOT NULL DEFAULT '{}',
    reason_codes            TEXT[] NOT NULL DEFAULT '{}',
    evidence_refs           JSONB NOT NULL DEFAULT '{}'::JSONB,

    fit_state               TEXT NOT NULL
                                 CHECK (fit_state IN ('OBSERVED_FIT', 'NO_OBSERVED_FIT', 'INSUFFICIENT_EVIDENCE')),
    fit_hash                TEXT NOT NULL CHECK (fit_hash ~ '^[0-9a-f]{64}$'),
    recorded_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (snapshot_id, company_root8, opportunity_id),
    FOREIGN KEY (snapshot_id, company_root8)
        REFERENCES public.confenge_live_intelligence_companies(snapshot_id, company_root8),
    FOREIGN KEY (snapshot_id, opportunity_id)
        REFERENCES public.confenge_live_intelligence_opportunities(snapshot_id, opportunity_id),

    -- ★ fit_state e derivacao deterministica das dimensoes (§4.2), aplicada
    -- estruturalmente. Impede UNKNOWN colapsado em NO_MATCH (R7/AC7).
    CONSTRAINT chk_live_intel_fit_state_derivation CHECK (
        (fit_state = 'OBSERVED_FIT'
         AND 'MATCH' = ANY (ARRAY[dim_object, dim_value_band, dim_geography,
                                  dim_comparable_buyer, dim_recency]))
        OR (fit_state = 'INSUFFICIENT_EVIDENCE'
            AND 'MATCH' <> ALL (ARRAY[dim_object, dim_value_band, dim_geography,
                                      dim_comparable_buyer, dim_recency])
            AND 'UNKNOWN' = ANY (ARRAY[dim_object, dim_value_band, dim_geography,
                                       dim_comparable_buyer, dim_recency]))
        OR (fit_state = 'NO_OBSERVED_FIT'
            AND ARRAY[dim_object, dim_value_band, dim_geography,
                      dim_comparable_buyer, dim_recency]
                = ARRAY['NO_MATCH', 'NO_MATCH', 'NO_MATCH', 'NO_MATCH', 'NO_MATCH'])
    ),
    -- Toda dimensao UNKNOWN precisa estar declarada em unknown_dimensions.
    CONSTRAINT chk_live_intel_fit_unknown_declared CHECK (
        ('UNKNOWN' <> ALL (ARRAY[dim_object, dim_value_band, dim_geography,
                                 dim_comparable_buyer, dim_recency]))
        = (cardinality(unknown_dimensions) = 0)
    )
);

REVOKE ALL ON TABLE public.confenge_live_intelligence_fit FROM PUBLIC;
REVOKE ALL ON TABLE public.confenge_live_intelligence_fit FROM smartlic_public_reader;

CREATE INDEX IF NOT EXISTS idx_live_intel_fit_state
    ON public.confenge_live_intelligence_fit (snapshot_id, fit_state);

COMMENT ON TABLE public.confenge_live_intelligence_fit IS
    'Aderencia observada tri-estado por dimensao. ZERO campo numerico por decisao arquitetural (impact-analysis Decisao 4 / R6).';

-- ---------------------------------------------------------------------------
-- 6. EVENTS (Decisão 5)
--    ★ A IDENTIDADE E A TRANSICAO, nao o estado de destino:
--    (subject_key, prev_semantic_hash, semantic_hash). Sem prev_semantic_hash
--    no material do event_id, a sequencia 15 → 20 → 15 teria o segundo evento
--    engolido por ON CONFLICT DO NOTHING (R12).
--    snapshot_id / prev_snapshot_id ficam FORA do material do hash: sao
--    linhagem; inclui-los faria todo replay gerar eventos novos.
--
--    ESCOPO: a tabela nasce VAZIA nesta story. Nenhum codigo da story 1
--    escreve nela; LI-7 (story 2) a popula.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.confenge_live_intelligence_events (
    event_id                TEXT PRIMARY KEY CHECK (event_id ~ '^[0-9a-f]{64}$'),
    event_type              TEXT NOT NULL
                                 CHECK (event_type IN ('NEW_OPPORTUNITY', 'OPPORTUNITY_CHANGED',
                                                       'DEADLINE_CHANGED', 'FIT_BECAME_RELEVANT',
                                                       'COMPANY_PORTFOLIO_CHANGED')),
    subject_key             TEXT NOT NULL,
    prev_semantic_hash      TEXT NOT NULL
                                 CHECK (prev_semantic_hash = '' OR prev_semantic_hash ~ '^[0-9a-f]{64}$'),
    semantic_hash           TEXT NOT NULL CHECK (semantic_hash ~ '^[0-9a-f]{64}$'),
    reason_codes            TEXT[] NOT NULL DEFAULT '{}',
    source_as_of            TIMESTAMPTZ NOT NULL,
    snapshot_id             TEXT NOT NULL
                                 REFERENCES public.confenge_live_intelligence_snapshots(snapshot_id),
    prev_snapshot_id        TEXT
                                 REFERENCES public.confenge_live_intelligence_snapshots(snapshot_id),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Transicao real: estado anterior e novo nao podem coincidir.
    CONSTRAINT chk_live_intel_event_is_transition CHECK (prev_semantic_hash <> semantic_hash),
    -- Bootstrap: prev vazio ⇔ sem snapshot base.
    CONSTRAINT chk_live_intel_event_bootstrap CHECK (
        (prev_semantic_hash = '' AND prev_snapshot_id IS NULL)
        OR (prev_semantic_hash <> '' AND prev_snapshot_id IS NOT NULL)
    ),
    -- Identidade da transicao, redundante com o event_id por construcao.
    CONSTRAINT uq_live_intel_event_transition
        UNIQUE (event_type, subject_key, prev_semantic_hash, semantic_hash)
);

REVOKE ALL ON TABLE public.confenge_live_intelligence_events FROM PUBLIC;
REVOKE ALL ON TABLE public.confenge_live_intelligence_events FROM smartlic_public_reader;

CREATE INDEX IF NOT EXISTS idx_live_intel_events_subject
    ON public.confenge_live_intelligence_events (snapshot_id, event_type, subject_key);

COMMENT ON TABLE public.confenge_live_intelligence_events IS
    'Eventos idempotentes derivados por diff entre snapshots do proprio motor. NENHUM trigger sobre tabela outbound, em nenhuma circunstancia. Nasce vazia na 104; LI-7 popula.';

-- ---------------------------------------------------------------------------
-- 7. LEITOR AS-OF (Decisão 6, §6.3)
--    Reproduz a projecao de 049 sobre a TABELA BASE pncp_raw_bids, com o
--    predicado re-expresso com parametro explicito. NAO e um wrapper sobre
--    v_open_opportunities_canonical: um wrapper so pode filtrar para menos, e
--    as linhas que a view excluiu (data_encerramento < CURRENT_DATE) sao
--    irrecuperaveis por qualquer consulta descendente (R2/AC4).
--
--    v_open_opportunities_canonical permanece INTOCADA: sem CREATE OR REPLACE,
--    sem DROP, sem ALTER. Equivalencia verificavel:
--      live_open_opportunities_as_of(CURRENT_DATE) == v_open_opportunities_canonical
--
--    §8.4: as colunas de data sao TIMESTAMPTZ (alteradas em 049). O parametro
--    permanece DATE (dia civil) e a promocao ocorre no TimeZone da sessao —
--    por isso sources.py fixa o TimeZone explicitamente e cutoff_timezone e
--    travado no header do snapshot.
--
--    DROP + CREATE (nao CREATE OR REPLACE) por disciplina de AC1 — ver nota
--    no cabeçalho.
-- ---------------------------------------------------------------------------
DROP FUNCTION IF EXISTS public.live_open_opportunities_as_of(DATE);

CREATE FUNCTION public.live_open_opportunities_as_of(p_as_of DATE)
RETURNS TABLE (
    bid_id                  TEXT,
    pncp_id                 TEXT,
    objeto                  TEXT,
    valor_estimado          NUMERIC,
    modalidade_id           INTEGER,
    modalidade              TEXT,
    esfera_id               TEXT,
    uf                      TEXT,
    municipio               TEXT,
    codigo_ibge             TEXT,
    orgao_cnpj              TEXT,
    orgao_nome              TEXT,
    data_publicacao         TIMESTAMPTZ,
    data_abertura           TIMESTAMPTZ,
    data_encerramento       TIMESTAMPTZ,
    link_edital             TEXT,
    source                  TEXT,
    source_id               TEXT,
    match_method            TEXT,
    match_score             NUMERIC,
    match_confidence        TEXT,
    matched_entity_id       INTEGER,
    matched_entity_nome     TEXT,
    within_200km            BOOLEAN,
    entity_cnpj_8           TEXT
)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path TO public, pg_temp
AS $live_as_of$
    SELECT
        b.pncp_id                AS bid_id,
        b.pncp_id                AS pncp_id,
        b.objeto_compra          AS objeto,
        b.valor_total_estimado   AS valor_estimado,
        b.modalidade_id,
        b.modalidade_nome        AS modalidade,
        b.esfera_id              AS esfera_id,
        b.uf,
        b.municipio,
        b.codigo_municipio_ibge  AS codigo_ibge,
        b.orgao_cnpj,
        b.orgao_razao_social     AS orgao_nome,
        b.data_publicacao,
        b.data_abertura,
        b.data_encerramento,
        b.link_pncp              AS link_edital,
        b.source,
        b.source_id,
        b.match_method,
        b.match_score,
        b.match_confidence,
        e.id                     AS matched_entity_id,
        e.razao_social           AS matched_entity_nome,
        e.raio_200km             AS within_200km,
        e.cnpj_8                 AS entity_cnpj_8
    FROM public.pncp_raw_bids b
    LEFT JOIN public.sc_public_entities e ON e.id = b.matched_entity_id
    WHERE b.data_encerramento >= p_as_of
       OR (b.data_encerramento IS NULL AND b.data_publicacao >= p_as_of - INTERVAL '30 days');
$live_as_of$;

-- FUNCTIONS concedem EXECUTE a PUBLIC por padrao — este REVOKE e carga util.
REVOKE ALL ON FUNCTION public.live_open_opportunities_as_of(DATE) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.live_open_opportunities_as_of(DATE) FROM smartlic_public_reader;

COMMENT ON FUNCTION public.live_open_opportunities_as_of(DATE) IS
    'Leitor as-of sobre a tabela base pncp_raw_bids. Generalizacao estrita de v_open_opportunities_canonical: as_of(CURRENT_DATE) deve retornar o mesmo conjunto que a view (impact-analysis 6.3).';

-- ---------------------------------------------------------------------------
-- 8. ROLE DE LEITURA DEDICADO (AC12-b)
--    Role NOVO. smartlic_public_reader NAO e reusado: ele tem contrato v1
--    publicado (public_read_v1, janela de depreciacao de 180 dias) e recebeu
--    REVOKE explicito sobre cada objeto acima.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'confenge_live_intel_reader') THEN
        CREATE ROLE confenge_live_intel_reader
            NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION;
        COMMENT ON ROLE confenge_live_intel_reader IS 'managed-by-extra-migration-104';
    END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO confenge_live_intel_reader', current_database());
    EXECUTE format('GRANT confenge_live_intel_reader TO %I', current_user);
END $$;

ALTER ROLE confenge_live_intel_reader SET statement_timeout = '2s';
ALTER ROLE confenge_live_intel_reader SET lock_timeout = '500ms';
ALTER ROLE confenge_live_intel_reader SET idle_in_transaction_session_timeout = '5s';
ALTER ROLE confenge_live_intel_reader SET default_transaction_read_only = 'on';

GRANT USAGE ON SCHEMA public TO confenge_live_intel_reader;

-- Grants minimos: SELECT nas 6 tabelas do motor + EXECUTE na funcao as-of.
-- Nenhum grant sobre qualquer objeto outbound.
GRANT SELECT ON TABLE public.confenge_live_intelligence_snapshots TO confenge_live_intel_reader;
GRANT SELECT ON TABLE public.confenge_live_intelligence_source_watermarks TO confenge_live_intel_reader;
GRANT SELECT ON TABLE public.confenge_live_intelligence_opportunities TO confenge_live_intel_reader;
GRANT SELECT ON TABLE public.confenge_live_intelligence_companies TO confenge_live_intel_reader;
GRANT SELECT ON TABLE public.confenge_live_intelligence_fit TO confenge_live_intel_reader;
GRANT SELECT ON TABLE public.confenge_live_intelligence_events TO confenge_live_intel_reader;
GRANT EXECUTE ON FUNCTION public.live_open_opportunities_as_of(DATE) TO confenge_live_intel_reader;

-- ---------------------------------------------------------------------------
-- 9. (REMOVIDA) ALTER DEFAULT PRIVILEGES
--    Secao deliberadamente vazia — numeracao preservada para nao invalidar as
--    referencias cruzadas de docs, story e testes. O mecanismo era inerte no
--    PostgreSQL 16 e foi removido por decisao do @data-engineer; a justificativa
--    medida esta no cabecalho ("ALTER DEFAULT PRIVILEGES REMOVIDO").
--
--    A barreira de seguranca desta migration (§8.3 / AC3) e composta
--    EXCLUSIVAMENTE pelos REVOKE explicitos por objeto das secoes 1 a 7.
--    Se um dia esta secao voltar a existir e gravar linha em pg_default_acl,
--    a secao 3 do rollback precisa voltar a emitir o GRANT inverso.
-- ---------------------------------------------------------------------------

COMMIT;
