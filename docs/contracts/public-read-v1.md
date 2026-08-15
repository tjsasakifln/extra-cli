# `public_read_v1` producer contract

Version: `v1.0.0`

Owner: Extra canonical truth plane
Canonical consumer: `tjsasakifln/web-cfg#60` at `confenge.com.br`

## Boundary

`public_read_v1` is a server-side, versioned, SELECT-only projection over the
latest `READY_CANONICAL` public snapshot. It is not a second DataLake, browser
API, synchronization feed, or place for client scores. The PostgreSQL role
`smartlic_public_reader` is a legacy implementation name retained for v1 compatibility; it has no password in this repository, no access to the
`public` schema and no write/DDL privileges. Runtime credentials must remain in
server-side secret storage and must never enter JS bundles, HTML, source maps or
browser requests.

Every fact/entity family (`tenders`, `contracts`, `entities`, `suppliers`,
`organs`, and `municipalities`) carries `as_of`, `source_updated_at`,
`completeness`, `reason_codes`, and JSON provenance. `current_snapshot` exposes
the snapshot hashes and completeness, while `surface_health` exposes its own
operational status fields. A failed or blocked build does not replace the last
`READY_CANONICAL` snapshot. The `surface_health` family remains readable to
show staleness and kill-switch state.

## MVP families and representative queries

| Family | Required fields | Public web query |
|---|---|---|
| `current_snapshot` | snapshot/content and seven input hashes, `as_of`, completeness, provenance | current public revision and cache key |
| `tenders` | event/process/type/status/title/publication/official number, origin metadata | tender detail/status/document history by `process_key` |
| `contracts` | event/process/status/title/value/official number, origin metadata | contract history by `process_key` |
| `entities` | canonical ID/type/name/export-safe tax identity, origin metadata | canonical entity detail by `entity_id` |
| `suppliers` | entity fields restricted to supplier/company | supplier detail and contract joins |
| `organs` | entity fields restricted to organ/unit | buyer/publisher detail |
| `municipalities` | canonical municipality ID, IBGE, UF/name, origin metadata | municipality landing-page identity |
| `surface_health` | view, refresh/query/error/p95, snapshot/as-of, completeness | freshness banner and server-side circuit-breaker evidence |
| `research_flagship_series` | competence/geography/archetype, volume, integral BRL ticket, provenance | chart/research series for web-cfg flagship research |
| `research_claim_gate` | `nacional_completo`, `national_claim_allowed`, reason_codes, denominator hashes | fail-closed national publish decision |
| `research_health` | freshness, coverage, consumer errors | operational observability for the research family |

Exact query text, timeout, p95 target, row limit and concurrency budget are
queryable in `public_read_v1.query_budgets`. Consumers must always use bounded
predicates and limits; a generic table browser is outside the contract.

## Compatibility and deprecation

Within v1, only additive nullable columns are compatible. Removing or renaming
a column, changing its type/meaning/nullability, or weakening provenance needs
`public_read_v2`, or a documented overlap of at least 180 days. The producer
schema fingerprint and changelog live in `public_read_v1.contract_releases`;
producer and consumer fixtures must compare that fingerprint before cutover.

## Operational limits and rollout

Role defaults: read-only transactions, 2 s statement timeout, 500 ms lock
timeout and 5 s idle-in-transaction timeout. Rollout is shadow → fixture
reconciliation → no-traffic soak → bounded canary → continuous gate. Local
PostgreSQL tests prove permissions, schema shape, repeatable reads and query
plans; they do not prove Netcup readiness, live canonical web-consumer cutover, combined-load
soak, or `VPS_OPERATIONAL`.

## Changelog

- `v1.1.0` (2026-08-15): additive research-flagship families
  (`research_flagship_series`, `research_claim_gate`, `research_health`) for
  `web-cfg / flagship research` (extra-cli#400, web-cfg#65/#73). Contract:
  [`public-read-research-flagship-v1.md`](public-read-research-flagship-v1.md).
  Migration `094_public_intelligence_research_models.sql` (094 was free on
  `origin/main` at `42166330`). No v1.0.0 column was removed or renamed.
- `v1.0.0` (2026-08-13): initial snapshot, tender, contract, entity, supplier,
  organ, municipality and surface-health families.
