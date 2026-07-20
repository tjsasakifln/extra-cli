# HANDOFF-FINAL — ENTITY-FRESHNESS-CANONICAL-ACCEPTANCE-01

## Status

**READY FOR PR / CI** — item DOD de mensurabilidade sustentado por identidade canônica.

## Baseline

| Campo | Valor |
|-------|-------|
| Base main SHA | `d6d9e1984e348d64a669546613e192e4ebf610cd` |
| Branch | `goal/entity-freshness-canonical-acceptance` |
| Worktree | `wt-entity-freshness-canonical` |
| Adapter | `freshness_by_entity/2.0.0-canonical` |

## O que foi entregue

1. Engine `scripts/coverage/freshness_by_entity.py`
   - População = `load_canonical_universe(seed).included`
   - Reconciliação registry → entity_id canônico (fail closed)
   - Dual report `notices_or_bids` / `contracts`
   - FRESH/STALE exigem timestamp + run_id + content_hash
   - Manifesto de evidência via `--evidence-manifest`
2. `config/coverage_slas.yaml` — `sla_version` + capabilities
3. `tests/test_freshness_by_entity.py` — 27 testes (wave0 + set equality + manifest tamper)
4. CI: teste obrigatório em `Test (critical readiness)` e `test-operational-expanded`
5. ADR-028 reescrito (sem migration 058 como spine)
6. Evidências em `docs/ops/campaigns/ENTITY-FRESHNESS-01/evidence/`

## Evidências operacionais (as_of 2026-07-20T12:00:00Z)

| Campo | Valor |
|-------|-------|
| Exit code | `0` |
| seed_sha256 | `d65f272812cf8dc95f3ca78c5db9a2fb2a39a759e5633eb3fb91891ad10a5486` |
| canonical_count | 1093 |
| canonical_ids_sha256 | `0b3f894d87ba71f2e0fa96887cb3075033488de1af1e6e55f97ccda0701fb396` |
| freshness-editais.json sha256 | `2a69602cce818bc65ca7281204b6316a5f5bd7ba4a0d43e02e264eab36d1efe9` |
| freshness-contracts.json sha256 | `8fa91d284528c1f89f402d845345ee7f808dcd6e2e58f49bdc9f41d384b0bc7c` |
| duplicate_count | 0 |
| missing_count | 0 |
| extra_count | 0 |
| unreconciled_count | 0 |
| list_identity_ok | true / true |
| Editais status | FRESH=0 STALE=288 INCOMPLETE=120 NEVER=685 |
| Contratos status | FRESH=365 NEVER=728 |
| Manifest | `docs/ops/campaigns/ENTITY-FRESHNESS-01/evidence/acceptance-manifest.json` |
| Wave0 review | `evidence/wave0-manual-review.md` |

**Sem claim de 95%.** Percentuais observados são descritivos apenas.

## Comando de aceite

```bash
python -m scripts.coverage.freshness_by_entity \
  --seed "Extra - alvos de licitação. R-0.xlsx" \
  --registry data/entity_source_registry.jsonl \
  --output-dir output/coverage \
  --strict \
  --as-of 2026-07-20T12:00:00+00:00 \
  --evidence-manifest docs/ops/campaigns/ENTITY-FRESHNESS-01/evidence/acceptance-manifest.json
```

## Claims

**Allowed:** mensurável por entidade; população canônica; set equality; dual capability; breaches nominais; strict fail-closed.

**Forbidden:** cobertura/freshness/recall ≥95%; LOCAL_READY; VPS_OPERATIONAL; PROJECT_DONE; len==1093 sem set equality; migration 058 / entity_source_binding como spine.

## Fora de escopo (não iniciar)

- Redução de gaps / aumento de % FRESH
- Cobertura operacional 95% / recall
- Migration 058 / bindings
- VPS / full suite / agentes / dashboards

## CI

- Local: `pytest tests/test_freshness_by_entity.py` → 27 passed
- CI run id: preencher após Actions na PR

## Parada

Após merge em main com este único item DOD comprovado — **parar**.
