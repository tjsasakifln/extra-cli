# Coverage Truth Report

**Generated:** 2026-07-12T17:40:40.632300+00:00
**Radius:** 200.0 km from Florianópolis (-27.5954, -48.548)
**Coverage window:** 90 days
**Evidence ledger:** Available

---

## Denominator

- **Active entities within 200.0 km:** 1093
- Statewide total: [unverified — query scoped to radius]

## Metric Definitions

| Metric | Definition | Source |
|--------|-----------|--------|
| Monitoring Coverage | % of entities with ≥1 source having evidence state `success_*` | `coverage_evidence` (v_latest_evidence) |
| Freshness | % of entities with `last_seen_at` within 90 days | `entity_coverage.last_seen_at` |
| Bid Presence | % of entities with ≥1 persisted bid record | `entity_coverage.total_bids` |
| Contract Presence | % of entities with a contract record | `entity_coverage` (source='contracts') |
| Source Health | % of successful entity-level evidence rows per source | `coverage_evidence` (v_source_health) |
| Entity/Source Gaps | Entity+source pairs without `success_*` evidence | `coverage_evidence` |

## Monitoring Coverage

- **Coverage:** 100.0% (1093/1093)
- Source: `coverage_evidence (v_latest_evidence)`
- ⚠️  Monitoring coverage from evidence ledger — entity-level observations only. Bid presence is a separate metric.
- Checked (no success): 0
- Never checked: 0

### By Source (from evidence ledger)

| Source | Entities Checked | Entities Covered | Coverage % |
|--------|-----------------|------------------|------------|
| pncp | 1093 | 1093 | 100.0% |
| dom_sc | 0 | 0 | N/A |
| pcp | 0 | 0 | N/A |
| compras_gov | 0 | 0 | N/A |
| sc_compras | 0 | 0 | N/A |
| contracts | 0 | 0 | N/A |
| transparencia | 0 | 0 | N/A |
| tce_sc | 0 | 0 | N/A |
| doe_sc | 0 | 0 | N/A |
| ciga_ckan | 0 | 0 | N/A |
| mides_bigquery | 0 | 0 | N/A |
| selenium | 0 | 0 | N/A |

## Freshness

- **Fresh (≤90d):** 479 (43.8%)
- **Stale (>90d):** 9
- **Unknown:** 605

## Bid Presence (persisted records)

- **Entities with bids:** 488 (44.6%)
- **Entities without bids:** 605
- ⚠️  Bid presence counts entities with ≥1 persisted bid record. This is NOT monitoring coverage — an entity may have bids without an evidence-backed monitoring observation.

## Contract Presence

- **Entities with contracts:** 0 (0.0%)
- **Entities without contracts:** 1093

## Source Health (from evidence ledger)

| Source | Entity Rows | Successful | Failed | Health % | Last Check |
|--------|------------|------------|--------|----------|------------|
| pncp | 1093 | 1093 | 0 | 100.0% | 2026-07-12T17:40:30.712848+00:00 |
| dom_sc | ? | ? | ? | unverified | never |
| pcp | ? | ? | ? | unverified | never |
| compras_gov | ? | ? | ? | unverified | never |
| sc_compras | ? | ? | ? | unverified | never |
| contracts | ? | ? | ? | unverified | never |
| transparencia | ? | ? | ? | unverified | never |
| tce_sc | ? | ? | ? | unverified | never |
| doe_sc | ? | ? | ? | unverified | never |
| ciga_ckan | ? | ? | ? | unverified | never |
| mides_bigquery | ? | ? | ? | unverified | never |
| selenium | ? | ? | ? | unverified | never |

## Entity/Source Gaps

- **Total uncovered combinations:** 10930

### By Source (ranked by marginal impact)

| Rank | Source | Uncovered Entities |
|------|--------|-------------------|
| 1 | dom_sc | 1093 |
| 2 | pcp | 1093 |
| 3 | compras_gov | 1093 |
| 4 | sc_compras | 1093 |
| 5 | contracts | 1093 |
| 6 | transparencia | 1093 |
| 7 | tce_sc | 1093 |
| 8 | doe_sc | 1093 |
| 9 | mides_bigquery | 1093 |
| 10 | selenium | 1093 |

