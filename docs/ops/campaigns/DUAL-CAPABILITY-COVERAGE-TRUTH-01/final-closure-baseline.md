# Final Closure Baseline — DUAL-CAPABILITY-COVERAGE-TRUTH-01

**Captured at (runtime):** 2026-07-22T12:20:00Z  
**Branch at capture:** `fix/dual-canonical-closure` tracking `origin/main`  
**Do not treat document SHAs as current tip without re-running `git rev-parse`.**

## Observed facts (preflight; not docs)

| Field | Value |
|-------|-------|
| `origin_main_sha` | `1c063005e5116ff394e26ef3ac3221c7f97c2d01` |
| `open_prs` | #107 OPEN CONFLICTING; drafts/open: #66 #64 #63 #62 #61 #60 #59 #58 #57 #56 #55 #54 #53 #52 #51 #50 #48 |
| `pr_107_status` | OPEN, `mergeable=CONFLICTING`, head `campaign/continue-03-report-valores` (valores report) |
| `latest_ci` | main push run `29891069907` SUCCESS (merge #114) |
| `accepted_evidence_sha` | pack `.dod/evidence/DOD-rol-1-definition-of-done-4efe05fc94/` (accepted under older semantics) |
| `current_engine_sha` | `1c06300` (includes #108–#114; engine honesty at `ed7be1c` ancestry) |
| `current_live_measurement` | `measurement_success=false`, `dual_gate_status=NOT_READY`, `source_combinations=["pncp"]` both caps, never_checked=1093 |
| `current_mapping_status` | `identity_unresolved`, `identity_unresolved_count=4`, `ambiguous_cnpj8=['00394494']` |
| `current_source_policy_status` | `draft` (`config/source_applicability.yaml`) |
| `known_cross_artifact_conflicts` | see below |

## PR stack (#108–#114)

| PR | State | Merge SHA / note |
|----|-------|------------------|
| #108 | MERGED | `edd7618` dual engine |
| #109 | MERGED | `30f5548` DOD accept calcula cobertura |
| #110 | MERGED | `3a17805` skeptic identity/scope/view |
| #111 | MERGED | `ac81c51` clean-env measurement tolerance |
| #112 | MERGED | `3ab3a3a` cap-level honesty |
| #113 | MERGED | `86cb028` docs stamp |
| #114 | MERGED | `1c06300` ancestry-safe restamp (**origin/main**) |

## Known cross-artifact conflicts (blocking final closure)

1. **Required combinations diverge:** `applicability_matrix.MIN_SOURCE_COMBINATION` (pncp+ciga_ckan / pncp+contracts) vs `dual_capability_coverage.DEFAULT_REQUIRED_SOURCES` (pncp-only) vs live report `source_combinations=["pncp"]`.
2. **Draft policy participates:** `config/source_applicability.yaml` `status: draft` is still loaded by `build_applicability_resolutions` and forms denominators as if authoritative.
3. **Esfera hardcoded:** `build_applicability_resolutions` injects `"esfera": "municipal"` for every entity.
4. **Presence fail-open paths:** `table_absent` treated as “descriptive zero”; fully unmapped presence can yield zero presence with only a limitation.
5. **Identity:** four legitimate distinct seed entities share cnpj8 `00394494`; engine counts all four as `identity_unresolved` instead of multi-key resolution (DB has CNPJ14 for three of four + distinct names).
6. **Acceptance stale:** DOD item “O golden path calcula cobertura” cites `measurement_success=true` and pack `4efe05fc94` while live reproof on tip has `measurement_success=false`.
7. **Stamps:** campaign `STATUS.md` / converge call `86cb028` “current tip” while `origin/main` is `1c06300`.
8. **Spec Kit:** `converge-report.md` declares CONVERGED and classifies identity/policy as “operational only”.
9. **PR #107:** still OPEN and `mergeable=false` against dual-era `main`.

## Non-claims at baseline

* No operational 95% dual coverage  
* No LOCAL_READY / PROJECT_DONE  
* No GOAL DONE at this baseline  

## Next

Implementation branch `fix/dual-canonical-closure` from `origin/main@1c06300` to close conflicts above.
