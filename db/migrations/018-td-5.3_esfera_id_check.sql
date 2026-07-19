-- Migration 018: CHECK constraint for esfera_id on pncp_raw_bids
-- Story TD-5.3 / TD-DB-09
--
-- Runtime schema on local/main has esfera_id as TEXT (not INT).
-- Migration 001 may still create INT on fresh installs; cast before check.
-- Accept both numeric codes and letter codes used across crawlers:
--   1/F Federal, 2/E Estadual, 3/M Municipal, 4/D Distrital

ALTER TABLE pncp_raw_bids
  ALTER COLUMN esfera_id TYPE TEXT USING esfera_id::text;

UPDATE pncp_raw_bids
SET esfera_id = NULL
WHERE esfera_id IS NOT NULL
  AND esfera_id NOT IN ('1', '2', '3', '4', 'F', 'E', 'M', 'D');

ALTER TABLE pncp_raw_bids
DROP CONSTRAINT IF EXISTS chk_pncp_raw_bids_esfera_id;

ALTER TABLE pncp_raw_bids
ADD CONSTRAINT chk_pncp_raw_bids_esfera_id
CHECK (
  esfera_id IS NULL
  OR esfera_id IN ('1', '2', '3', '4', 'F', 'E', 'M', 'D')
);

COMMENT ON CONSTRAINT chk_pncp_raw_bids_esfera_id ON pncp_raw_bids IS
    'TD-DB-09: esfera_id text codes 1/F,2/E,3/M,4/D or NULL';
