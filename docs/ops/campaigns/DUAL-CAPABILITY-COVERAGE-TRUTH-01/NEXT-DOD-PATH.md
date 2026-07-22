# NEXT-DOD-PATH — após verdade dual de cobertura v1.1

**Campaign:** `DUAL-CAPABILITY-COVERAGE-TRUTH-01`  
**Implementation tip:** `campaign/dual-capability-coverage-truth` @ `2dd7c8c`  
**PR:** #108  
**Adapter:** `dual_capability_coverage/1.1.0`

## Estado comprovado (reproof local af045a9 / tip 2dd7c8c)

| Campo | Valor |
|-------|-------|
| Method | `dual_capability_coverage` |
| Universe | 1093 (seed stamps + ordered ids) |
| open_tenders | den=1093 num=0 never_checked=1093 gate FAIL 0% |
| historical_contracts | den=1093 num=0 never_checked=1093 gate FAIL 0% |
| measurement_success | true |
| coverage_gate_pass | false |
| schema_compatibility_mode | modern |
| identity_unresolved_count | 4 (ambiguous cnpj8 `00394494`, no first-wins) |
| mapping | partial 1089/2085 db entities mapped |
| legacy 19.5791% | SUPERSEDED |
| 95% live claim | **NÃO** |

### Comandos de reproof

```bash
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"
export REQUIRE_REAL_DB=1
python3 -m scripts.ops.apply_migrations --dsn "$LOCAL_DATALAKE_DSN"
python3 -m scripts.coverage.dual_capability_coverage --capability both --output-dir output/coverage
python3 -m scripts.golden_path --execute-dual-coverage-only --capability both
python3 -m pytest tests/test_dual_capability_coverage.py tests/test_golden_path_coverage.py -q -o addopts=
```

## Próximos passos priorizados

| # | Ação | Owner | Deps | Evidência |
|---|------|-------|------|-----------|
| 1 | CI full suite verde no tip final | @devops | push 2dd7c8c | Actions run SUCCESS |
| 2 | Revisão independente PASS_FOR_MERGE (não implementador) | @qa | CI green | review file + verdict |
| 3 | Merge PR #108 → main | @devops | review PASS | merge SHA |
| 4 | Reproof dual em main | @dev/@qa | merge | summary JSON + git_sha main |
| 5 | Acceptance pack + register_acceptance / controller | @qa/@po | main reproof | pack path |
| 6 | DOD §12.1 calcula cobertura → ACCEPTED (só método dual) | @po | controller | DOD checkbox + evidence |
| 7 | Resolver identity_unresolved (cnpj8 ambíguo) | @data-engineer | main | zero ambiguous roots or explicit blocked |
| 8 | Backfill coverage_evidence PNCP open_tenders frescos ≤24h | ops | engine | never_checked ↓ |
| 9 | Backfill historical_contracts ≥3y + incremental ≤7d | ops | engine | dual % real |
| 10 | Candidatar gates 95% só com prova live dual | @po/@qa | 8+9 | gate PASS dual |

## Non-claims

* Não há cobertura 95%.
* Não há LOCAL_READY / PROJECT_DONE.
* Não declarar GOAL DONE até itens 1–6.
* PR #107 (valores report) é concorrente em golden_path — rebasar após merge dual se necessário.
