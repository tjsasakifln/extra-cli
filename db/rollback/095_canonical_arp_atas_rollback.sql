-- Rollback 095_canonical_arp_atas.sql
BEGIN;
DROP TABLE IF EXISTS public.canonical_arp_atas;
COMMIT;
