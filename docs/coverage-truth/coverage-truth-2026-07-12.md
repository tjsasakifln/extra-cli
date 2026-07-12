# Coverage Truth Report

**Generated:** 2026-07-12T16:44:34.366204+00:00
**Radius:** 200.0 km from Florianópolis (-27.5954, -48.548)
**Coverage window:** 90 days
**Evidence ledger:** Unverified — ledger empty

---

## Denominator

- **Active entities within 200.0 km:** 1093
- Statewide total: [unverified — query scoped to radius]

## Metric Definitions

| Metric | Definition |
|--------|-----------|
| Monitoring Coverage | % of entities with ≥1 source having `is_covered=true` in the coverage window |
| Freshness | % of entities with `last_seen_at` within 90 days |
| Bid Presence | % of entities with ≥1 bid record in entity_coverage |
| Contract Presence | % of entities with a contract record (`source='contracts'`, `is_covered=true`) |
| Source Health | % of successful evidence records per source (from coverage_evidence ledger) |
| Entity/Source Gaps | Uncovered entity+source combinations |

## Monitoring Coverage

- **Coverage:** 44.6% (487/1093)
- Checked but no coverage: 606
- Never checked: 0

### By Source

| Source | Entities Checked | Entities Covered | Coverage % |
|--------|-----------------|------------------|------------|
| pncp | 1093 | 455 | 41.6% |
| dom_sc | 1093 | 0 | 0.0% |
| pcp | 1093 | 26 | 2.4% |
| compras_gov | 1093 | 57 | 5.2% |
| sc_compras | 1093 | 0 | 0.0% |
| contracts | 0 | 0 | N/A |
| transparencia | 1093 | 0 | 0.0% |
| tce_sc | 0 | 0 | N/A |
| doe_sc | 1093 | 0 | 0.0% |
| ciga_ckan | 1093 | 153 | 14.0% |
| mides_bigquery | 1093 | 0 | 0.0% |
| selenium | 0 | 0 | N/A |

## Freshness

- **Fresh (≤90d):** 478 (43.7%)
- **Stale (>90d):** 9
- **Unknown:** 606

## Bid Presence

- **Entities with bids:** 487 (44.6%)
- **Entities without bids:** 606

## Contract Presence

- **Entities with contracts:** 0 (0.0%)
- **Entities without contracts:** 1093

## Source Health

| Source | Total Runs | Successful | Failed | Health % | Last Check |
|--------|-----------|------------|--------|----------|------------|
| pncp | ? | ? | ? | 41.6% | never |
| dom_sc | ? | ? | ? | 0.0% | never |
| pcp | ? | ? | ? | 2.4% | never |
| compras_gov | ? | ? | ? | 5.2% | never |
| sc_compras | ? | ? | ? | 0.0% | never |
| contracts | ? | ? | ? | unverified | never |
| transparencia | ? | ? | ? | 0.0% | never |
| tce_sc | ? | ? | ? | unverified | never |
| doe_sc | ? | ? | ? | 0.0% | never |
| ciga_ckan | ? | ? | ? | 14.0% | never |
| mides_bigquery | ? | ? | ? | 0.0% | never |
| selenium | ? | ? | ? | unverified | never |

## Entity/Source Gaps

- **Total uncovered combinations:** 12425

### By Source (ranked by marginal impact)

| Rank | Source | Uncovered Entities |
|------|--------|-------------------|
| 1 | dom_sc | 1093 |
| 2 | sc_compras | 1093 |
| 3 | contracts | 1093 |
| 4 | transparencia | 1093 |
| 5 | tce_sc | 1093 |
| 6 | doe_sc | 1093 |
| 7 | mides_bigquery | 1093 |
| 8 | selenium | 1093 |
| 9 | pcp | 1067 |
| 10 | compras_gov | 1036 |
| 11 | ciga_ckan | 940 |
| 12 | pncp | 638 |

### Next Best Action

**Source:** `dom_sc`
**Impact:** 1093 uncovered entities resolved
**Rationale:** Checking all entities against 'dom_sc' would resolve 1093 uncovered entity+source gaps — the highest marginal impact among all sources.

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
| SECRETARIA MUNICIPAL DE EDUCACAO | SANTO AMARO DA IMPERATRIZ | ciga_ckan | not_investigated |
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

---

## Caveats

- These metrics do **NOT** imply completeness or ≥95% recall.
- One record ≠ full coverage; absence of evidence ≠ evidence of absence.
- Statewide entity count is reported separately from the radius-filtered denominator.
- Sources not yet checked are marked `not_investigated`.
- Measurements marked `unverified` reflect missing evidence ledger data — never fabricated.
