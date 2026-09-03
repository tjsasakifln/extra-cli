-- 106_confenge_live_intelligence_event_delivery.sql
-- CONFENGE_LIVE_INTELLIGENCE — bump ADITIVO do schema do motor para rastrear
-- entrega de eventos ao webhook inbound do Warmbly (P2 / CONFENGE_OPPORTUNITY_EVENT).
--
-- Owner DDL:  @data-engineer (autoridade exclusiva sobre schema/DDL)
-- Base:       db/migrations/104_confenge_live_intelligence_v1.sql,
--             db/migrations/105_confenge_live_intelligence_company_ref.sql
--             (padrao de estilo, REVOKE/GRANT herdados literalmente)
--
-- ============================================================================
-- ESCOPO — lista fechada, nada alem disto:
--   ALTER TABLE public.confenge_live_intelligence_events
--     + coluna  delivery_status    TEXT      NOT NULL DEFAULT 'pending'
--     + coluna  delivery_attempts  INTEGER   NOT NULL DEFAULT 0
--     + coluna  delivered_at       TIMESTAMPTZ (nullable)
--     + coluna  last_delivery_error TEXT     (nullable)
--     + CHECK   chk_live_intel_event_delivery_status
--     + INDEX   idx_live_intel_events_delivery_pending (parcial, so pending/failed)
--   Reassercao literal dos REVOKE/GRANT da 104 sobre a MESMA tabela.
--
-- NAO faz parte desta migration:
--   * qualquer fila externa (SQS/Redis/etc.) — o outbox e a propria tabela,
--     por decisao do goal (P2: "retry/outbox minimo... zero broker").
--   * qualquer alteracao de coluna existente, DROP, TRUNCATE ou DML.
--
-- ADITIVIDADE — nenhum ALTER, DROP, CREATE OR REPLACE nem DML sobre objeto
-- outbound. Colunas novas sao NOT NULL DEFAULT ou nullable — nenhuma linha
-- pre-existente e invalidada.
-- ============================================================================

BEGIN;

ALTER TABLE public.confenge_live_intelligence_events
    ADD COLUMN IF NOT EXISTS delivery_status TEXT NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS delivery_attempts INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_delivery_error TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.confenge_live_intelligence_events'::regclass
          AND conname = 'chk_live_intel_event_delivery_status'
    ) THEN
        ALTER TABLE public.confenge_live_intelligence_events
            ADD CONSTRAINT chk_live_intel_event_delivery_status CHECK (
                delivery_status IN ('pending', 'delivered', 'failed')
            );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_live_intel_events_delivery_pending
    ON public.confenge_live_intelligence_events (delivery_status, source_as_of)
    WHERE delivery_status IN ('pending', 'failed');

REVOKE ALL ON TABLE public.confenge_live_intelligence_events FROM PUBLIC;
REVOKE ALL ON TABLE public.confenge_live_intelligence_events FROM smartlic_public_reader;
GRANT SELECT ON TABLE public.confenge_live_intelligence_events TO confenge_live_intel_reader;

COMMENT ON COLUMN public.confenge_live_intelligence_events.delivery_status IS
    'Estado do outbox de entrega ao webhook inbound do Warmbly (P2). pending -> delivered|failed. Nunca broker externo.';
COMMENT ON COLUMN public.confenge_live_intelligence_events.delivery_attempts IS
    'Contador de tentativas de entrega HTTP. Incrementado a cada tentativa, sucesso ou falha.';
COMMENT ON COLUMN public.confenge_live_intelligence_events.delivered_at IS
    'Timestamp do primeiro 2xx (ou 200 de replay) do endpoint Warmbly. NULL enquanto pending/failed.';
COMMENT ON COLUMN public.confenge_live_intelligence_events.last_delivery_error IS
    'Ultimo erro de entrega (HTTP status ou excecao), para diagnostico. NULL apos sucesso.';

COMMIT;
