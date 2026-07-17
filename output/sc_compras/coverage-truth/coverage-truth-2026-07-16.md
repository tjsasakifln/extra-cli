# Coverage Truth Report

**Generated:** 2026-07-17T00:11:02.838757+00:00
**Radius:** 200 km from Florianópolis (-27.5954, -48.548)
**Coverage window:** 90 days
**Evidence ledger:** Unverified — ledger empty

---

## Denominator

- **Active entities within 200 km:** 1093
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

- **Coverage:** unverified (0/1093)
- Source: `coverage_evidence (v_latest_evidence)`
- ⚠️  Monitoring coverage from evidence ledger — entity-level observations only. Bid presence is a separate metric.
- Checked (no success): 0
- Never checked: 1093

### By Source (from evidence ledger)

| Source | Entities Checked | Entities Covered | Coverage % |
|--------|-----------------|------------------|------------|
| pncp | 0 | 0 | N/A |
| ciga_ckan | 0 | 0 | N/A |
| pcp | 0 | 0 | N/A |
| compras_gov | 0 | 0 | N/A |
| sc_compras | 0 | 0 | N/A |
| contracts | 0 | 0 | N/A |
| transparencia | 0 | 0 | N/A |
| tce_sc | 0 | 0 | N/A |
| doe_sc | 0 | 0 | N/A |
| mides_bigquery | 0 | 0 | N/A |
| dom_sc | 0 | 0 | N/A |

## Freshness

- **Fresh (≤90d):** 52 (4.8%)
- **Stale (>90d):** 0
- **Unknown:** 1041

## Bid Presence (persisted records)

- **Entities with bids:** 52 (4.8%)
- **Entities without bids:** 1041
- ⚠️  Bid presence counts entities with ≥1 persisted bid record. This is NOT monitoring coverage — an entity may have bids without an evidence-backed monitoring observation.

## Contract Presence

- **Entities with contracts:** 0 (0.0%)
- **Entities without contracts:** 1093

## Source Health (from evidence ledger)

| Source | Status | Entity Rows | Successful | Failed | Health % | Last Check |
|--------|--------|------------|------------|--------|----------|------------|
| pncp | active | ? | ? | ? | unverified | never |
| | | _Evidence ledger empty — source health unverified_ | | | | |
| ciga_ckan | active | ? | ? | ? | unverified | never |
| | | _Evidence ledger empty — source health unverified_ | | | | |
| pcp | active | ? | ? | ? | unverified | never |
| | | _Evidence ledger empty — source health unverified_ | | | | |
| compras_gov | active | ? | ? | ? | unverified | never |
| | | _Evidence ledger empty — source health unverified_ | | | | |
| sc_compras | blocked | 0 | 0 | 0 | unverified | never |
| | ⚠️ API não documentada, acesso instável | | | | | |
| contracts | active | ? | ? | ? | unverified | never |
| | | _Evidence ledger empty — source health unverified_ | | | | |
| transparencia | blocked | 0 | 0 | 0 | unverified | never |
| | ⚠️ Portais individuais por município (295+) | | | | | |
| tce_sc | active | ? | ? | ? | unverified | never |
| | | _Evidence ledger empty — source health unverified_ | | | | |
| doe_sc | blocked | 0 | 0 | 0 | unverified | never |
| | ⚠️ Requer Selenium + certificado digital | | | | | |
| mides_bigquery | blocked | 0 | 0 | 0 | unverified | never |
| | ⚠️ BigQuery requer credencial GCP | | | | | |
| dom_sc | blocked | 0 | 0 | 0 | unverified | never |
| | ⚠️ Aguardando credenciais API REST v2 (CPF+CNPJ+X-API-Key). Contatar dom@consorciociga.gov.br | | | | | |

## Entity/Source Gaps

- **Total uncovered combinations:** 11990

### By Source (ranked by marginal impact)

| Rank | Source | Uncovered Entities |
|------|--------|-------------------|
| 1 | pncp | 1090 |
| 2 | ciga_ckan | 1090 |
| 3 | pcp | 1090 |
| 4 | compras_gov | 1090 |
| 5 | sc_compras | 1090 |
| 6 | contracts | 1090 |
| 7 | transparencia | 1090 |
| 8 | tce_sc | 1090 |
| 9 | doe_sc | 1090 |
| 10 | mides_bigquery | 1090 |
| 11 | dom_sc | 1090 |

