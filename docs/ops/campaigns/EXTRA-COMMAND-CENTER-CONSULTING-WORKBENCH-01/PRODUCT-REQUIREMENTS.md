# PRODUCT-REQUIREMENTS — WORKBENCH-01

**Spec Kit:** `specs/008-command-center-consulting-workbench/spec.md` (FR IDs)

## Primary outcome

Tiago completes consulting work (Extra / CONFENGE suppliers / agencies / documents) from business goal → professional PDF/XLSX → human decision → optional regenerate, without terminal after launch.

## Requirement traceability

| ID | Requirement | Implementation | Test |
|----|-------------|----------------|------|
| FR-HOME-01 | Outcome-first home | `overview.py`, `HomePage.tsx` | e2e home |
| FR-FLOW-A–D | Guided flows PDF+XLSX+manifest | `workflows/runner.py`, capabilities `workflow.*` | `test_workbench_flows`, e2e task1–4 |
| FR-FLOW-E | Review queue | store reviews + DecisionPanel | e2e review |
| FR-MANIFEST-01 | run-manifest primary | `run_manifest.py`, job endpoint | unit + API |
| FR-PREV-01/02 | PDF/XLSX in browser | artifact_reader + ArtifactViewer + preview-xlsx | e2e hard open |
| FR-REV-01–03 | Rationale + hash ACCEPT | `review_rules.py`, app decisions | API + e2e |
| FR-REV-24 | Obsolete after hash change | `mark_accepts_obsolete_for_item`, regenerate | `test_regenerate_and_obsolete` |
| FR-BUNDLE-01 | Export bundle | `export_bundle.py` | unit |
| FR-COMPARE | What changed | `run_compare.py`, ComparePage | e2e task5 |
| FR-PRESET | Last params / rerun | `last_params:{id}` pref on job start | `test_last_params_preset_saved` |
| FR-MD | Semantic markdown | `MarkdownView.tsx` | structural + render path |
| FR-SEC | No DOD auto / no outreach / allowlist | app decision + security tests | test_api_security |
| FR-FIXTURE | No fake live | runner rejects `use_fixture=False` | `test_use_fixture_false_is_rejected` |

## Non-goals

- Second SPA / alternate commercial router
- Auto outreach / DOD auto-accept
- Full live orchestration inside guided workflows (Avançado retains CLI)
