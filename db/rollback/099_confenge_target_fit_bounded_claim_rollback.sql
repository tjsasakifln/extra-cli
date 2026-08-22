-- 099_confenge_target_fit_bounded_claim_rollback.sql
-- Restore the 071 claim index and drop the 099 replacement.
-- Reverting the index alone re-exposes the unbounded-Sort claim plan, so this
-- rollback is only safe together with reverting scripts/confenge_target_fit/store.py.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

CREATE INDEX IF NOT EXISTS confenge_tf_dirty_claim_idx
    ON public.confenge_target_fit_dirty (status, priority DESC, detected_at ASC)
    WHERE status IN ('pending', 'retry');

DROP INDEX IF EXISTS public.confenge_tf_dirty_claim2_idx;

COMMIT;
