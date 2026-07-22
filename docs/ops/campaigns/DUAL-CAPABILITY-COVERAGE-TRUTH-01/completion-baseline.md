# Completion baseline — DUAL-CAPABILITY-COVERAGE-TRUTH-01

**Captured:** 2026-07-22T02:35:00Z (approx)  
**Mission:** conclude dual capability coverage truth (fail-closed + matrix + acceptance)

## Git / branches

| Ref | SHA | Notes |
|-----|-----|-------|
| `origin/main` | `5a19df7dcd938af255ab5f44dc8d4d2137da40b2` | `docs(dod): ACCEPTED O golden path gera relatório de concorrentes (#106)` |
| PR #108 head `campaign/dual-capability-coverage-truth` | `89bf306fd9d275fa5bc063465df2272ecd48bf21` | 4 commits ahead of main; **0 behind** main |
| merge-base(main, PR#108) | `5a19df7…` | PR already on current main |
| PR #107 head `campaign/continue-03-report-valores` | `f144a868be670da1e2e88ce00712fcd8da95f385` | valores report; touches `scripts/golden_path.py` |
| Local workspace (primary checkout) | `fix/weekly-strict-fail-closed` @ `1435f52` | unrelated; dirty local scrape json |
| Campaign worktree | `.worktrees/dual-capability-coverage-truth` @ `89bf306` | working tree has local specify + output artifacts (uncommitted) |

## PR #108

| Field | Value |
|-------|-------|
| URL | https://github.com/tjsasakifln/extra-cli/pull/108 |
| State | open, not draft, mergeable_state=clean |
| Files | 20 (+3054/−105) |
| Reviews | none |
| Issue comments | none |
| CI run | `29884048883` — **all 8 checks SUCCESS** (lint, mypy, bandit, pip-audit, critical readiness, operational expanded, resilience, full suite) |
| Verdict for merge of *current* tip | CI green but **semantic FAIL** vs mission criteria (fail-open paths, hardcoded PNCP, outsider ignored, hashes not validated, vacuous tests, incomplete aggregates, matrix not engine-integrated) |

### PR #108 commits

1. `ef60991` feat(coverage): dual capability monitoring coverage truth (ADR-029)
2. `f5a7639` fix(coverage): ruff S607/format for dual capability spine
3. `06d6011` fix(coverage): dual gate exit codes, unknown applicability, ADR-030
4. `89bf306` fix(golden_path): do not fail clean-env skip_sources on dual coverage gates

## Concurrent PRs touching golden_path / coverage / DOD

| PR | Branch | Overlap risk | Integration rule |
|----|--------|--------------|------------------|
| #107 | `campaign/continue-03-report-valores` | **HIGH** — adds `run_valores_report` + CLI flags to `golden_path.py` | Do **not** overwrite valores work; dual PR stays independent; rebase #107 after dual merge if needed |
| #63 | `fix/weekly-strict-fail-closed` | medium — freshness by entity, migration 058 ESR capability (name collision risk with dual’s 058 views) | Dual already has `058_dual_capability_coverage_views.sql`; keep additive; coordinate if both land |
| #66 | full suite | low (draft) | ignore for dual merge |
| #64/#62/#61/#60 | architecture drafts | low | ignore |

## Spec Kit state (pre-completion)

| Artifact | Present | Honest status |
|----------|---------|---------------|
| `specs/001-dual-capability-coverage-truth/spec.md` | yes | incomplete vs mission §4–12 |
| `plan.md` | yes | incomplete |
| `tasks.md` | yes | T005 open falsely; T020 open; false CONVERGED |
| `analyze-report.md` | yes | **premature CONVERGED** — must re-analyze |
| `converge-report.md` | yes | **premature CONVERGED** |
| `checklists/requirements.md` | **missing** | must create |

## Known critical findings (must fix before merge)

1. **Fail-open DB load** — `except Exception` falls back to legacy query / empty presence / empty map
2. **Unmapped evidence skipped** — undercount, not fail-closed
3. **CNPJ first-wins** — ambiguity not detected
4. **Outsider ignored** in pure path (`test_outsider` asserts ignore is OK)
5. **Hashes recorded not validated** against expected from planilha/ledger
6. **Hardcoded `REQUIRED_SOURCES = pncp`** — matrix not consulted by engine
7. **Default applicability=applicable** masks unknown
8. **success_with_data** allows `records_persisted=0` if fetched>0 path incomplete; missing started_at/provenance rigor
9. **success_zero** weak error_message scan; accepts bare `supports_zero_proof`
10. **Aggregates hide pending/never** as unknown=0
11. **Vacuous test** `assert … or True`
12. **Denominators test** forces 3==3 for both caps (does not prove distinct A_C)
13. **Golden path** reloads seed independently of planilha validation stamps
14. **DOD** annotated PARTIAL without normative acceptance controller

## Working tree policy

- Campaign work performed in worktree `campaign/dual-capability-coverage-truth`
- Do not commit unrelated primary-checkout dirt (`data/transparencia_scrape_results.json`, STABILIZE campaign, freshness outputs)
- Do not claim GOAL DONE until PR merged, main reproof, acceptance pack, controller

## Commands (baseline)

```bash
git fetch --all --prune
git rev-parse origin/main origin/campaign/dual-capability-coverage-truth
git merge-base origin/main origin/campaign/dual-capability-coverage-truth
git log --oneline origin/main..origin/campaign/dual-capability-coverage-truth
```

## Docs stamp closure

**Date:** 2026-07-22  
**Main tip:** `3ab3a3a738437791cb4a9e34b76f41bb578f47a8`  
**Live dual:** measurement_success=false · mapping_status=identity_unresolved · identity_unresolved_count=4 · dual_gate_status=NOT_READY  
**Gate:** `docs/ops/campaigns/DUAL-CAPABILITY-COVERAGE-TRUTH-01/scripts/check_campaign_stamp_consistency.py` → exit 0  
**Evidence:** `evidence/dual-reproof-summary.json` (git_sha = tip)  

Process stack #108–#112 DONE on main. Remaining work is operational (identity CNPJ + backfill), not engine implementable.