### Next Best Action ⚠️ UNVERIFIED

**Source:** `dom_sc`
**Impact:** 1093 uncovered entities
**Rationale:** NO source has entity-level evidence. 'dom_sc' has 1093 uncovered entities but marginal gain is unverified — no observed evidence exists for any source.

⚠️  **Marginal gain is unverified.** No source has entity-level evidence in the ledger. This ranking reflects only the count of uncovered entity+source combinations — it does NOT reflect observed source effectiveness.

### Sample Gaps (first 20)

| Entity | Municipio | Source | State |
|--------|-----------|--------|-------|
| SECRETARIA MUNICIPAL DE EDUCACAO | SANTO AMARO DA IMPERATRIZ | dom_sc | not_investigated |
| SECRETARIA MUNICIPAL DE EDUCACAO | SANTO AMARO DA IMPERATRIZ | pcp | not_investigated |
| SECRETARIA MUNICIPAL DE EDUCACAO | SANTO AMARO DA IMPERATRIZ | compras_gov | not_investigated |
| SECRETARIA MUNICIPAL DE EDUCACAO | SANTO AMARO DA IMPERATRIZ | sc_compras | not_investigated |
| SECRETARIA MUNICIPAL DE EDUCACAO | SANTO AMARO DA IMPERATRIZ | contracts | not_investigated |
| SECRETARIA MUNICIPAL DE EDUCACAO | SANTO AMARO DA IMPERATRIZ | transparencia | not_investigated |
| SECRETARIA MUNICIPAL DE EDUCACAO | SANTO AMARO DA IMPERATRIZ | tce_sc | not_investigated |
| SECRETARIA MUNICIPAL DE EDUCACAO | SANTO AMARO DA IMPERATRIZ | doe_sc | not_investigated |
| SECRETARIA MUNICIPAL DE EDUCACAO | SANTO AMARO DA IMPERATRIZ | mides_bigquery | not_investigated |
| SECRETARIA MUNICIPAL DE EDUCACAO | SANTO AMARO DA IMPERATRIZ | selenium | not_investigated |
| SANTO AMARO DA IMPERATRIZ CAMARA DE VEREADORES | SANTO AMARO DA IMPERATRIZ | dom_sc | not_investigated |
| SANTO AMARO DA IMPERATRIZ CAMARA DE VEREADORES | SANTO AMARO DA IMPERATRIZ | pcp | not_investigated |
| SANTO AMARO DA IMPERATRIZ CAMARA DE VEREADORES | SANTO AMARO DA IMPERATRIZ | compras_gov | not_investigated |
| SANTO AMARO DA IMPERATRIZ CAMARA DE VEREADORES | SANTO AMARO DA IMPERATRIZ | sc_compras | not_investigated |
| SANTO AMARO DA IMPERATRIZ CAMARA DE VEREADORES | SANTO AMARO DA IMPERATRIZ | contracts | not_investigated |
| SANTO AMARO DA IMPERATRIZ CAMARA DE VEREADORES | SANTO AMARO DA IMPERATRIZ | transparencia | not_investigated |
| SANTO AMARO DA IMPERATRIZ CAMARA DE VEREADORES | SANTO AMARO DA IMPERATRIZ | tce_sc | not_investigated |
| SANTO AMARO DA IMPERATRIZ CAMARA DE VEREADORES | SANTO AMARO DA IMPERATRIZ | doe_sc | not_investigated |
| SANTO AMARO DA IMPERATRIZ CAMARA DE VEREADORES | SANTO AMARO DA IMPERATRIZ | mides_bigquery | not_investigated |
| SANTO AMARO DA IMPERATRIZ CAMARA DE VEREADORES | SANTO AMARO DA IMPERATRIZ | selenium | not_investigated |

---

## Caveats

- Monitoring coverage (from evidence ledger) ≠ bid presence (from persisted records).
- These metrics do **NOT** imply completeness or ≥95% recall.
- One record ≠ full coverage; absence of evidence ≠ evidence of absence.
- Statewide entity count is reported separately from the radius-filtered denominator.
- Sources not yet checked are marked `not_investigated`.
- Measurements marked `unverified` reflect missing evidence ledger data — never fabricated.
- When no entity-level evidence exists, monitoring coverage is `unverified`, not 0%.
