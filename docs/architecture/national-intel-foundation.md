# National contracts intelligence foundation

Migration `060_national_contracts_intelligence_layers.sql` adds additive analytical
views for national PNCP contracts. It does **not** alter dual-capability coverage,
crawlers, or fact-table write paths.

## Layers

| Layer | View / product | Meaning |
|-------|----------------|---------|
| L1 | `v_intel_contracts_raw_national` | National inventory stamp |
| L2 | `v_intel_contracts_geo_sc` | Geographic UF=SC filter only — **not** operational coverage |
| L3+ | `scripts/national_intel` products | Agencies, competitors, benchmarks with lineage |

## Isolation

Operational SC coverage remains on the dual spine (`compute_dual_coverage` /
canonical universe). National-intel products must never be labeled as operational
coverage. Adversarial tests under `tests/national_intel/` enforce this boundary.

## CLI

```bash
python -m scripts.national_intel --help
```
