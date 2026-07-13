-- QW-01: auditable opportunity radar evidence and run metadata.
-- Extends existing ledgers; does not alter or delete raw data.
-- Idempotent on PostgreSQL 16+.

BEGIN;

ALTER TYPE evidence_state ADD VALUE IF NOT EXISTS 'success';
ALTER TYPE evidence_state ADD VALUE IF NOT EXISTS 'error';
ALTER TYPE evidence_state ADD VALUE IF NOT EXISTS 'pending';
ALTER TYPE evidence_state ADD VALUE IF NOT EXISTS 'stale';
ALTER TYPE evidence_state ADD VALUE IF NOT EXISTS 'blocked';

ALTER TABLE coverage_evidence
    ADD COLUMN IF NOT EXISTS canonical_entity_key TEXT,
    ADD COLUMN IF NOT EXISTS applicability TEXT NOT NULL DEFAULT 'applicable',
    ADD COLUMN IF NOT EXISTS scope_key TEXT,
    ADD COLUMN IF NOT EXISTS checked_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS pages_expected INTEGER,
    ADD COLUMN IF NOT EXISTS pages_processed INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS records_fetched INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS open_records INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS freshness_status TEXT NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS evidence_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

DO $$ BEGIN
    ALTER TABLE coverage_evidence ADD CONSTRAINT ck_ce_applicability
        CHECK (applicability IN ('applicable', 'not_applicable', 'unknown'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE coverage_evidence ADD CONSTRAINT ck_ce_freshness_status
        CHECK (freshness_status IN ('fresh', 'stale', 'never', 'unknown'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

ALTER TABLE coverage_evidence DROP CONSTRAINT IF EXISTS ck_success_zero_completeness;
ALTER TABLE coverage_evidence DROP CONSTRAINT IF EXISTS ck_ce_success_zero_scope;

ALTER TABLE coverage_evidence ADD CONSTRAINT ck_ce_success_zero_scope
    CHECK (
        state != 'success_zero'
        OR (
            queried_start IS NOT NULL
            AND queried_end IS NOT NULL
            AND scope_key IS NOT NULL
            AND pages_processed > 0
            AND (
                (pages_expected IS NOT NULL AND pages_processed >= pages_expected)
                OR (
                    pages_expected IS NULL
                    AND evidence_metadata->>'completion_rule' IN (
                        'short_page_without_total',
                        'empty_page_after_valid_scope',
                        'http_204_complete'
                    )
                )
            )
        )
    ) NOT VALID;

-- Migration 024 introduced ``partial`` as a valid enum state, but some local
-- databases carry a later trigger revision that rejects it. QW-01 requires an
-- explicit partial state whenever pagination cannot be proven complete.
CREATE OR REPLACE FUNCTION fn_validate_coverage_evidence()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.state = 'success_with_data' AND NEW.count_persisted <= 0 THEN
        RAISE EXCEPTION 'success_with_data requires count_persisted > 0 (got %)', NEW.count_persisted;
    END IF;
    IF NEW.state = 'success_zero' AND NEW.count_persisted > 0 THEN
        RAISE EXCEPTION 'success_zero requires count_persisted = 0 (got %)', NEW.count_persisted;
    END IF;
    RETURN NEW;
END;
$$;

DROP INDEX IF EXISTS uq_ce_entity_run;

CREATE UNIQUE INDEX IF NOT EXISTS uq_ce_legacy_entity_run
    ON coverage_evidence (entity_id, source, data_type, run_id)
    WHERE canonical_entity_key IS NULL AND entity_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_ce_canonical_entity_run
    ON coverage_evidence (canonical_entity_key, source, data_type, run_id)
    WHERE canonical_entity_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ce_canonical_entity_source
    ON coverage_evidence (canonical_entity_key, source, checked_at DESC);

ALTER TABLE opportunity_runs
    ADD COLUMN IF NOT EXISTS external_run_id TEXT,
    ADD COLUMN IF NOT EXISTS source_strategy TEXT,
    ADD COLUMN IF NOT EXISTS period_start DATE,
    ADD COLUMN IF NOT EXISTS period_end DATE,
    ADD COLUMN IF NOT EXISTS records_expected INTEGER,
    ADD COLUMN IF NOT EXISTS scope_complete BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS completion_reason TEXT,
    ADD COLUMN IF NOT EXISTS error_code TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_or_external_run_id
    ON opportunity_runs (external_run_id)
    WHERE external_run_id IS NOT NULL;

ALTER TABLE opportunity_checkpoints
    ADD COLUMN IF NOT EXISTS external_run_id TEXT,
    ADD COLUMN IF NOT EXISTS pages_expected INTEGER,
    ADD COLUMN IF NOT EXISTS scope_complete BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS completion_reason TEXT;

CREATE OR REPLACE FUNCTION upsert_qw01_pncp_opportunities(batch JSONB)
RETURNS TABLE(action TEXT, record_id BIGINT, result_content_hash TEXT)
LANGUAGE plpgsql
AS $$
DECLARE
    rec JSONB;
BEGIN
    FOR rec IN SELECT * FROM jsonb_array_elements(batch)
    LOOP
        IF COALESCE(rec->>'numero_controle_pncp', '') = '' THEN
            RAISE EXCEPTION 'QW-01 PNCP record missing numero_controle_pncp';
        END IF;

        INSERT INTO opportunity_intel (
            source, source_id, source_url, content_hash, numero_controle_pncp,
            crawl_batch_id, run_id, orgao_cnpj, orgao_nome, ente_federativo,
            uf, municipio, codigo_ibge, numero_processo, numero_edital,
            modalidade, modalidade_id, objeto, categoria, valor_estimado,
            valor_semantica, data_publicacao, data_abertura, data_encerramento,
            status_fonte, status_canonico, status_motivo, status_data,
            link_edital, link_anexos, proveniencia, metadata
        ) VALUES (
            'pncp', rec->>'source_id', rec->>'source_url', rec->>'content_hash',
            rec->>'numero_controle_pncp', rec->>'crawl_batch_id', (rec->>'run_id')::BIGINT,
            rec->>'orgao_cnpj', rec->>'orgao_nome', rec->>'ente_federativo',
            COALESCE(rec->>'uf', 'SC'), rec->>'municipio', rec->>'codigo_ibge',
            rec->>'numero_processo', rec->>'numero_edital', rec->>'modalidade',
            (rec->>'modalidade_id')::INTEGER, rec->>'objeto', rec->>'categoria',
            (rec->>'valor_estimado')::NUMERIC, rec->>'valor_semantica',
            (rec->>'data_publicacao')::TIMESTAMPTZ, (rec->>'data_abertura')::TIMESTAMPTZ,
            (rec->>'data_encerramento')::TIMESTAMPTZ, rec->>'status_fonte',
            COALESCE(rec->>'status_canonico', 'unknown'), rec->>'status_motivo',
            (rec->>'status_data')::TIMESTAMPTZ, rec->>'link_edital',
            CASE WHEN jsonb_typeof(rec->'link_anexos') = 'array'
                THEN ARRAY(SELECT * FROM jsonb_array_elements_text(rec->'link_anexos')) END,
            COALESCE(rec->'proveniencia', '{}'::jsonb), COALESCE(rec->'metadata', '{}'::jsonb)
        )
        ON CONFLICT (numero_controle_pncp)
            WHERE numero_controle_pncp IS NOT NULL AND is_active = TRUE
        DO UPDATE SET
            source_url = COALESCE(EXCLUDED.source_url, opportunity_intel.source_url),
            content_hash = EXCLUDED.content_hash,
            crawl_batch_id = EXCLUDED.crawl_batch_id,
            run_id = EXCLUDED.run_id,
            last_seen_at = NOW(),
            orgao_cnpj = COALESCE(EXCLUDED.orgao_cnpj, opportunity_intel.orgao_cnpj),
            orgao_nome = COALESCE(EXCLUDED.orgao_nome, opportunity_intel.orgao_nome),
            municipio = COALESCE(EXCLUDED.municipio, opportunity_intel.municipio),
            codigo_ibge = COALESCE(EXCLUDED.codigo_ibge, opportunity_intel.codigo_ibge),
            numero_processo = COALESCE(EXCLUDED.numero_processo, opportunity_intel.numero_processo),
            numero_edital = COALESCE(EXCLUDED.numero_edital, opportunity_intel.numero_edital),
            modalidade = COALESCE(EXCLUDED.modalidade, opportunity_intel.modalidade),
            modalidade_id = COALESCE(EXCLUDED.modalidade_id, opportunity_intel.modalidade_id),
            objeto = EXCLUDED.objeto,
            categoria = COALESCE(EXCLUDED.categoria, opportunity_intel.categoria),
            valor_estimado = COALESCE(EXCLUDED.valor_estimado, opportunity_intel.valor_estimado),
            valor_semantica = COALESCE(EXCLUDED.valor_semantica, opportunity_intel.valor_semantica),
            data_publicacao = COALESCE(EXCLUDED.data_publicacao, opportunity_intel.data_publicacao),
            data_abertura = COALESCE(EXCLUDED.data_abertura, opportunity_intel.data_abertura),
            data_encerramento = COALESCE(EXCLUDED.data_encerramento, opportunity_intel.data_encerramento),
            status_fonte = EXCLUDED.status_fonte,
            status_canonico = EXCLUDED.status_canonico,
            status_motivo = EXCLUDED.status_motivo,
            status_data = EXCLUDED.status_data,
            link_edital = COALESCE(EXCLUDED.link_edital, opportunity_intel.link_edital),
            link_anexos = COALESCE(EXCLUDED.link_anexos, opportunity_intel.link_anexos),
            proveniencia = EXCLUDED.proveniencia,
            metadata = EXCLUDED.metadata,
            is_active = TRUE
        RETURNING
            CASE WHEN xmax = 0 THEN 'insert' ELSE 'update' END,
            id,
            content_hash
        INTO action, record_id, result_content_hash;
        RETURN NEXT;
    END LOOP;
END;
$$;

COMMIT;

COMMENT ON COLUMN coverage_evidence.canonical_entity_key IS
    'Stable seed identity hash; preserves legitimate duplicate CNPJ roots.';
COMMENT ON COLUMN opportunity_runs.scope_complete IS
    'True only when every declared source scope has auditable pagination completion.';
