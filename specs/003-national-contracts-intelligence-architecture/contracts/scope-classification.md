# Scope Classification Labels

| Label | Meaning | Valid for operational coverage gate? |
|-------|---------|--------------------------------------|
| `raw_national` | All rows in national contracts inventory | No |
| `geo_sc` | Rows with UF = SC (geographic filter only) | No |
| `canonical_sc_operational` | Dual-coverage / entity evidence over canonical universe | **Yes** (only path) |
| `intel_product` | Derived strategic analytics (competitors, benchmarks, …) | No |

## Rules

1. Products MUST stamp one primary label in output lineage.
2. `geo_sc` MUST NOT be renamed “coverage”.
3. `raw_national` row counts MUST NOT appear as coverage numerators.
4. When joining to canonical universe, stamp universe count + seed hash when available.
