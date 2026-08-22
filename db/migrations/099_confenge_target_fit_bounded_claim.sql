-- 099_confenge_target_fit_bounded_claim.sql
-- Make the target-fit dirty-queue claim terminate early instead of sorting the
-- whole backlog. Additive index swap only; no table rewrite, no data change.
--
-- Why: the claim query orders by (priority DESC, detected_at ASC) over the
-- partial set status IN ('pending','retry'). The 071 index leads with `status`,
-- which is already implied by the partial predicate, so an ordered walk over an
-- IN-list of two values needs a merge-append; the planner instead chose
-- scan + blocking Sort. A blocking Sort makes LIMIT useless: every backlog row
-- is materialized (and every row-level qual evaluated) before the first tuple
-- reaches the Limit node. With pg_try_advisory_xact_lock() as one of those
-- quals that meant one advisory lock per backlog row, exhausting the
-- cluster-global shared lock table ("out of shared memory").
--
-- Dropping the redundant leading `status` column gives an index whose order
-- matches the ORDER BY exactly, so Limit terminates the walk after ~LIMIT rows.
--
-- Index build strategy: plain CREATE INDEX (not CONCURRENTLY). scripts/ops/
-- apply_migrations.py rewrites CONCURRENTLY -> plain unless --allow-concurrent,
-- and the build was measured at 125 ms on a 423k-row queue, so the short SHARE
-- lock on the enqueue path is cheaper than the operational complexity of a
-- concurrent build. lock_timeout below fails fast rather than queueing.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

-- Ordered exactly as the claim ORDER BY, so Limit can stop the walk early.
CREATE INDEX IF NOT EXISTS confenge_tf_dirty_claim2_idx
    ON public.confenge_target_fit_dirty (priority DESC, detected_at ASC)
    WHERE status IN ('pending', 'retry');

COMMENT ON INDEX public.confenge_tf_dirty_claim2_idx IS
'Claim path for confenge_target_fit_dirty. Partial on the claimable statuses; key order matches the claim ORDER BY so LIMIT terminates the index walk instead of sorting the backlog.';

-- Redundant once claim2 exists: same partial predicate, and the leading `status`
-- column is implied by that predicate. No other query orders by this shape.
DROP INDEX IF EXISTS public.confenge_tf_dirty_claim_idx;

COMMIT;
