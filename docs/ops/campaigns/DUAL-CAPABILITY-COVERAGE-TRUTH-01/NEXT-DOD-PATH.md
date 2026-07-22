# NEXT-DOD-PATH — dual capability coverage (post-closure)

**Campaign:** `DUAL-CAPABILITY-COVERAGE-TRUTH-01`  
**Date:** 2026-07-22  
**Main tip (source of truth):** `3ab3a3a738437791cb4a9e34b76f41bb578f47a8`  
**Adapter:** dual fail-closed engine on main (PRs #108–#112)

## Estado comprovado (reproof live em main)

| Campo | Valor |
|-------|-------|
| Method | `dual_capability_coverage` |
| artifact git_sha | `3ab3a3a738437791cb4a9e34b76f41bb578f47a8` (= origin/main) |
| measurement_success | **false** |
| coverage_gate_pass | **false** |
| pipeline_success | **false** |
| scope_complete | **true** |
| dual_gate_status | **NOT_READY** |
| mapping_status | **identity_unresolved** |
| identity_unresolved_count | **4** |
| ambiguous_cnpj8 | `['00394494']` |
| universe entity_count | 1093 |
| seed_sha256 | `d65f272812cf8dc9…` |
| canonical_ids_sha256 | `0b3f894d87ba71f2…` |
| open_tenders | den=1093 num=0 never=1093 cap_meas=False gate=FAIL presence=0.0% |
| historical_contracts | den=1093 num=0 never=1093 cap_meas=False gate=FAIL presence=0.0915% |
| legacy 19.5791% | SUPERSEDED (ERRATA-19-5791.md) |
| 95% live claim | **NÃO** |
| LOCAL_READY | **NÃO** |

### Comandos de reproof (main)

```bash
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"
export REQUIRE_REAL_DB=1
git checkout 3ab3a3a  # or origin/main
python3 -m scripts.ops.apply_migrations --dsn "$LOCAL_DATALAKE_DSN"
python3 -m scripts.coverage.dual_capability_coverage --capability both --output-dir output/coverage
python3 -m scripts.golden_path --execute-dual-coverage-only --capability both
python3 -m pytest tests/test_dual_capability_coverage.py tests/test_golden_path_coverage.py -q -o addopts=
```

## Process stack — DONE (not next work)

| # | Step | Status | Evidence |
|---|------|--------|----------|
| 1 | Implement dual fail-closed engine | **DONE** | PR #108 merge `edd7618` |
| 2 | CI green on implementation | **DONE** | Actions on #108 / main post-merge |
| 3 | Independent review PASS_FOR_MERGE | **DONE** | `independent-review-v1.3-final.md` (reviewed_commit `ed7be1c`) |
| 4 | Merge implementation to main | **DONE** | PR #108 |
| 5 | Main dual reproof | **DONE** | live summary above on `3ab3a3a` |
| 6 | Acceptance pack + controller + DOD accept | **DONE** | pack `.dod/evidence/DOD-rol-1-definition-of-done-4efe05fc94/` · PR #109 |
| 7 | Skeptic: identity/scope/view | **DONE** | PR #110 |
| 8 | Clean-env measurement tolerance | **DONE** | PR #111 full suite green |
| 9 | Cap-level measurement honesty + docs stamp | **DONE** | PR #112 · tip `3ab3a3a` |

## Próximos passos (somente operacional)

| # | Ação | Owner | Deps | Evidência / comando |
|---|------|-------|------|---------------------|
| A | Resolver CNPJ raiz ambíguo `00394494` (identity_unresolved→0) | @data-engineer | main engine DONE | dual summary mapping_status=ok, identity_unresolved_count=0 |
| B | Backfill `coverage_evidence` PNCP open_tenders frescos ≤24h | ops | A opcional | never_checked↓; dual CLI |
| C | Backfill historical_contracts ≥3y + incremental ≤7d | ops | A opcional | dual CLI contracts gate path |
| D | Re-medir dual em main após backfill | @dev/@qa | B+C | summary measurement_success=true (se identity ok) + % reais |
| E | Candidatar gates 95% só com prova live dual | @po/@qa | D | gate PASS both caps + acceptance pack 95% |
| F | Rebasar PR #107 (valores) se ainda aberta | @devops | main tip | avoid golden_path conflict |

## Non-claims

* Não há cobertura operacional 95%.
* Não há LOCAL_READY / PROJECT_DONE.
* measurement_success=false em main é **correto** enquanto identity_unresolved>0.
* Process steps 1–9 acima estão **DONE**; não reabrir como “next” sem regressão.