### Next Best Action ⚠️ UNVERIFIED

**Source:** `pncp`
**Impact:** 1090 uncovered entities
**Rationale:** NO source has entity-level evidence. 'pncp' has 1090 uncovered entities but marginal gain is unverified — no observed evidence exists for any source.

⚠️  **Marginal gain is unverified.** No source has entity-level evidence in the ledger. This ranking reflects only the count of uncovered entity+source combinations — it does NOT reflect observed source effectiveness.

### Sample Gaps (first 20)

| Entity | Municipio | Source | State |
|--------|-----------|--------|-------|
| SECRETARIA MUNICIPAL DE EDUCACAO | SANTO AMARO DA IMPERATRIZ | pncp | not_investigated |
| SECRETARIA MUNICIPAL DE EDUCACAO | SANTO AMARO DA IMPERATRIZ | ciga_ckan | not_investigated |
| SECRETARIA MUNICIPAL DE EDUCACAO | SANTO AMARO DA IMPERATRIZ | pcp | not_investigated |
| SECRETARIA MUNICIPAL DE EDUCACAO | SANTO AMARO DA IMPERATRIZ | compras_gov | not_investigated |
| SECRETARIA MUNICIPAL DE EDUCACAO | SANTO AMARO DA IMPERATRIZ | sc_compras | not_investigated |
| SECRETARIA MUNICIPAL DE EDUCACAO | SANTO AMARO DA IMPERATRIZ | contracts | not_investigated |
| SECRETARIA MUNICIPAL DE EDUCACAO | SANTO AMARO DA IMPERATRIZ | transparencia | not_investigated |
| SECRETARIA MUNICIPAL DE EDUCACAO | SANTO AMARO DA IMPERATRIZ | tce_sc | not_investigated |
| SECRETARIA MUNICIPAL DE EDUCACAO | SANTO AMARO DA IMPERATRIZ | doe_sc | not_investigated |
| SECRETARIA MUNICIPAL DE EDUCACAO | SANTO AMARO DA IMPERATRIZ | mides_bigquery | not_investigated |
| SECRETARIA MUNICIPAL DE EDUCACAO | SANTO AMARO DA IMPERATRIZ | dom_sc | not_investigated |
| SANTO AMARO DA IMPERATRIZ CAMARA DE VEREADORES | SANTO AMARO DA IMPERATRIZ | pncp | not_investigated |
| SANTO AMARO DA IMPERATRIZ CAMARA DE VEREADORES | SANTO AMARO DA IMPERATRIZ | ciga_ckan | not_investigated |
| SANTO AMARO DA IMPERATRIZ CAMARA DE VEREADORES | SANTO AMARO DA IMPERATRIZ | pcp | not_investigated |
| SANTO AMARO DA IMPERATRIZ CAMARA DE VEREADORES | SANTO AMARO DA IMPERATRIZ | compras_gov | not_investigated |
| SANTO AMARO DA IMPERATRIZ CAMARA DE VEREADORES | SANTO AMARO DA IMPERATRIZ | sc_compras | not_investigated |
| SANTO AMARO DA IMPERATRIZ CAMARA DE VEREADORES | SANTO AMARO DA IMPERATRIZ | contracts | not_investigated |
| SANTO AMARO DA IMPERATRIZ CAMARA DE VEREADORES | SANTO AMARO DA IMPERATRIZ | transparencia | not_investigated |
| SANTO AMARO DA IMPERATRIZ CAMARA DE VEREADORES | SANTO AMARO DA IMPERATRIZ | tce_sc | not_investigated |
| SANTO AMARO DA IMPERATRIZ CAMARA DE VEREADORES | SANTO AMARO DA IMPERATRIZ | doe_sc | not_investigated |

---

## Caveats

- Monitoring coverage (from evidence ledger) ≠ bid presence (from persisted records).
- These metrics do **NOT** imply completeness or ≥95% recall.
- One record ≠ full coverage; absence of evidence ≠ evidence of absence.
- Statewide entity count is reported separately from the radius-filtered denominator.
- Sources not yet checked are marked `not_investigated`.
- Measurements marked `unverified` reflect missing evidence ledger data — never fabricated.
- When no entity-level evidence exists, monitoring coverage is `unverified`, not 0%.
