-- Rollback 053 — destructive: removes the entity source registry table.
-- Export the registry before use outside a disposable/local environment.
BEGIN;
DROP TRIGGER IF EXISTS trg_entity_source_registry_updated_at
    ON public.entity_source_registry;
DROP FUNCTION IF EXISTS public.entity_source_registry_touch_updated_at();
DROP TABLE IF EXISTS public.entity_source_registry;
COMMIT;
