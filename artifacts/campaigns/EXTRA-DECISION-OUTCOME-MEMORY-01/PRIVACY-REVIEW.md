# Privacy review — EXTRA-DECISION-OUTCOME-MEMORY-01

## Controls

1. Explicit `client_id` on every API — no silent default in generic core.
2. Cross-client FK/trigger enforcement for actions and outcomes.
3. List/show filter by `client_id` (adversarial test: other client gets empty / None).
4. Import cannot switch client scope (test_import_does_not_switch_client_scope).
5. Fixtures use synthetic CNPJ-like ids and actors (`fixture-actor`, `evidence-actor`).
6. No real Extra commercial margins, private contacts, or production decision dumps committed.

## RLS

Not enabled in v1. Rationale: many app connections use privileged roles where RLS is ineffective;
false security theater avoided. Isolation proven at repository + SQL constraints + tests.

## Residual risk

Operators with full DB superuser access can read all clients (same as rest of datalake).
Multi-tenant SaaS RLS hardening is a future campaign, not claimed here.
