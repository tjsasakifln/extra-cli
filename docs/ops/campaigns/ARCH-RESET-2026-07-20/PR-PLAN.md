# Campaign PR plan — ARCH-RESET-2026-07-20

Baseline: `d6d9e19`. Each independent PR from fresh `origin/main` unless dependency is inevitable and documented.

## Order (revised after baseline + PR triage)

| Order | ID | Branch (suggested) | Purpose | Depends on | Prod behavior change? |
|------:|----|--------------------|---------|------------|------------------------|
| 1 | **A** | `arch/arch-reset-baseline-20260720` | Baseline, PR disposition, ADR-023, fitness contract | — | **No** |
| 2 | **B** | `test/architecture-characterization` | Characterize `extra-weekly` boundaries, seams | A merged or stacked on A | **No** (tests only) |
| 3 | **C** | `refactor/one-canonical-weekly-pipeline` | Consolidate entrypoints; aliases explicit | B | **Yes** (orchestration only) |
| 4 | **I0** | (human) | Disposition action on #52/#53/#48–51 | A | Merge policy only |
| 5 | **I** | `refactor/versioned-decision-rules` | Prefer #52 material; versioned GO/REVIEW/NO_GO | I0 / #52 | **Yes** |
| 6 | **L** | `feat/ops-run-execution-ledger` | Thin ledger from #50/#53 if not in I | I or main | **Yes** |
| 7 | **D** | `spike/ocds-semantic-mapping` | OCDS spike | A | **No** (spike schema OK) |
| 8 | **E** | `spike/dbt-snapshot-postgres` | dbt snapshots isolated schema | A | **No** unless adopt later |
| 9 | **F** | `spike/data-quality-contract` | One quality contract comparison | A | **No** |
| 10 | **G** | `spike/document-parser-benchmark` | Parser benchmark + license gate | A | **No** |
| 11 | **H** | `spike/entity-resolution-residual` | Splink residual only | A | **No** |
| 12 | **J** | `spike/reporting-output-engine` | XlsxWriter/fpdf2 vs current | A | **No** |
| 13 | **Adopt-*** | per spike | Only if spike passes criteria | matching spike | **Yes** |
| 14 | **Docs** | `docs/architecture-rebaseline` | Reconcile all canonical docs | C + major decisions | Docs |
| 15 | **Cleanup** | `chore/cleanup-superseded-paths` | Remove dead paths | Docs + live cycle | **Yes** |

Spikes D–J may run **in parallel after A** (and preferably after B characterization).  
**Do not** batch-adopt dbt+Soda+Splink+PyMuPDF+XlsxWriter+fpdf2 in one PR.

## Existing open PRs (do not auto-merge)

| PR | Plan reference |
|----|----------------|
| #52 | Primary product MERGE_CANDIDATE → feeds **I** |
| #53 | REBASE_AND_REDUCE → thin **L** or supersede #52 carefully |
| #48–#51 | KEEP_DRAFT / SUPERSEDE — out of product critical path |

## PR description template (mandatory for campaign PRs)

Use the template in the campaign charter / goal §7.5 (Outcome, Problem, Baseline SHA, Scope, Architecture, Before/After, DOD impact, Validation including **full suite**, Evidence, Dependencies/licensing, Rollback, Allowed/Forbidden claims, Review recommendation).

## Success metrics (before vs after campaign)

Track in final report:

- entrypoints, pipelines, orchestrators, ledgers, coverage/freshness impl counts  
- direct deps + install size  
- LOC scripts/tests, LOC removed  
- suite duration, weekly cycle duration  
- real coverage/freshness (no claim of 95% unless measured)  
- actionable opportunities / false open / human review time  

“More modern” is **not** a metric.
