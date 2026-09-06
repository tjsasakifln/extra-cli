# Deferred rollout plan — do not execute while #468 is active

This is sequencing documentation only. It authorizes no production action.

## Migration order

1. `107_contact_discovery_cohort_scoped_identity.sql` — already on the base;
2. `108_pncp_structural_fields.sql`;
3. `109_contract_date_hygiene.sql`;
4. `110_contract_engineering_class.sql`;
5. `111_contract_terms_lifecycle.sql`;
6. `112_engineering_supplier_registry.sql`;
7. `113_supplier_structural_profile.sql`;
8. `114_orgaos_contratantes_projeto.sql`;
9. `115_commercial_read_v1.sql`;
10. `116_engineering_data_release_candidate_v2.sql`.

## Only after #468 independently clears

Rebase/re-evaluate against then-current `origin/main`; require exact-HEAD CI and
human review before merge. A later, separately authorized production change
window would apply migrations, run resumable backfills, refresh the materialized
profile and collect the pending production metrics. Credentials stay outside the
repository and login roles receive the `NOLOGIN` read role separately.

No results/homologation migration belongs in this sequence.
