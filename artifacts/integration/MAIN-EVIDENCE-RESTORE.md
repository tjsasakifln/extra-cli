# Main evidence restore (skeptic fix)

## Problem

Commit `a5eb260a` (slim) accidentally deleted **11 files already present on `main`**
from unrelated campaigns while scanning the full worktree for policy violations.
The generated-artifacts policy gate only enforces **Added/Modified** paths
(`git diff --diff-filter=AM`), so deleting pre-existing main evidence was
unnecessary and violated retention rule 13.

## Restored paths (blob-identical to origin/main)

1. `artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/dual-reproof-after-applicability/dual-coverage-gaps-historical_contracts.csv`
2. `artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/dual-reproof-after-applicability/dual-coverage-gaps-historical_contracts.json`
3. `artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/dual-reproof-after-applicability/dual-coverage-gaps-open_tenders.csv`
4. `artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/dual-reproof-after-applicability/dual-coverage-gaps-open_tenders.json`
5. `artifacts/campaigns/OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01/operational-report.html`
6. `artifacts/campaigns/OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01/tests.xml`
7. `artifacts/campaigns/OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01/weekly-offline-rc/deliverable_e.json`
8. `artifacts/campaigns/OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01/weekly-offline-rc/deliverable_e_audit.json`
9. `artifacts/campaigns/OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01/weekly-offline-rc/extra_weekly_pack.xlsx`
10. `artifacts/campaigns/STRATIFIED-RECALL-SOURCE-RESILIENCE-01/operational-report.html`
11. `artifacts/campaigns/STRATIFIED-RECALL-SOURCE-RESILIENCE-01/tests.xml`

## Method

```bash
git checkout origin/main -- <paths>
```

## Scope of Phase-3 slim (unchanged)

Only campaign outputs **introduced by #129/#130/#131** remain out of Git
(reproducible pack PDF/XLSX/dossiers/pack-rc/pack-verify/etc.).
