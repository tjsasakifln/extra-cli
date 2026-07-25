# PR #121 — Destination

## Decision

**SUPERSEDED** by PR #131 migration `060_national_contracts_intelligence_layers.sql` and national_intel modules.

## Collision

| PR | Migration file |
|----|----------------|
| main | `059_coverage_evidence_canonical_entity_unique.sql` |
| #121 | `059_national_contracts_intelligence_layers.sql` (**same number, different content**) |
| #131 | `060_national_contracts_intelligence_layers.sql` (renumbered equivalent) |

## Preserved ideas (in #131)

- Layered intel views (raw_national / geo_sc / supplier_geo / agency_profile)
- Scope labels and non-coverage claims on views
- `scripts/national_intel/*` product surface

## Rejected / not merged as-is

- Shipping a second 059 migration
- Parallel architecture PR competing with integrator

## Close procedure (after #131 on main)

1. Comment with this file + absorption of ideas into 060
2. Close without merge
3. No full cherry-pick of #121
