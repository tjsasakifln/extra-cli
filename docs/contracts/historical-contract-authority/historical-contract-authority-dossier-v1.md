# historical-contract-authority-dossier/1.0

Facts-only producer. No SEO copy, no publication or index approval.

## States

`REJECT` | `HOLD_FOR_DATA` | `HANDOFF_READY`

`HANDOFF_READY` requires every quality hard gate and `DOSSIER_AUTHORITY_SCORE` ≥ 88 with no dimension below 75.

## Score weights

| Dimension | Weight |
|-----------|--------|
| documentary_depth | 25 |
| epistemic_integrity | 20 |
| analytical_singularity | 15 |
| calc_chronology_rigor | 15 |
| decision_utility | 15 |
| citability | 5 |
| maintenance | 5 |

Integer arithmetic. No rounding up to fabricate approval.

## Claim classes

`FACT` | `CALCULATION` | `INFERENCE` | `UNKNOWN`

A FACT without source ref and locator fails. A CALCULATION without formula, inputs, unit and replay fails. INFERENCE stays labeled. UNKNOWN is preserved.

## Comparability

Delegated to `scripts.contract_comparables.build_peer_group` (#415). States: `COMPARABLE` | `HOLD_FOR_DATA` | `NOT_COMPARABLE`. Missing `unidade` / `regime` / `valor_semantic` is never invented.

## Consumer

`public-read-contract-analysis/1.0` via adapter. Data states only: `DATA_READY` | `DATA_HOLD` | `DATA_REJECT`. Never `PUBLISHABLE_*` or `INDEX`.

## Replay

```bash
python3 -m scripts.historical_contract_authority --mode fixture --as-of 2026-08-17T12:00:00Z
```
