-- contract_lifecycle_distribution.sql
-- Story: contract-lifecycle-truth-v1 (AC19, Task 9).
--
-- NOT_READY: correct and reproducible, but NOT yet run against real data.
-- The local test DataLake (LOCAL_DATALAKE_DSN) is empty of production
-- contracts, so this query returns zero rows there. Run it as a post-deploy
-- verification step against a read-only production or staging copy. It is
-- deliberately NOT part of this story's automated test suite: an empty-DB
-- result is not evidence of anything.
--
-- Read-only. Touches no table and no pre-existing view.
--
-- Usage:
--   python3 - <<'PY'
--   import os, psycopg2
--   sql = open('scripts/reports/contract_lifecycle_distribution.sql').read()
--   with psycopg2.connect(os.environ['LOCAL_DATALAKE_DSN']) as conn, conn.cursor() as cur:
--       cur.execute(sql)
--       for row in cur.fetchall():
--           print(row)
--   PY

WITH total AS (
    SELECT count(*)::numeric AS rows_total
    FROM public.v_contract_lifecycle_truth_v1
)
SELECT
    lifecycle_state,
    lifecycle_trust,
    count(*) AS contracts,
    round(100.0 * count(*) / NULLIF(total.rows_total, 0), 4) AS pct_of_view,
    count(*) FILTER (WHERE lifecycle_is_current_evidence) AS current_evidence_rows,
    count(*) FILTER (WHERE contracting_date_in_qualification_window) AS in_window_rows,
    min(contracting_date) AS contracting_date_min,
    max(contracting_date) AS contracting_date_max
FROM public.v_contract_lifecycle_truth_v1
CROSS JOIN total
GROUP BY lifecycle_state, lifecycle_trust, total.rows_total
ORDER BY lifecycle_state, lifecycle_trust;
