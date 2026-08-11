-- 074_confenge_shadow_classifier_lineage.sql
-- Shadow target-fit must carry the same classifier lineage as ACTIVE current.

BEGIN;

ALTER TABLE public.confenge_target_fit_shadow
    ADD COLUMN IF NOT EXISTS classifier_sha TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS confenge_tf_shadow_version_classifier_idx
    ON public.confenge_target_fit_shadow (target_fit_version, classifier_sha);

COMMIT;
