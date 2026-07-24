# Function matrix — existing vs national_intel

| Function | Existing | New | Duplication | Decision |
|----------|----------|-----|-------------|----------|
| SC historical list | `contract_intel historico` + views | — | no | keep contract_intel |
| SC supplier ranking | `contract_intel fornecedores` + deliverable_b | national competitors (UF multi) | partial (ranking concept) | national uses own SQL with UF footprint + claim classes; facade `national-competitors` |
| Expiring contracts | `contract_intel ativos` + deliverable_c | — | no | keep |
| Price history entity | `contract_intel precos` + deliverable_d | benchmarks (distribution) | partial (values) | different grain (distribution vs entity history) |
| Org ranking DoD | deliverable_a | agencies profile | partial | national is filterable national profile, not DoD 15 list |
| Dual coverage | dual_capability_coverage | never | no | dual only |
| Scope stamps / claim class | — | lineage envelope | no | national only |
| Isolation DSN default | LOCAL_DATALAKE_DSN | NATIONAL_INTEL_DSN | intentional | national prefers 5435 |

**Canonical operators:**  
`python -m scripts.contract_intel national-{competitors,benchmarks,agencies}` (facade)  
or `python -m scripts.national_intel …` (same engine).
