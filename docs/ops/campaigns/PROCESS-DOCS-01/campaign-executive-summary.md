# PROCESS-DOCS-01 — Final wave: coverage exit 0 with residual policy

Generated: 2026-07-31T00:20:21.579595+00:00

## Gate
`python -m scripts.process_documents coverage --full` → **exit 0**

Residual policy (PO): waives **exit code** for win/qual only.  
`meets_threshold` remains **false** for those two metrics. Denominators **not** shrunk.

## Metrics

| Metric | % | meets_threshold | Gate |
|--------|---:|:---------------:|------|
| discovery | 100 | true | MET |
| operational | 96.56 | true | MET |
| recall | 100 | true | MET |
| financial | 100 | true | MET |
| notice | 99.94 | true | MET |
| session | 99.94 | true | MET |
| winning proposal | 8.91 | **false** | residual waived |
| qualification | 1.27 | **false** | residual waived |

## candidate_complete
**false** — win/qual completeness targets not met (publication limits; PO residual accepted).

## #137 / #133
- #137 **CLOSED**
- #133 rebased MERGEABLE; bid_readiness 28/28; not auto-merged

## READY_TO_SUBMIT
**forbidden**
