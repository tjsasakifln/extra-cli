-- 106_confenge_live_intelligence_event_delivery_rollback.sql
-- Rollback completo de db/migrations/106_confenge_live_intelligence_event_delivery.sql
--
--   psql "$LOCAL_DATALAKE_DSN" -f db/rollback/106_confenge_live_intelligence_event_delivery_rollback.sql
--
-- Ordem: indice -> constraint -> colunas.
--
-- PERDA DE DADO — este rollback DESCARTA o estado de entrega (delivery_status,
-- delivery_attempts, delivered_at, last_delivery_error). Aceitavel por
-- construcao: o outbox e reconstruivel a partir do proprio event_id
-- determinístico (ON CONFLICT DO NOTHING garante que nenhum evento e perdido,
-- apenas volta a "pending" e sera reentregue — o endpoint Warmbly ja trata
-- replay do mesmo event_id como 200 idempotente, nao como duplicata).

BEGIN;

DROP INDEX IF EXISTS public.idx_live_intel_events_delivery_pending;

ALTER TABLE public.confenge_live_intelligence_events
    DROP CONSTRAINT IF EXISTS chk_live_intel_event_delivery_status;

ALTER TABLE public.confenge_live_intelligence_events
    DROP COLUMN IF EXISTS last_delivery_error,
    DROP COLUMN IF EXISTS delivered_at,
    DROP COLUMN IF EXISTS delivery_attempts,
    DROP COLUMN IF EXISTS delivery_status;

COMMIT;
