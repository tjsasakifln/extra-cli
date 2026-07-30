# Research — 007

## Prior campaign findings (CONFENGE-COMMERCIAL-READY-01)

- Status BLOCKED with multi-truth coverage (5% vs 1.65% vs 100% on different denominators).
- Snapshots of 60k / 11 974 rows used; VPS lake holds **4 467 364** contracts.
- Official registry coverage claimed inconsistently while VPS `supplier_registry` empty.
- Human precision correctly null.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Entry point | Keep `make confenge-commercial-cycle` | No parallel command theater |
| Population default for activation | `FULL_POPULATION` + `RC` | Real queue requires full eligible ranking |
| Discovery | Prefilter SQL + full history expansion | Documented; not called full snapshot scan |
| Coverage | `canonical_coverage` module | Single structure for all exports |
| SOURCE/STATE | Restored snapshot on local allowlisted port | Isolation fail-closed |
| Cadastro | RFB open data / authenticated extract | Aggregators not official authority |
| Human gate | Tiago only | precision null until labels |

## Performance notes

- Avoid loading 4.4M rows as Python objects for scoring.
- Batch history by CNPJ; indexes on fornecedor_cnpj + dates.
- Registry ingest resumable/idempotent.

## Risks

- RFB bulk download size/time.
- Bad dates in lake (outlier year 8406) — use sane filters for envelopes only.
- Long discovery query; need EXPLAIN and indexes.
