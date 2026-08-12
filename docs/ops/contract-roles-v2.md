# Canonical contract roles v2

Migration 077 introduces `v_contracts_canonical_v2` and an auditable
`contract_role_links` ledger. The historical `v_contracts_canonical` remains
available only for compatibility and is explicitly deprecated.

## Role contract

- Buyer fields are derived only from `orgao_cnpj`; the root is matched to
  `sc_public_entities.cnpj_8`.
- Supplier fields come from the typed identity introduced by migration 076.
  `supplier_identity_id` is a role-specific, content-addressed identifier and
  is never reused as `buyer_entity_id`.
- Every ledger row records match method, confidence, reason codes, run,
  snapshot and timestamp. Ingestion sets a source-bound run automatically;
  canonical linkage refreshes it with the identified linkage run.
- `v_value_observations_canonical_v2` also exposes only buyer-derived entity
  fields for contract observations.

Current consumers use v2. The only Python SQL consumer of the old contracts
view, `competitive_intel_validation.py`, was migrated in the same change.
Future #291 buyer marts and #292 report-ready projections must use the v2
views. Removing v1 requires a separate deprecation audit after those issues
land.

## Query-plan evidence

Evidence was captured on PostgreSQL 17.6 in `extra_test` after applying
migrations 076–077. The test database held 11 contracts and 10 role links; the
small size makes this a structural index proof, not a production performance
claim.

```text
buyer_entity_id  -> Index Only Scan using idx_contract_roles_buyer
supplier_identity_id -> Index Only Scan using idx_contract_roles_supplier
contract_id      -> Index Scan using contract_role_links_pkey
snapshot_id      -> Index Only Scan using idx_contract_roles_snapshot
```

All four `EXPLAIN (ANALYZE, BUFFERS)` plans executed in 0.1 ms or less on that
fixture. `tests/test_contract_roles_v2.py` repeats the four plan assertions and
the adversarial role test inside a rolled-back transaction. This evidence does
not claim production cardinality or VPS readiness.
