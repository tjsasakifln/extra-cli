# INTEGRATION-REPORT

## Branch

- `feat/extra-local-command-center` contains `origin/main` @ `1718d638` (process_documents #184)
- Preserved: Extra decision loop (#181), registry (#183), public agencies (#185), process_documents (#184)
- Commercial capabilities still use `confenge_commercial_target_router` only

## New integration surface

| Component | Role |
|-----------|------|
| workflow.* capabilities | Outcome-first entry; JobRunner in-process |
| run-manifest | Primary artifact discovery |
| deliverables/* | PDF/XLSX profiles |
| /api/workflows, preview-xlsx, export-bundle, job manifest | Browser workbench APIs |
