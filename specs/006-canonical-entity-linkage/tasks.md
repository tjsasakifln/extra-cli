# Tasks — 006 Canonical Entity Linkage

- [x] Baseline + isolation quarantine + worktree from origin/main
- [x] Prove specs 001/002/003 are not linkage authority; create 006
- [x] Migration 061 + layered resolver + pipeline
- [x] Seed isolated DB from authenticated dump hash + consulting CSV + radar overlap
- [x] Run linkage `link-20260724T-rc1` (20 org exact, 114 contract exact, 126 suppliers)
- [x] Workspace `entity` + fix competitors column names + claim language
- [x] Dossier operational-report.{html,json,csv}
- [x] Tests `tests/test_canonical_entity_linkage.py`
- [x] Make gates campaign-gate / release-candidate / verify-isolated
- [x] Campaign artifacts under `artifacts/campaigns/CANONICAL-ENTITY-LINKAGE-01/`
- [ ] Independent adversarial review findings resolved
- [ ] Commit + PR via @devops
- [ ] Main CI green + DOD serial ACCEPTED (only items truly proven)

## Evidence map

| Task | Evidence |
|------|----------|
| Linkage run | investigation.json, linkage-quality.json |
| Isolation | isolation.json |
| Keys | key-profile.json |
| Workspace | verify-isolated.json / workspace CLI stdout |
| Spec | specs/006-*/ |
